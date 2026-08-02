import pytest

from apps.core.models import Project, ProjectSyncRequest
from apps.core.sitemap_submission import (
    SitemapDocumentKind,
    SitemapSubmissionError,
    SitemapSubmissionErrorCode,
    SitemapValidation,
)


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])


@pytest.fixture
def valid_sitemap(monkeypatch):
    monkeypatch.setattr(
        "apps.core.sitemap_submission.validate_sitemap",
        lambda *args, **kwargs: SitemapValidation(SitemapDocumentKind.URL_SET),
    )


@pytest.mark.django_db
def test_project_api_validates_and_queues_one_initial_sync(client, profile, valid_sitemap):
    subscribe(profile)
    api_key = profile.rotate_api_key()

    response = client.post(
        "/api/projects",
        data={"name": "Example", "sitemap_url": "https://EXAMPLE.com/sitemap.xml"},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["normalized_host"] == "example.com"
    assert payload["sitemap_kind"] == "urlset"
    assert payload["sync_state"] == "queued"
    assert Project.objects.filter(owner=profile).count() == 1
    assert ProjectSyncRequest.objects.count() == 1


@pytest.mark.django_db
def test_project_api_requires_subscription_before_fetch(client, profile, monkeypatch):
    api_key = profile.rotate_api_key()
    fetch = pytest.fail
    monkeypatch.setattr("apps.core.sitemap_submission.validate_sitemap", fetch)

    response = client.post(
        "/api/projects",
        data={"name": "Blocked", "sitemap_url": "https://blocked.example/sitemap.xml"},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 403
    assert response.json() == {
        "code": "subscription_required",
        "message": "An active subscription is required to add a site.",
        "retryable": False,
    }


@pytest.mark.django_db
def test_project_api_returns_safe_retryable_fetch_error(client, profile, monkeypatch):
    subscribe(profile)
    api_key = profile.rotate_api_key()
    monkeypatch.setattr(
        "apps.core.sitemap_submission.validate_sitemap",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            SitemapSubmissionError(
                SitemapSubmissionErrorCode.TEMPORARY_FETCH,
                retryable=True,
            )
        ),
    )

    response = client.post(
        "/api/projects",
        data={
            "name": "Temporary",
            "sitemap_url": "https://temporary.example/?token=secret",
        },
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 503
    assert response.json()["code"] == "temporary_fetch"
    assert response.json()["retryable"] is True
    assert "secret" not in response.content.decode()
    assert not Project.objects.exists()
