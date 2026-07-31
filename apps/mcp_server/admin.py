from django.contrib import admin

from apps.mcp_server.models import (
    McpOAuthAccessToken,
    McpOAuthAuthorizationCode,
    McpOAuthClient,
    McpOAuthRefreshToken,
)


@admin.register(McpOAuthClient)
class McpOAuthClientAdmin(admin.ModelAdmin):
    list_display = ("client_name", "client_id", "token_endpoint_auth_method", "created_at")
    search_fields = ("client_name", "client_id")


@admin.register(McpOAuthAuthorizationCode)
class McpOAuthAuthorizationCodeAdmin(admin.ModelAdmin):
    list_display = ("client", "user", "scope", "expires_at", "used_at", "created_at")
    search_fields = ("client__client_name", "client__client_id", "user__email")


@admin.register(McpOAuthAccessToken)
class McpOAuthAccessTokenAdmin(admin.ModelAdmin):
    list_display = ("client", "user", "scope", "expires_at", "revoked_at", "created_at")
    search_fields = ("client__client_name", "client__client_id", "user__email")


@admin.register(McpOAuthRefreshToken)
class McpOAuthRefreshTokenAdmin(admin.ModelAdmin):
    list_display = ("client", "user", "scope", "expires_at", "revoked_at", "created_at")
    search_fields = ("client__client_name", "client__client_id", "user__email")
