import base64
import hashlib
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import override_settings
from django.utils import timezone

from apps.mcp_server.auth import authenticate_mcp_headers
from apps.mcp_server.models import McpOAuthAccessToken, McpOAuthClient

VALID_PKCE_VERIFIER = "test-verifier-value-that-is-long-enough-for-pkce"


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="mcpuser",
        email="mcpuser@example.com",
        password="password123",
    )


@pytest.fixture
def profile(user):
    return user.profile


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _register_public_client(client, redirect_uri="http://127.0.0.1:33418/callback"):
    response = client.post(
        "/oauth/register",
        data=json.dumps(
            {
                "client_name": "Test MCP Client",
                "redirect_uris": [redirect_uri],
                "token_endpoint_auth_method": "none",
            }
        ),
        content_type="application/json",
    )
    assert response.status_code == 201
    return response.json()["client_id"], redirect_uri


def _authorize_client(client, user, client_id, redirect_uri, verifier):
    client.force_login(user)
    response = client.post(
        "/oauth/authorize",
        data={"decision": "approve"},
        query_params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp:user",
            "state": "state-123",
            "resource": "https://example.com/mcp",
            "code_challenge": _pkce_challenge(verifier),
            "code_challenge_method": "S256",
        },
    )
    assert response.status_code == 302
    params = parse_qs(urlsplit(response["Location"]).query)
    assert params["state"] == ["state-123"]
    return params["code"][0]


def _exchange_code(client, client_id, code, redirect_uri, verifier):
    return client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "resource": "https://example.com/mcp",
        },
    )


@override_settings(SITE_URL="https://example.com")
def test_oauth_metadata_advertises_mcp_discovery(client):
    auth_response = client.get("/.well-known/oauth-authorization-server")
    assert auth_response.status_code == 200
    auth_metadata = auth_response.json()
    assert auth_metadata["issuer"] == "https://example.com"
    assert auth_metadata["authorization_endpoint"] == "https://example.com/oauth/authorize"
    assert auth_metadata["registration_endpoint"] == "https://example.com/oauth/register"
    assert "S256" in auth_metadata["code_challenge_methods_supported"]

    resource_response = client.get("/.well-known/oauth-protected-resource/mcp")
    assert resource_response.status_code == 200
    resource_metadata = resource_response.json()
    assert resource_metadata["resource"] == "https://example.com/mcp"
    assert resource_metadata["authorization_servers"] == ["https://example.com"]
    assert resource_metadata["scopes_supported"] == ["mcp:user"]


