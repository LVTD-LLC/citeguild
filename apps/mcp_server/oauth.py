import base64
import hashlib
import json
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from django.contrib.auth.views import redirect_to_login
from django.db import transaction
from django.http import HttpRequest, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.views import build_absolute_public_url
from apps.mcp_server.auth import MCP_OAUTH_SCOPE, canonical_mcp_resource_url
from apps.mcp_server.models import (
    McpOAuthAccessToken,
    McpOAuthAuthorizationCode,
    McpOAuthClient,
    McpOAuthRefreshToken,
    generate_oauth_token,
    hash_client_secret,
)

ACCESS_TOKEN_SECONDS = 60 * 60
AUTHORIZATION_CODE_SECONDS = 10 * 60
REFRESH_TOKEN_DAYS = 30
SUPPORTED_SCOPES = {MCP_OAUTH_SCOPE, "offline_access"}
TOKEN_AUTH_METHODS = {"none", "client_secret_basic", "client_secret_post"}
PKCE_VERIFIER_MIN_LENGTH = 43
PKCE_VERIFIER_MAX_LENGTH = 128
PKCE_ALLOWED_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~")


def _issuer() -> str:
    return build_absolute_public_url("/").rstrip("/")


def _url(path: str) -> str:
    return build_absolute_public_url(path)


def _resource_aliases() -> set[str]:
    resource = canonical_mcp_resource_url()
    return {resource, f"{resource}/"}


def _resource_documentation_url() -> str:
    return _url("/docs/features/mcp/")


def _json_body(request: HttpRequest) -> dict:
    if (request.content_type or "").startswith("application/json"):
        try:
            body = request.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise json.JSONDecodeError("Invalid UTF-8 JSON body", "", 0) from exc
        return json.loads(body or "{}")
    return request.POST.dict()


def _normalize_scope(scope: str | None) -> str:
    requested = set((scope or MCP_OAUTH_SCOPE).split())
    if not requested:
        requested = {MCP_OAUTH_SCOPE}
    requested.add(MCP_OAUTH_SCOPE)
    unsupported = requested - SUPPORTED_SCOPES
    if unsupported:
        raise ValueError(f"Unsupported OAuth scope: {', '.join(sorted(unsupported))}")
    ordered_scopes = [MCP_OAUTH_SCOPE, "offline_access"]
    return " ".join(scope_name for scope_name in ordered_scopes if scope_name in requested)


def _is_valid_pkce_value(value: str) -> bool:
    return PKCE_VERIFIER_MIN_LENGTH <= len(value) <= PKCE_VERIFIER_MAX_LENGTH and all(
        char in PKCE_ALLOWED_CHARS for char in value
    )


def _is_allowed_redirect_uri(uri: str) -> bool:
    parsed = urlsplit(uri)
    if parsed.scheme == "https" and parsed.netloc:
        return True
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    return False


def _validate_resource(resource: str | None) -> str:
    if not resource:
        return canonical_mcp_resource_url()
    if resource not in _resource_aliases():
        raise ValueError("Invalid MCP OAuth resource.")
    return canonical_mcp_resource_url()


def _redirect_with_params(redirect_uri: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


def _redirect_error(redirect_uri: str, error: str, state: str = "", description: str = ""):
    params = {"error": error}
    if state:
        params["state"] = state
    if description:
        params["error_description"] = description
    return redirect(_redirect_with_params(redirect_uri, params))


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    if not _is_valid_pkce_value(code_verifier) or not _is_valid_pkce_value(code_challenge):
        return False

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return computed == code_challenge


def _basic_auth_client_credentials(request: HttpRequest) -> tuple[str, str]:
    authorization = request.headers.get("Authorization", "")
    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "basic" or not credentials:
        return "", ""

    try:
        decoded = base64.b64decode(credentials).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return "", ""

    client_id, _, client_secret = decoded.partition(":")
    return client_id, client_secret


def _authenticate_token_client(request: HttpRequest, data: dict) -> McpOAuthClient | None:
    basic_client_id, basic_client_secret = _basic_auth_client_credentials(request)
    client_id = basic_client_id or data.get("client_id", "")
    client_secret = basic_client_secret or data.get("client_secret", "")
    if not client_id:
        return None

    client = McpOAuthClient.objects.filter(client_id=client_id).first()
    if client is None:
        return None

    if client.token_endpoint_auth_method == "none":
        return client

    if client.check_client_secret(client_secret):
        return client

    return None


def oauth_authorization_server_metadata(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "issuer": _issuer(),
            "authorization_endpoint": _url("/oauth/authorize"),
            "token_endpoint": _url("/oauth/token"),
            "registration_endpoint": _url("/oauth/register"),
            "revocation_endpoint": _url("/oauth/revoke"),
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": sorted(TOKEN_AUTH_METHODS),
            "scopes_supported": [MCP_OAUTH_SCOPE, "offline_access"],
            "resource_parameter_supported": True,
        }
    )


