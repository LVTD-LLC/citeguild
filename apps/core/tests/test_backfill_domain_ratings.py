from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.core.domain_ratings import DOMAIN_RATING_REFRESH_UPDATED, DomainRatingError
from apps.core.projects import ProjectService


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])


def create_project(profile, host):
    return ProjectService.create(
        owner=profile,
        name=host,
        sitemap_url=f"https://{host}/sitemap.xml",
    )


@pytest.mark.django_db
def test_backfill_processes_only_sites_missing_domain_rating(profile, settings, monkeypatch):
    settings.AHREFS_API_KEY = "test-key"
    subscribe(profile)
    first = create_project(profile, "first.example")
    rated = create_project(profile, "rated.example")
    second = create_project(profile, "second.example")
    rated.ahrefs_domain_rating = Decimal("31.0")
    rated.ahrefs_domain_rating_updated_at = timezone.now()
    rated.save(
        update_fields=[
            "ahrefs_domain_rating",
            "ahrefs_domain_rating_updated_at",
            "updated_at",
        ]
    )
    refreshed = []
    sleeps = []
    monkeypatch.setattr(
        "apps.core.management.commands.backfill_domain_ratings.refresh_project_domain_rating",
        lambda project_id: refreshed.append(project_id) or DOMAIN_RATING_REFRESH_UPDATED,
    )
    monkeypatch.setattr(
        "apps.core.management.commands.backfill_domain_ratings.time.sleep",
        sleeps.append,
    )
    stdout = StringIO()

    call_command("backfill_domain_ratings", stdout=stdout)

    assert refreshed == [first.pk, second.pk]
    assert sleeps == [1.0]
    assert "selected=2, updated=2, failed=0" in stdout.getvalue()


@pytest.mark.django_db
def test_backfill_limit_bounds_the_snapshot(profile, settings, monkeypatch):
    settings.AHREFS_API_KEY = "test-key"
    subscribe(profile)
    first = create_project(profile, "first-limit.example")
    create_project(profile, "second-limit.example")
    refreshed = []
    monkeypatch.setattr(
        "apps.core.management.commands.backfill_domain_ratings.refresh_project_domain_rating",
        lambda project_id: refreshed.append(project_id) or DOMAIN_RATING_REFRESH_UPDATED,
    )

    call_command("backfill_domain_ratings", limit=1, stdout=StringIO())

    assert refreshed == [first.pk]


@pytest.mark.django_db
def test_backfill_finishes_snapshot_then_reports_failures(profile, settings, monkeypatch):
    settings.AHREFS_API_KEY = "test-key"
    subscribe(profile)
    first = create_project(profile, "failed.example")
    second = create_project(profile, "retryable.example")
    attempted = []

    def refresh(project_id):
        attempted.append(project_id)
        if project_id == first.pk:
            return "failed:provider_authentication_failed"
        raise DomainRatingError("provider_rate_limited", retryable=True)

    monkeypatch.setattr(
        "apps.core.management.commands.backfill_domain_ratings.refresh_project_domain_rating",
        refresh,
    )
    monkeypatch.setattr(
        "apps.core.management.commands.backfill_domain_ratings.time.sleep",
        lambda seconds: None,
    )

    with pytest.raises(CommandError, match="selected=2, updated=0, failed=2"):
        call_command("backfill_domain_ratings", stdout=StringIO())

    assert attempted == [first.pk, second.pk]


def test_backfill_requires_ahrefs_key(settings):
    settings.AHREFS_API_KEY = ""

    with pytest.raises(CommandError, match="AHREFS_API_KEY is required"):
        call_command("backfill_domain_ratings", stdout=StringIO())


@pytest.mark.parametrize("limit", (0, -1))
def test_backfill_rejects_non_positive_limit(settings, limit):
    settings.AHREFS_API_KEY = "test-key"

    with pytest.raises(CommandError, match="--limit must be a positive integer"):
        call_command("backfill_domain_ratings", limit=limit, stdout=StringIO())
