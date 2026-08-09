from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
from django.utils import timezone

from apps.core.domain_ratings import (
    AHREFS_DOMAIN_RATING_URL,
    AhrefsDomainRatingClient,
    DomainRatingError,
    refresh_due_project_domain_ratings,
    refresh_project_domain_rating,
)
from apps.core.projects import ProjectService


class FakeFetcher:
    def __init__(self, ratings=None, error=None):
        self.ratings = ratings or {}
        self.error = error
        self.targets = []

    def fetch(self, target):
        self.targets.append(target)
        if self.error:
            raise self.error
        return self.ratings.get(target, Decimal("42.0"))


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])


def create_project(profile, host):
    return ProjectService.create(
        owner=profile,
        name=host,
        sitemap_url=f"https://{host}/sitemap.xml",
    )


def test_ahrefs_client_uses_fixed_endpoint_bearer_auth_and_normalizes_rating():
    def handler(request):
        assert str(request.url).startswith(AHREFS_DOMAIN_RATING_URL)
        assert request.url.params["target"] == "example.com"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"domain_rating": {"domain_rating": 42.26}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        rating = AhrefsDomainRatingClient(
            api_key="test-key",
            client=client,
        ).fetch("example.com")

    assert rating == Decimal("42.3")


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    (
        (401, "provider_authentication_failed", False),
        (429, "provider_rate_limited", True),
        (503, "provider_unavailable", True),
    ),
)
def test_ahrefs_client_classifies_failures_without_using_response_content(
    status_code, code, retryable
):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, text="sensitive provider response")
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(DomainRatingError) as raised:
            AhrefsDomainRatingClient(api_key="test-key", client=client).fetch("example.com")

    assert raised.value.code == code
    assert raised.value.retryable is retryable
    assert "sensitive provider response" not in str(raised.value)


@pytest.mark.django_db
def test_refresh_persists_last_successful_rating_and_timestamp(profile):
    subscribe(profile)
    project = create_project(profile, "rating.example")
    before = timezone.now()

    result = refresh_project_domain_rating(
        project.pk,
        fetcher=FakeFetcher({"rating.example": Decimal("17.4")}),
    )

    project.refresh_from_db()
    assert result == "updated"
    assert project.ahrefs_domain_rating == Decimal("17.4")
    assert project.ahrefs_domain_rating_updated_at >= before


@pytest.mark.django_db
def test_retryable_failure_preserves_last_successful_rating(profile):
    subscribe(profile)
    project = create_project(profile, "preserve.example")
    previous_time = timezone.now() - timedelta(days=31)
    project.ahrefs_domain_rating = Decimal("28.0")
    project.ahrefs_domain_rating_updated_at = previous_time
    project.save(
        update_fields=[
            "ahrefs_domain_rating",
            "ahrefs_domain_rating_updated_at",
            "updated_at",
        ]
    )

    with pytest.raises(DomainRatingError):
        refresh_project_domain_rating(
            project.pk,
            fetcher=FakeFetcher(error=DomainRatingError("provider_rate_limited", retryable=True)),
        )

    project.refresh_from_db()
    assert project.ahrefs_domain_rating == Decimal("28.0")
    assert project.ahrefs_domain_rating_updated_at == previous_time


@pytest.mark.django_db
def test_daily_sweep_refreshes_missing_and_month_old_values_only(profile, settings):
    settings.AHREFS_API_KEY = "test-key"
    subscribe(profile)
    missing = create_project(profile, "missing.example")
    stale = create_project(profile, "stale.example")
    recent = create_project(profile, "recent.example")
    now = timezone.now()
    stale.ahrefs_domain_rating = Decimal("10.0")
    stale.ahrefs_domain_rating_updated_at = now - timedelta(days=30)
    stale.save()
    recent.ahrefs_domain_rating = Decimal("20.0")
    recent.ahrefs_domain_rating_updated_at = now - timedelta(days=29)
    recent.save()
    fetcher = FakeFetcher(
        {
            "missing.example": Decimal("11.0"),
            "stale.example": Decimal("12.0"),
        }
    )
    sleeps = []

    result = refresh_due_project_domain_ratings(
        now=now,
        fetcher=fetcher,
        sleep=sleeps.append,
    )

    assert result == {"due_projects": 2, "updated_projects": 2, "failed_projects": 0}
    assert fetcher.targets == ["missing.example", "stale.example"]
    assert sleeps == [1.0]
    missing.refresh_from_db()
    stale.refresh_from_db()
    recent.refresh_from_db()
    assert missing.ahrefs_domain_rating == Decimal("11.0")
    assert stale.ahrefs_domain_rating == Decimal("12.0")
    assert recent.ahrefs_domain_rating == Decimal("20.0")


@pytest.mark.django_db(transaction=True)
def test_new_project_queues_rating_refresh_after_commit(profile, monkeypatch, settings):
    settings.AHREFS_API_KEY = "test-key"
    subscribe(profile)
    queued = []
    monkeypatch.setattr(
        "apps.core.domain_ratings.queue_project_domain_rating_refresh",
        lambda project_id: queued.append(project_id),
    )

    project = create_project(profile, "new-site.example")

    assert queued == [project.pk]


@pytest.mark.django_db
def test_host_change_clears_stale_rating(profile):
    subscribe(profile)
    project = create_project(profile, "before-rating.example")
    project.ahrefs_domain_rating = Decimal("31.0")
    project.ahrefs_domain_rating_updated_at = timezone.now()
    project.save()

    updated = ProjectService.update(
        owner=profile,
        project_uuid=project.uuid,
        name=project.name,
        sitemap_url="https://after-rating.example/sitemap.xml",
    )

    assert updated.ahrefs_domain_rating is None
    assert updated.ahrefs_domain_rating_updated_at is None
