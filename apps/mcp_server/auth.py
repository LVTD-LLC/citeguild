import logging

from asgiref.sync import sync_to_async
from django.db import close_old_connections
from django.utils import timezone
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from apps.api.auth import get_profile_for_api_key
from apps.core.models import Profile
from apps.core.views import build_absolute_public_url
from apps.mcp_server.models import McpOAuthAccessToken

logger = logging.getLogger(__name__)

MCP_OAUTH_SCOPE = "mcp:user"


def canonical_mcp_resource_url() -> str:
    return build_absolute_public_url("/mcp").rstrip("/")


def protected_resource_metadata_url() -> str:
    return build_absolute_public_url("/.well-known/oauth-protected-resource/mcp")


def build_www_authenticate_header(error: str | None = None) -> str:
    parts = [
        f'resource_metadata="{protected_resource_metadata_url()}"',
        f'scope="{MCP_OAUTH_SCOPE}"',
    ]
    if error:
        parts.insert(0, f'error="{error}"')
    return "Bearer " + ", ".join(parts)


def _bearer_token(headers) -> str:
    authorization = headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        return token.strip()
    return ""


def _profile_for_oauth_token(token: str) -> Profile | None:
    if not token:
        return None

    now = timezone.now()
    access_token = (
        McpOAuthAccessToken.objects.select_related("user", "client")
        .filter(token=token, revoked_at__isnull=True, expires_at__gt=now)
        .first()
    )
    if access_token is None:
        return None

    profile, _created = Profile.objects.select_related("user").get_or_create(user=access_token.user)
    return profile


def _profile_for_api_key(key: str) -> Profile | None:
    if not key:
        return None

    return get_profile_for_api_key(key)


def authenticate_mcp_headers(headers) -> Profile | None:
    """Authenticate OAuth access tokens first, then legacy API-key headers."""
    close_old_connections()
    try:
        bearer_token = _bearer_token(headers)
        if bearer_token:
            profile = _profile_for_oauth_token(bearer_token)
            if profile is not None:
                return profile

            profile = _profile_for_api_key(bearer_token)
            if profile is not None:
                logger.info(
                    "mcp.authentication.completed",
                    extra={
                        "event.name": "mcp.authentication.completed",
                        "auth.method": "legacy_bearer_api_key",
                        "profile_id": profile.id,
                        "outcome": "success",
                    },
                )
                return profile

        header_key = headers.get("x-api-key", "").strip()
        profile = _profile_for_api_key(header_key)
        if profile is not None:
            logger.info(
                "mcp.authentication.completed",
                extra={
                    "event.name": "mcp.authentication.completed",
                    "auth.method": "legacy_x_api_key",
                    "profile_id": profile.id,
                    "outcome": "success",
                },
            )
            return profile

        return None
    finally:
        close_old_connections()


class McpAuthMiddleware:
    """Protect the hosted MCP transport while preserving legacy API-key headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        profile = await sync_to_async(authenticate_mcp_headers, thread_sensitive=True)(headers)
        if profile is not None:
            await self.app(scope, receive, send)
            return

        has_credentials = bool(_bearer_token(headers) or headers.get("x-api-key", "").strip())
        response = JSONResponse(
            {"detail": "MCP authentication required."},
            status_code=401,
            headers={
                "WWW-Authenticate": build_www_authenticate_header(
                    "invalid_token" if has_credentials else None
                )
            },
        )
        await response(scope, receive, send)
