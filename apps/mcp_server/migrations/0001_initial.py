import uuid

import apps.mcp_server.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="McpOAuthClient",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "client_id",
                    models.CharField(
                        default=apps.mcp_server.models.generate_oauth_token,
                        max_length=96,
                        unique=True,
                    ),
                ),
                ("client_secret_hash", models.CharField(blank=True, default="", max_length=128)),
                ("client_name", models.CharField(blank=True, default="", max_length=255)),
                (
                    "redirect_uris",
                    models.JSONField(default=apps.mcp_server.models.default_redirect_uris),
                ),
                (
                    "grant_types",
                    models.JSONField(default=apps.mcp_server.models.default_grant_types),
                ),
                (
                    "response_types",
                    models.JSONField(default=apps.mcp_server.models.default_response_types),
                ),
                ("scope", models.CharField(blank=True, default="mcp:user", max_length=255)),
                ("token_endpoint_auth_method", models.CharField(default="none", max_length=64)),
            ],
        ),
        migrations.CreateModel(
            name="McpOAuthAuthorizationCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "code",
                    models.CharField(
                        default=apps.mcp_server.models.generate_oauth_token,
                        max_length=128,
                        unique=True,
                    ),
                ),
                ("redirect_uri", models.URLField(max_length=2048)),
                ("code_challenge", models.CharField(max_length=255)),
                ("code_challenge_method", models.CharField(default="S256", max_length=16)),
                ("scope", models.CharField(default="mcp:user", max_length=255)),
                ("resource", models.URLField(max_length=2048)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="authorization_codes",
                        to="mcp_server.mcpoauthclient",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_authorization_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="McpOAuthAccessToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "token",
                    models.CharField(
                        default=apps.mcp_server.models.generate_oauth_token,
                        max_length=128,
                        unique=True,
                    ),
                ),
                ("scope", models.CharField(default="mcp:user", max_length=255)),
                ("resource", models.URLField(max_length=2048)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="access_tokens",
                        to="mcp_server.mcpoauthclient",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_access_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="McpOAuthRefreshToken",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "token",
                    models.CharField(
                        default=apps.mcp_server.models.generate_oauth_token,
                        max_length=128,
                        unique=True,
                    ),
                ),
                ("scope", models.CharField(default="mcp:user", max_length=255)),
                ("resource", models.URLField(max_length=2048)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="refresh_tokens",
                        to="mcp_server.mcpoauthclient",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_refresh_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