def oauth_protected_resource_metadata(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        {
            "resource": canonical_mcp_resource_url(),
            "authorization_servers": [_issuer()],
            "scopes_supported": [MCP_OAUTH_SCOPE],
            "bearer_methods_supported": ["header"],
            "resource_documentation": _resource_documentation_url(),
        }
    )


@csrf_exempt
@require_POST
def register_client(request: HttpRequest) -> JsonResponse:  # noqa: C901
    try:
        data = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)

    redirect_uris = data.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not redirect_uris:
        return JsonResponse({"error": "invalid_redirect_uri"}, status=400)
    if any(not isinstance(uri, str) or not _is_allowed_redirect_uri(uri) for uri in redirect_uris):
        return JsonResponse({"error": "invalid_redirect_uri"}, status=400)

    grant_types = data.get("grant_types") or ["authorization_code", "refresh_token"]
    response_types = data.get("response_types") or ["code"]
    auth_method = data.get("token_endpoint_auth_method") or "none"
    if auth_method not in TOKEN_AUTH_METHODS:
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)
    if not isinstance(grant_types, list) or not isinstance(response_types, list):
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)
    if any(grant_type not in {"authorization_code", "refresh_token"} for grant_type in grant_types):
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)
    if any(response_type != "code" for response_type in response_types):
        return JsonResponse({"error": "invalid_client_metadata"}, status=400)

    try:
        scope = _normalize_scope(data.get("scope"))
    except ValueError as exc:
        return JsonResponse({"error": "invalid_scope", "error_description": str(exc)}, status=400)

    client_name = data.get("client_name") or "CiteGuild MCP client"
    if not isinstance(client_name, str) or len(client_name) > 255:
        return JsonResponse(
            {
                "error": "invalid_client_metadata",
                "error_description": "client_name must be a string of at most 255 characters",
            },
            status=400,
        )

    client_secret = "" if auth_method == "none" else generate_oauth_token()
    client = McpOAuthClient.objects.create(
        client_secret_hash="" if not client_secret else hash_client_secret(client_secret),
        client_name=client_name,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        response_types=response_types,
        scope=scope,
        token_endpoint_auth_method=auth_method,
    )

    response = {
        "client_id": client.client_id,
        "client_id_issued_at": int(client.created_at.timestamp()),
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "grant_types": client.grant_types,
        "response_types": client.response_types,
        "scope": client.scope,
        "token_endpoint_auth_method": client.token_endpoint_auth_method,
    }
    if client_secret:
        response["client_secret"] = client_secret
        response["client_secret_expires_at"] = 0
    return JsonResponse(response, status=201)


def _validated_authorization_request(request: HttpRequest):
    client_id = request.GET.get("client_id", "")
    redirect_uri = request.GET.get("redirect_uri", "")
    state = request.GET.get("state", "")
    code_challenge = request.GET.get("code_challenge", "")

    client = McpOAuthClient.objects.filter(client_id=client_id).first()
    if client is None:
        return None, None, HttpResponseBadRequest("Unknown OAuth client.")
    if redirect_uri not in client.redirect_uris:
        return None, None, HttpResponseBadRequest("Invalid OAuth redirect_uri.")
    if request.GET.get("response_type") != "code":
        return None, None, _redirect_error(redirect_uri, "unsupported_response_type", state)
    if request.GET.get("code_challenge_method") != "S256" or not _is_valid_pkce_value(
        code_challenge
    ):
        return (
            None,
            None,
            _redirect_error(
                redirect_uri,
                "invalid_request",
                state,
                "MCP OAuth requires PKCE with S256 and a valid code_challenge.",
            ),
        )

    try:
        scope = _normalize_scope(request.GET.get("scope"))
        resource = _validate_resource(request.GET.get("resource"))
    except ValueError as exc:
        return None, None, _redirect_error(redirect_uri, "invalid_request", state, str(exc))

    authorization = {
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
        "resource": resource,
    }
    return client, authorization, None


