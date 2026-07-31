from django.urls import path

from apps.mcp_server import oauth

urlpatterns = [
    path(
        ".well-known/oauth-authorization-server",
        oauth.oauth_authorization_server_metadata,
        name="mcp_oauth_authorization_server_metadata",
    ),
    path(
        ".well-known/openid-configuration",
        oauth.oauth_authorization_server_metadata,
        name="mcp_openid_configuration",
    ),
    path(
        ".well-known/oauth-protected-resource",
        oauth.oauth_protected_resource_metadata,
        name="mcp_oauth_protected_resource_metadata",
    ),
    path(
        ".well-known/oauth-protected-resource/mcp",
        oauth.oauth_protected_resource_metadata,
        name="mcp_oauth_protected_resource_metadata_with_path",
    ),
    path(
        ".well-known/oauth-protected-resource/mcp/",
        oauth.oauth_protected_resource_metadata,
        name="mcp_oauth_protected_resource_metadata_with_trailing_path",
    ),
    path("oauth/register", oauth.register_client, name="mcp_oauth_register"),
    path("oauth/authorize", oauth.authorize, name="mcp_oauth_authorize"),
    path("oauth/token", oauth.token, name="mcp_oauth_token"),
    path("oauth/revoke", oauth.revoke, name="mcp_oauth_revoke"),
]