@pytest.mark.django_db
@override_settings(SITE_URL="https://example.com")
def test_dcr_registers_public_mcp_client(client):
    response = client.post(
        "/oauth/register",
        data=json.dumps(
            {
                "client_name": "Test MCP Client",
                "redirect_uris": ["http://127.0.0.1:33418"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["client_id"]
    assert payload["token_endpoint_auth_method"] == "none"
    assert "client_secret" not in payload


@pytest.mark.django_db
def test_dcr_returns_secret_once_and_stores_only_hash_for_confidential_client(client):
    response = client.post(
        "/oauth/register",
        data=json.dumps(
            {
                "client_name": "Confidential MCP Client",
                "redirect_uris": ["https://client.example.com/callback"],
                "token_endpoint_auth_method": "client_secret_post",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 201
    payload = response.json()
    oauth_client = McpOAuthClient.objects.get(client_id=payload["client_id"])
    assert payload["client_secret"]
    assert oauth_client.client_secret_hash
    assert oauth_client.client_secret_hash != payload["client_secret"]
    assert oauth_client.check_client_secret(payload["client_secret"])


@pytest.mark.django_db
def test_dcr_rejects_oversized_client_name(client):
    response = client.post(
        "/oauth/register",
        data=json.dumps(
            {
                "client_name": "x" * 256,
                "redirect_uris": ["http://127.0.0.1:33418"],
                "token_endpoint_auth_method": "none",
            }
        ),
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"


@pytest.mark.django_db
def test_dcr_rejects_non_utf8_json(client):
    response = client.post(
        "/oauth/register",
        data=b"\xff",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.json()["error"] == "invalid_client_metadata"


@pytest.mark.django_db(transaction=True)
def test_legacy_api_key_header_still_authenticates_mcp(profile):
    api_key = profile.rotate_api_key()
    authenticated_profile = authenticate_mcp_headers({"x-api-key": api_key})

    assert authenticated_profile == profile


@pytest.mark.django_db(transaction=True)
@override_settings(SITE_URL="https://example.com")
def test_oauth_authorization_code_flow_issues_mcp_access_token(client, user, profile):
    client_id, redirect_uri = _register_public_client(client)
    verifier = VALID_PKCE_VERIFIER
    code = _authorize_client(client, user, client_id, redirect_uri, verifier)
    token_response = _exchange_code(client, client_id, code, redirect_uri, verifier)

    assert token_response.status_code == 200
    access_token = token_response.json()["access_token"]
    assert token_response.json()["refresh_token"]
    assert token_response.json()["resource"] == "https://example.com/mcp"
    assert authenticate_mcp_headers({"authorization": f"Bearer {access_token}"}) == profile


@pytest.mark.django_db
@override_settings(SITE_URL="https://example.com")
def test_authorization_code_cannot_be_reused(client, user):
    client_id, redirect_uri = _register_public_client(client)
    verifier = VALID_PKCE_VERIFIER
    code = _authorize_client(client, user, client_id, redirect_uri, verifier)

    assert _exchange_code(client, client_id, code, redirect_uri, verifier).status_code == 200
    replay_response = _exchange_code(client, client_id, code, redirect_uri, verifier)

    assert replay_response.status_code == 400
    assert replay_response.json()["error"] == "invalid_grant"


@pytest.mark.django_db(transaction=True)
@override_settings(SITE_URL="https://example.com")
def test_refresh_rotation_revokes_existing_access_tokens(client, user):
    client_id, redirect_uri = _register_public_client(client)
    verifier = VALID_PKCE_VERIFIER
    code = _authorize_client(client, user, client_id, redirect_uri, verifier)
    token_payload = _exchange_code(client, client_id, code, redirect_uri, verifier).json()

    refresh_response = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": token_payload["refresh_token"],
        },
    )

    assert refresh_response.status_code == 200
    old_access_token = token_payload["access_token"]
    new_access_token = refresh_response.json()["access_token"]
    assert refresh_response.json()["resource"] == "https://example.com/mcp"
    assert authenticate_mcp_headers({"authorization": f"Bearer {old_access_token}"}) is None
    assert authenticate_mcp_headers({"authorization": f"Bearer {new_access_token}"}) == user.profile


@pytest.mark.django_db
@override_settings(SITE_URL="https://example.com")
def test_short_pkce_verifier_is_rejected(client, user):
    client_id, redirect_uri = _register_public_client(client)
    verifier = "short-verifier"
    code = _authorize_client(client, user, client_id, redirect_uri, verifier)

    token_response = _exchange_code(client, client_id, code, redirect_uri, verifier)

    assert token_response.status_code == 400
    assert token_response.json()["error"] == "invalid_grant"


@pytest.mark.django_db
@override_settings(SITE_URL="https://example.com")
def test_oversized_pkce_challenge_is_rejected(client, user):
    client_id, redirect_uri = _register_public_client(client)
    client.force_login(user)

    response = client.get(
        "/oauth/authorize",
        query_params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp:user",
            "state": "state-123",
            "resource": "https://example.com/mcp",
            "code_challenge": "x" * 256,
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code == 302
    params = parse_qs(urlsplit(response["Location"]).query)
    assert params["error"] == ["invalid_request"]
    assert params["state"] == ["state-123"]


@pytest.mark.django_db
def test_revoke_requires_client_auth_for_confidential_clients(client, user):
    oauth_client = McpOAuthClient(
        client_name="Confidential MCP Client",
        redirect_uris=["https://client.example.com/callback"],
        token_endpoint_auth_method="client_secret_post",
    )
    oauth_client.set_client_secret("client-secret")
    oauth_client.save()
    access_token = McpOAuthAccessToken.objects.create(
        client=oauth_client,
        user=user,
        scope="mcp:user",
        resource="https://example.com/mcp",
        expires_at=timezone.now() + timedelta(hours=1),
    )

    missing_secret_response = client.post(
        "/oauth/revoke",
        data={"client_id": oauth_client.client_id, "token": access_token.token},
    )
    access_token.refresh_from_db()
    assert missing_secret_response.status_code == 401
    assert access_token.revoked_at is None

    revoke_response = client.post(
        "/oauth/revoke",
        data={
            "client_id": oauth_client.client_id,
            "client_secret": "client-secret",
            "token": access_token.token,
        },
    )
    access_token.refresh_from_db()
    assert revoke_response.status_code == 200
    assert access_token.revoked_at is not None


@pytest.mark.django_db
def test_revoke_only_revokes_tokens_for_authenticated_client(client, user):
    owner_client = McpOAuthClient.objects.create(
        client_name="Owner MCP Client",
        redirect_uris=["https://owner.example.com/callback"],
        token_endpoint_auth_method="none",
    )
    other_client = McpOAuthClient.objects.create(
        client_name="Other MCP Client",
        redirect_uris=["https://other.example.com/callback"],
        token_endpoint_auth_method="none",
    )
    access_token = McpOAuthAccessToken.objects.create(
        client=owner_client,
        user=user,
        scope="mcp:user",
        resource="https://example.com/mcp",
        expires_at=timezone.now() + timedelta(hours=1),
    )

    client.post(
        "/oauth/revoke",
        data={"client_id": other_client.client_id, "token": access_token.token},
    )
    access_token.refresh_from_db()
    assert access_token.revoked_at is None

    client.post(
        "/oauth/revoke",
        data={"client_id": owner_client.client_id, "token": access_token.token},
    )
    access_token.refresh_from_db()
    assert access_token.revoked_at is not None