@require_http_methods(["GET", "POST"])
def authorize(request: HttpRequest):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())

    client, authorization, error_response = _validated_authorization_request(request)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        return render(
            request,
            "mcp_server/authorize.html",
            {
                "client": client,
                "scope": authorization["scope"],
                "project_name": "CiteGuild",
            },
        )

    if request.POST.get("decision") != "approve":
        return _redirect_error(
            authorization["redirect_uri"],
            "access_denied",
            authorization["state"],
        )

    code = McpOAuthAuthorizationCode.objects.create(
        client=client,
        user=request.user,
        redirect_uri=authorization["redirect_uri"],
        code_challenge=request.GET["code_challenge"],
        code_challenge_method="S256",
        scope=authorization["scope"],
        resource=authorization["resource"],
        expires_at=timezone.now() + timedelta(seconds=AUTHORIZATION_CODE_SECONDS),
    )
    params = {"code": code.code}
    if authorization["state"]:
        params["state"] = authorization["state"]
    return redirect(_redirect_with_params(authorization["redirect_uri"], params))


def _token_response(access_token: McpOAuthAccessToken, refresh_token: McpOAuthRefreshToken):
    expires_in = max(0, int((access_token.expires_at - timezone.now()).total_seconds()))
    response = JsonResponse(
        {
            "access_token": access_token.token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "refresh_token": refresh_token.token,
            "scope": access_token.scope,
            "resource": access_token.resource,
        }
    )
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _issue_tokens(client: McpOAuthClient, user, scope: str, resource: str):
    access_token = McpOAuthAccessToken.objects.create(
        client=client,
        user=user,
        scope=scope,
        resource=resource,
        expires_at=timezone.now() + timedelta(seconds=ACCESS_TOKEN_SECONDS),
    )
    refresh_token = McpOAuthRefreshToken.objects.create(
        client=client,
        user=user,
        scope=scope,
        resource=resource,
        expires_at=timezone.now() + timedelta(days=REFRESH_TOKEN_DAYS),
    )
    return access_token, refresh_token


@csrf_exempt
@require_POST
def token(request: HttpRequest) -> JsonResponse:
    try:
        data = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_request"}, status=400)
    client = _authenticate_token_client(request, data)
    if client is None:
        return JsonResponse({"error": "invalid_client"}, status=401)

    grant_type = data.get("grant_type")
    if grant_type == "authorization_code":
        with transaction.atomic():
            code = (
                McpOAuthAuthorizationCode.objects.select_for_update()
                .select_related("client", "user")
                .filter(code=data.get("code", ""), client=client)
                .first()
            )
            if (
                code is None
                or code.used_at is not None
                or code.expires_at <= timezone.now()
                or code.redirect_uri != data.get("redirect_uri")
            ):
                return JsonResponse({"error": "invalid_grant"}, status=400)
            if not _verify_pkce(data.get("code_verifier", ""), code.code_challenge):
                return JsonResponse({"error": "invalid_grant"}, status=400)

            try:
                _validate_resource(data.get("resource") or code.resource)
            except ValueError as exc:
                return JsonResponse(
                    {"error": "invalid_target", "error_description": str(exc)},
                    status=400,
                )

            code.used_at = timezone.now()
            code.save(update_fields=["used_at", "updated_at"])
            access_token, refresh_token = _issue_tokens(
                client,
                code.user,
                code.scope,
                code.resource,
            )
        return _token_response(access_token, refresh_token)

    if grant_type == "refresh_token":
        with transaction.atomic():
            refresh_token = (
                McpOAuthRefreshToken.objects.select_for_update()
                .select_related("client", "user")
                .filter(
                    token=data.get("refresh_token", ""),
                    client=client,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if refresh_token is None:
                return JsonResponse({"error": "invalid_grant"}, status=400)

            now = timezone.now()
            refresh_token.revoked_at = now
            refresh_token.save(update_fields=["revoked_at", "updated_at"])
            McpOAuthAccessToken.objects.filter(
                client=client,
                user=refresh_token.user,
                revoked_at__isnull=True,
            ).update(revoked_at=now)
            access_token, new_refresh_token = _issue_tokens(
                client,
                refresh_token.user,
                refresh_token.scope,
                refresh_token.resource,
            )
        return _token_response(access_token, new_refresh_token)

    return JsonResponse({"error": "unsupported_grant_type"}, status=400)


@csrf_exempt
@require_POST
def revoke(request: HttpRequest) -> JsonResponse:
    try:
        data = _json_body(request)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid_request"}, status=400)

    client = _authenticate_token_client(request, data)
    if client is None:
        return JsonResponse({"error": "invalid_client"}, status=401)

    token_value = data.get("token", "")
    now = timezone.now()
    McpOAuthAccessToken.objects.filter(
        token=token_value,
        client=client,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    McpOAuthRefreshToken.objects.filter(
        token=token_value,
        client=client,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    return JsonResponse({})
