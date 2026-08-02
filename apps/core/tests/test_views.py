import logging
from unittest.mock import patch

import pytest
from allauth.account.models import EmailAddress
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse

from apps.core.models import Project
from apps.core.projects import ProjectService
from apps.core.sitemap_submission import (
    SitemapDocumentKind,
    SitemapSubmissionError,
    SitemapSubmissionErrorCode,
    SitemapValidation,
)


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.stripe_customer_id = "cus_test"
    profile.save(update_fields=["stripe_subscription_status", "stripe_customer_id", "updated_at"])


@pytest.mark.django_db
class TestHomeView:
    @pytest.fixture(autouse=True)
    def valid_sitemap(self, monkeypatch):
        monkeypatch.setattr(
            "apps.core.sitemap_submission.validate_sitemap",
            lambda *args, **kwargs: SitemapValidation(SitemapDocumentKind.URL_SET),
        )

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

    def test_unsubscribed_user_sees_checkout_not_add_site_form(self, auth_client):
        response = auth_client.get(reverse("home"))
        content = response.content.decode()

        assert "Subscribe for $10/month" in content
        assert 'id="add-site"' not in content

    def test_payment_success_shows_confirmation_until_webhook_grants_access(self, auth_client):
        response = auth_client.get(reverse("home"), {"payment": "success"})

        assert "Confirming your subscription" in response.content.decode()

    def test_subscribed_user_sees_empty_state_and_accessible_add_site_form(
        self, auth_client, profile
    ):
        subscribe(profile)

        response = auth_client.get(reverse("home"))
        content = response.content.decode()

        assert "No sites yet" in content
        assert 'id="add-site"' in content
        assert 'for="id_name"' in content
        assert 'for="id_sitemap_url"' in content
        assert ':aria-busy="submitting.toString()"' in content
        assert "Manage billing" in content

    def test_subscribed_user_can_add_site_from_dashboard(self, auth_client, profile):
        subscribe(profile)

        response = auth_client.post(
            reverse("home"),
            {"name": "Example", "sitemap_url": "https://EXAMPLE.com/sitemap.xml"},
            follow=True,
        )

        assert response.status_code == 200
        assert "Example was validated and queued" in response.content.decode()
        project = Project.objects.get(owner=profile)
        assert project.normalized_host == "example.com"

    def test_unsubscribed_user_cannot_post_site(self, auth_client):
        response = auth_client.post(
            reverse("home"),
            {"name": "Blocked", "sitemap_url": "https://blocked.example/sitemap.xml"},
        )

        assert response.status_code == 302
        assert response.url == reverse("pricing")
        assert not Project.objects.exists()

    @patch("apps.core.views.SitemapSubmissionService.submit", side_effect=PermissionDenied)
    def test_subscription_race_is_logged_and_redirects_to_billing(
        self, create_project, auth_client, profile, caplog
    ):
        subscribe(profile)

        with caplog.at_level(logging.WARNING, logger="apps.core.views"):
            response = auth_client.post(
                reverse("home"),
                {"name": "Race", "sitemap_url": "https://race.example/sitemap.xml"},
                follow=True,
            )

        create_project.assert_called_once()
        assert response.redirect_chain[0][0] == reverse("pricing")
        assert "subscription became inactive" in response.content.decode()
        record = next(item for item in caplog.records if item.msg == "project.create.completed")
        assert record.__dict__["operation.status"] == "subscription_became_inactive"
        assert record.outcome == "failure"

    def test_temporary_sitemap_failure_is_visible_and_retryable(
        self, auth_client, profile, monkeypatch
    ):
        subscribe(profile)
        monkeypatch.setattr(
            "apps.core.sitemap_submission.validate_sitemap",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                SitemapSubmissionError(
                    SitemapSubmissionErrorCode.TEMPORARY_FETCH,
                    retryable=True,
                )
            ),
        )

        response = auth_client.post(
            reverse("home"),
            {"name": "Temporary", "sitemap_url": "https://temporary.example/sitemap.xml"},
        )

        assert response.status_code == 503
        assert "could not be reached right now. Try again" in response.content.decode()
        assert not Project.objects.filter(name="Temporary").exists()

    def test_site_list_is_owner_scoped(self, auth_client, profile, django_user_model):
        subscribe(profile)
        ProjectService.create(
            owner=profile, name="Mine", sitemap_url="https://mine.example/sitemap.xml"
        )
        other = django_user_model.objects.create_user(username="other-dashboard", password="test")
        subscribe(other.profile)
        ProjectService.create(
            owner=other.profile,
            name="Other private site",
            sitemap_url="https://other.example/sitemap.xml",
        )

        content = auth_client.get(reverse("home")).content.decode()

        assert "Mine" in content
        assert "Other private site" not in content

    def test_duplicate_site_error_is_clear_and_does_not_create_a_second_row(
        self, auth_client, profile
    ):
        subscribe(profile)
        ProjectService.create(
            owner=profile, name="Existing", sitemap_url="https://example.com/sitemap.xml"
        )

        response = auth_client.post(
            reverse("home"),
            {"name": "Duplicate", "sitemap_url": "https://EXAMPLE.com/other.xml"},
        )

        assert response.status_code == 400
        assert "already belongs to a CiteGuild project" in response.content.decode()
        assert Project.objects.count() == 1

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
