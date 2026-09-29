from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.dashboard import DashboardService
from apps.core.metric_history import capture_daily_metrics, metric_history
from apps.core.models import ProjectMetricSnapshot

from .test_network_graph import create_article
from .test_views import subscribe


@pytest.mark.django_db
def test_snapshot_matches_dashboard_and_is_immutable_per_utc_day(profile):
    subscribe(profile)
    target = create_article(profile, "history-target.example", "guide")
    source = create_article(
        profile,
        "history-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Guide"},),
    )
    project = source.project
    project.ahrefs_domain_rating = Decimal("42.1")
    project.ahrefs_domain_rating_updated_at = timezone.now()
    project.save()
    now = timezone.now()
    assert capture_daily_metrics(now=now) == 2
    cards = DashboardService.for_owner(profile).projects.object_list
    for card in cards:
        snapshot = card.metric_snapshots.get()
        assert snapshot.indexed_pages == card.active_article_count
        assert snapshot.links_out == card.detected_links_given_count
        assert snapshot.domains_out == card.linked_domain_count
        assert snapshot.links_in == card.detected_links_received_count
        assert snapshot.domains_in == card.linking_domain_count
    assert project.metric_snapshots.get().domain_rating == Decimal("42.1")
    assert target.project.metric_snapshots.get().domain_rating is None
    project.active_article_count = 100
    project.save()
    assert capture_daily_metrics(now=now) == 0
    assert project.metric_snapshots.get().indexed_pages != 100
    assert capture_daily_metrics(now=now + timedelta(days=1)) == 2
    assert project.metric_snapshots.latest("date").indexed_pages == 100


@pytest.mark.django_db
def test_history_range_gaps_and_owner_scope(auth_client, profile):
    subscribe(profile)
    project = create_article(profile, "history.example", "guide").project
    today = timezone.now().date()
    for days, rating in [(100, 10), (2, 20), (0, None)]:
        ProjectMetricSnapshot.objects.create(
            project=project,
            date=today - timedelta(days=days),
            domain_rating=rating,
            indexed_pages=1,
            links_out=0,
            domains_out=0,
            links_in=0,
            domains_in=0,
        )
    history = metric_history(project, "30")
    assert len(history["rows"]) == 2
    assert len(history["charts"]) == 6
    assert "L" not in history["charts"][0]["path"]
    response = auth_client.get(reverse("sitemap_details", args=[project.uuid]))
    assert response.status_code == 200
    assert b"Metric history" in response.content
    assert b"Daily snapshots" in response.content
    from .test_dashboard import other_profile

    project.owner = other_profile("history-other")
    project.save()
    assert auth_client.get(reverse("sitemap_details", args=[project.uuid])).status_code == 404
