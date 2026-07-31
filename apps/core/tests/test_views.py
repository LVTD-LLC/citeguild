import pytest
from allauth.account.models import EmailAddress
from django.test import override_settings
from django.urls import reverse


@pytest.mark.django_db
class TestHomeView:
    def test_home_view_status_code(self, auth_client):
        url = reverse("home")
        response = auth_client.get(url)
        assert response.status_code == 200

    def test_home_view_uses_correct_template(self, auth_client):
        url = reverse("home")
        response = auth_client.get(url)
        assert "pages/home.html" in [t.name for t in response.templates]

    def test_home_view_includes_copyable_agent_prompt(self, auth_client, profile):
        url = reverse("home")
        response = auth_client.get(url)
        content = response.content.decode()

        assert response.status_code == 200
        assert "Copy/paste prompt" in content
        assert "data-copy-button" in content
        assert "/mcp/" in content
        assert "/AGENTS.md" in content
        assert "CITEGUILD_API_KEY" in content
        assert "?api_key=" not in content

    def test_rotate_api_key_stores_hash_and_shows_key_once(self, auth_client, profile):
        response = auth_client.post(reverse("rotate_api_key"), follow=True)
        content = response.content.decode()
        profile.refresh_from_db()

        assert response.status_code == 200
        assert profile.api_key_prefix
        assert profile.api_key_hash
        assert profile.api_key_hash not in content
        assert "Copy this key now" in content
        assert profile.api_key_prefix in content

        response = auth_client.get(reverse("settings"))
        content = response.content.decode()

        assert "Copy this key now" not in content
        assert profile.api_key_prefix in content

    def test_settings_profile_form_cannot_change_login_email_directly(self, auth_client, user):
        original_email = user.email
        submitted_email = "submitted-change@example.com"
        EmailAddress.objects.update_or_create(
            user=user,
            email=original_email,
            defaults={"primary": True, "verified": True},
        )

        response = auth_client.post(
            reverse("settings"),
            data={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": submitted_email,
            },
        )

        assert response.status_code == 302
        user.refresh_from_db()
        assert user.first_name == "Ada"
        assert user.last_name == "Lovelace"
        assert user.email == original_email
        assert not EmailAddress.objects.filter(user=user, email=submitted_email).exists()


@override_settings(SITE_URL="http://example.com")
def test_build_absolute_public_url_upgrades_non_local_http():
    from apps.core.views import build_absolute_public_url

    assert build_absolute_public_url("/api/user") == "https://example.com/api/user"


@override_settings(SITE_URL="http://notlocalhost.example")
def test_build_absolute_public_url_does_not_treat_hostname_substrings_as_local():
    from apps.core.views import build_absolute_public_url

    assert build_absolute_public_url("/api/user") == "https://notlocalhost.example/api/user"


@override_settings(SITE_URL="http://localhost:8000")
def test_build_absolute_public_url_preserves_localhost_http():
    from apps.core.views import build_absolute_public_url

    assert build_absolute_public_url("/api/user") == "http://localhost:8000/api/user"
