import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.core.choices import ProjectSyncStates
from apps.core.dashboard import DashboardService
from apps.core.models import DetectedNetworkLink, OutboundLinkObservation, ProjectSyncRequest
from apps.core.network_graph import DetectedNetworkLinkService
from apps.core.projects import ProjectService

from .test_network_graph import create_article, create_articles_for_project
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
    create_failed_sync(source.project)
    outsider = other_profile()
    create_article(outsider, "private-other.example", "private")

    with CaptureQueriesContext(connection) as queries:
        dashboard = DashboardService.for_owner(
            profile,
            site_page="invalid",
        )
        project_names = [project.name for project in dashboard.projects]

    assert len(queries) <= 7
    count_queries = [
        query["sql"] for query in queries if query["sql"].startswith("SELECT COUNT(*)")
    ]
    assert len(count_queries) == 1
    assert "JOIN" not in count_queries[0]
    assert "private-other.example" not in project_names
    assert dashboard.site_count == 2
    source_card = next(project for project in dashboard.projects if project.pk == source.project_id)
    target_card = next(project for project in dashboard.projects if project.pk == target.project_id)
    assert source_card.detected_links_given_count == 1
    assert source_card.detected_links_received_count == 0
    assert target_card.detected_links_given_count == 0
    assert target_card.detected_links_received_count == 1
    assert source_card.latest_sync_state == ProjectSyncStates.PARTIAL
    assert source_card.latest_sync_total_count == 5
    assert source_card.latest_sync_succeeded_count == 2
    assert source_card.latest_sync_failed_count == 1
    assert source_card.latest_sync_pending_count == 2
    assert source_card.latest_sync_error_code == "page_failures"


@pytest.mark.django_db
def test_dashboard_excludes_legacy_same_site_links_from_counts(profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Self link site",
        sitemap_url="https://dashboard-self-link.example/sitemap.xml",
    )
    target, source = create_articles_for_project(
        project,
        ("guide", ()),
        (
            "post",
            (
                {
                    "url": "https://dashboard-self-link.example/guide",
                    "anchor_text": "Self link",
                },
            ),
        ),
    )
    observation = OutboundLinkObservation.objects.get(source_article=source)
    DetectedNetworkLink.objects.create(
        observation=observation,
        source_article=source,
        target_project=target.project,
        target_article=target,
        normalized_destination_url=target.normalized_canonical_url,
        anchor_text="Self link",
        first_detected_at=observation.first_seen_at,
        last_detected_at=observation.last_seen_at,
        is_active=True,
    )

    dashboard = DashboardService.for_owner(profile)
    project = dashboard.projects[0]

    assert project.detected_links_given_count == 0
    assert project.detected_links_received_count == 0


@pytest.mark.django_db
def test_dashboard_groups_detected_links_by_site(profile):
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

    dashboard = DashboardService.for_owner(profile)
    target_card = next(project for project in dashboard.projects if project.pk == target.project_id)

    assert target_card.detected_links_given_count == 0
    assert target_card.detected_links_received_count == 12


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
    source.project.ahrefs_domain_rating = Decimal("37.0")
    source.project.ahrefs_domain_rating_updated_at = timezone.now()
    source.project.save()

    response = auth_client.get(reverse("home"))
    content = response.content.decode()

    assert response.status_code == 200
    assert source.project.normalized_sitemap_url in content
    assert "Searchable" in content
    assert "Needs attention" in content
    assert "Links from site" in content
    assert "Links to site" in content
    assert "Domain Rating" in content
    assert "Domain Rating by Ahrefs" in content
    assert re.search(r">\s*37\s*<", content)
    assert "Detected citations" not in content
    assert "Detected, not attributed" not in content
    assert '<script>alert("crawl")</script>' not in content


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
    assert target.project.normalized_host in content


@pytest.mark.django_db
def test_dashboard_empty_activity_has_clear_non_marketplace_copy(auth_client, profile):
    subscribe(profile)
    ProjectService.create(
        owner=profile,
        name="Empty activity",
        sitemap_url="https://empty-activity.example/sitemap.xml",
    )

    content = auth_client.get(reverse("home")).content.decode()

    assert "Links from site" in content
    assert "Links to site" in content
    assert "CiteGuild does not guarantee placements" not in content
