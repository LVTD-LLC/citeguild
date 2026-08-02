from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.choices import ProjectSyncStates
from apps.core.dashboard import DashboardService
from apps.core.models import DetectedNetworkLink, ProjectSyncRequest
from apps.core.network_graph import DetectedNetworkLinkService
from apps.core.projects import ProjectService

from .test_network_graph import create_article
from .test_views import subscribe


def other_profile(name="dashboard-other"):
    user = get_user_model().objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password="password123",
    )
    subscribe(user.profile)
    return user.profile


def create_failed_sync(project):
    completed_at = timezone.now()
    return ProjectSyncRequest.objects.create(
        project=project,
        state=ProjectSyncStates.PARTIAL,
        sitemap_kind="urlset",
        idempotency_key=f"dashboard:{project.uuid}",
        error_code="page_failures",
        total_count=5,
        queued_count=0,
        succeeded_count=2,
        failed_count=1,
        started_at=completed_at - timedelta(minutes=2),
        completed_at=completed_at,
    )


@pytest.mark.django_db
def test_dashboard_service_is_owner_scoped_bounded_and_reconciles_counts(profile):
    subscribe(profile)
    target = create_article(profile, "dashboard-target.example", "guide")
    source = create_article(
        profile,
        "dashboard-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Guide"},),
    )
    DetectedNetworkLinkService.reconcile_article(source)
    historical = DetectedNetworkLink.objects.get(source_article=source)
    historical.is_active = False
    historical.save(update_fields=["is_active", "updated_at"])
    create_failed_sync(source.project)
    outsider = other_profile()
    create_article(outsider, "private-other.example", "private")

    with CaptureQueriesContext(connection) as queries:
        dashboard = DashboardService.for_owner(
            profile,
            site_page="invalid",
            given_page=1,
            received_page=1,
        )
        project_names = [project.name for project in dashboard.projects]
        given = list(dashboard.links_given)
        received = list(dashboard.links_received)

    assert len(queries) <= 12
    assert "private-other.example" not in project_names
    assert dashboard.summary.site_count == 2
    assert dashboard.summary.indexed_article_count == 2
    assert dashboard.summary.detected_links_given == len(given) == 1
    assert dashboard.summary.detected_links_received == len(received) == 1
    assert given[0].is_active is False
    assert received[0].is_active is False
    source_card = next(project for project in dashboard.projects if project.pk == source.project_id)
    assert source_card.latest_sync_state == ProjectSyncStates.PARTIAL
    assert source_card.latest_sync_total_count == 5
    assert source_card.latest_sync_succeeded_count == 2
    assert source_card.latest_sync_failed_count == 1
    assert source_card.latest_sync_pending_count == 2
    assert source_card.latest_sync_error_code == "page_failures"


@pytest.mark.django_db
def test_dashboard_link_pagination_is_bounded_and_stable(profile):
    subscribe(profile)
    target = create_article(profile, "page-target.example", "guide")
    for number in range(12):
        member = other_profile(f"page-source-{number}")
        source = create_article(
            member,
            f"page-source-{number}.example",
            "post",
            links=(
                {
                    "url": target.normalized_canonical_url,
                    "anchor_text": f"Source {number}",
                },
            ),
        )
        DetectedNetworkLinkService.reconcile_article(source)

    first = DashboardService.for_owner(profile, received_page=1)
    second = DashboardService.for_owner(profile, received_page=2)

    assert first.links_received.paginator.count == 12
    assert len(first.links_received.object_list) == DashboardService.LINK_PAGE_SIZE
    assert len(second.links_received.object_list) == 2
    assert set(first.links_received.object_list).isdisjoint(second.links_received.object_list)


@pytest.mark.django_db
def test_dashboard_renders_safe_activity_progress_and_empty_states(auth_client, profile):
    subscribe(profile)
    target = create_article(profile, "render-target.example", "guide")
    source = create_article(
        profile,
        "render-source.example",
        "post",
        links=(
            {
                "url": target.normalized_canonical_url,
                "anchor_text": '<script>alert("crawl")</script>',
            },
        ),
    )
    DetectedNetworkLinkService.reconcile_article(source)
    edge = DetectedNetworkLink.objects.get(source_article=source)
    assert edge.anchor_text.startswith("<script>")
    create_failed_sync(source.project)

    response = auth_client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert source.project.normalized_sitemap_url in content
    assert "2 succeeded" in content
    assert "2 pending" in content
    assert "1 failed" in content
    assert "Detected links given" in content
    assert "Detected links received" in content
    assert "Detected, not attributed" in content
    assert '<script>alert("crawl")</script>' not in content
    assert "&lt;script&gt;alert" in content
    assert 'aria-label="Detected links given pagination"' in content
    assert 'aria-label="Detected links received pagination"' in content


@pytest.mark.django_db
def test_dashboard_does_not_render_other_account_private_site_name(auth_client, profile):
    subscribe(profile)
    target = create_article(profile, "owned-public.example", "guide")
    outsider = other_profile("dashboard-private-owner")
    source = create_article(
        outsider,
        "public-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Public source"},),
    )
    source.project.name = "PRIVATE ACCOUNT LABEL"
    source.project.save(update_fields=["name", "updated_at"])
    DetectedNetworkLinkService.reconcile_article(source)

    content = auth_client.get(reverse("home")).content.decode()

    assert "PRIVATE ACCOUNT LABEL" not in content
    assert source.project.normalized_host in content
    assert source.normalized_canonical_url in content


@pytest.mark.django_db
def test_dashboard_empty_activity_has_clear_non_marketplace_copy(auth_client, profile):
    subscribe(profile)
    ProjectService.create(
        owner=profile,
        name="Empty activity",
        sitemap_url="https://empty-activity.example/sitemap.xml",
    )

    content = auth_client.get(reverse("home")).content.decode()

    assert "No detected links given yet" in content
    assert "No detected links received yet" in content
    assert "CiteGuild does not guarantee placements" in content
