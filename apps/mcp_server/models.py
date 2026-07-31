import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import models

from apps.core.base_models import BaseModel


def generate_oauth_token() -> str:
    return secrets.token_urlsafe(48)


CLIENT_SECRET_SALT_BYTES = 16
CLIENT_SECRET_HASH_VERSION = "v1"
CLIENT_SECRET_HASH_CONTEXT = "citeguild-mcp-client-secret-v1"


def hash_client_secret(client_secret: str) -> str:
    salt = secrets.token_urlsafe(CLIENT_SECRET_SALT_BYTES)
    digest = _hash_client_secret_with_salt(client_secret, salt)
    return f"{CLIENT_SECRET_HASH_VERSION}${salt}${digest}"


def verify_client_secret(client_secret: str, client_secret_hash: str) -> bool:
    if not client_secret or not client_secret_hash:
        return False

    try:
        version, salt, digest = client_secret_hash.split("$", 2)
    except ValueError:
        return False

    if version != CLIENT_SECRET_HASH_VERSION or not salt or not digest:
        return False

    return hmac.compare_digest(_hash_client_secret_with_salt(client_secret, salt), digest)


def _hash_client_secret_with_salt(client_secret: str, salt: str) -> str:
    value = f"{CLIENT_SECRET_HASH_CONTEXT}:{salt}:{client_secret}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def default_grant_types() -> list[str]:
    return ["authorization_code", "refresh_token"]


def default_response_types() -> list[str]:
    return ["code"]


def default_redirect_uris() -> list[str]:
    return []


class McpOAuthClient(BaseModel):
    """OAuth client registered by an MCP client through Dynamic Client Registration."""

    client_id = models.CharField(max_length=96, unique=True, default=generate_oauth_token)
    client_secret_hash = models.CharField(max_length=128, blank=True, default="")
    client_name = models.CharField(max_length=255, blank=True, default="")
    redirect_uris = models.JSONField(default=default_redirect_uris)
    grant_types = models.JSONField(default=default_grant_types)
    response_types = models.JSONField(default=default_response_types)
    scope = models.CharField(max_length=255, blank=True, default="mcp:user")
    token_endpoint_auth_method = models.CharField(max_length=64, default="none")

    def __str__(self):
        return self.client_name or self.client_id

    def set_client_secret(self, client_secret: str | None = None) -> str:
        client_secret = client_secret or generate_oauth_token()
        self.client_secret_hash = hash_client_secret(client_secret)
        return client_secret

    def check_client_secret(self, client_secret: str) -> bool:
        return verify_client_secret(client_secret, self.client_secret_hash)


class McpOAuthAuthorizationCode(BaseModel):
    code = models.CharField(max_length=128, unique=True, default=generate_oauth_token)
    client = models.ForeignKey(
        McpOAuthClient,
        on_delete=models.CASCADE,
        related_name="authorization_codes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_authorization_codes",
    )
    redirect_uri = models.URLField(max_length=2048)
    code_challenge = models.CharField(max_length=255)
    code_challenge_method = models.CharField(max_length=16, default="S256")
    scope = models.CharField(max_length=255, default="mcp:user")
    resource = models.URLField(max_length=2048)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.client} authorization code for {self.user_id}"


class McpOAuthAccessToken(BaseModel):
    token = models.CharField(max_length=128, unique=True, default=generate_oauth_token)
    client = models.ForeignKey(
        McpOAuthClient,
        on_delete=models.CASCADE,
        related_name="access_tokens",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_access_tokens",
    )
    scope = models.CharField(max_length=255, default="mcp:user")
    resource = models.URLField(max_length=2048)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.client} access token for {self.user_id}"


class McpOAuthRefreshToken(BaseModel):
    token = models.CharField(max_length=128, unique=True, default=generate_oauth_token)
    client = models.ForeignKey(
        McpOAuthClient,
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mcp_refresh_tokens",
    )
    scope = models.CharField(max_length=255, default="mcp:user")
    resource = models.URLField(max_length=2048)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.client} refresh token for {self.user_id}"
