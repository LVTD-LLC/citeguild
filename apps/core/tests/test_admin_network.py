from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.admin_network import AdminNetworkOverviewService
from apps.core.models import DetectedNetworkLink, OutboundLinkObservation
from apps.core.network_graph import DetectedNetworkLinkService

from .test_network_graph import create_article, create_articles_for_project, create_project


@pytest.mark.django_db
def test_admin_network_overview_aggregates_active_cross_site_links(profile):
    target = create_article(profile, "target-overview.example", "guide")
    source = create_article(
        profile,
        "source-overview.example",
        "post",
        links=(
            {"url": target.normalized_canonical_url, "anchor_text": "Guide"},
            {"url": "https://target-overview.example/about", "anchor_text": "About"},
        ),
    )
    DetectedNetworkLinkService.reconcile_article(source)

    overview = AdminNetworkOverviewService.build("30")

    assert overview.period.key == "30"
    assert overview.citation_count == 2
    assert overview.connection_count == 1
    assert overview.connected_site_count == 2
    assert len(overview.nodes) == 2
    assert len(overview.edges) == 1
    assert overview.edges[0].citation_count == 2
    assert overview.edges[0].source_host == "source-overview.example"
    assert overview.edges[0].target_host == "target-overview.example"


@pytest.mark.django_db
def test_admin_network_overview_filters_old_inactive_and_same_site_links(profile):
    target = create_article(profile, "period-target.example", "guide")
    source = create_article(
        profile,
        "period-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Guide"},),
    )
    DetectedNetworkLinkService.reconcile_article(source)
    old_link = DetectedNetworkLink.objects.get()
    DetectedNetworkLink.objects.filter(pk=old_link.pk).update(
        last_detected_at=timezone.now() - timedelta(days=40)
    )

    inactive_target = create_article(profile, "inactive-target.example", "guide")
    inactive_source = create_article(
        profile,
        "inactive-source.example",
        "post",
        links=(
            {
                "url": inactive_target.normalized_canonical_url,
                "anchor_text": "Inactive guide",
            },
        ),
    )
    DetectedNetworkLinkService.reconcile_article(inactive_source)
    DetectedNetworkLink.objects.filter(source_article=inactive_source).update(is_active=False)

    self_project = create_project(profile, "legacy-admin-self.example")
    self_target, self_source = create_articles_for_project(
        self_project,
        ("about", ()),
        (
            "post",
            (
                {
                    "url": "https://legacy-admin-self.example/about",
                    "anchor_text": "Self",
                },
            ),
        ),
    )
    observation = OutboundLinkObservation.objects.get(source_article=self_source)
    DetectedNetworkLink.objects.create(
        observation=observation,
        source_article=self_source,
        target_project=self_project,
        target_article=self_target,
        normalized_destination_url=self_target.normalized_canonical_url,
        anchor_text="Self",
        first_detected_at=observation.first_seen_at,
        last_detected_at=observation.last_seen_at,
        is_active=True,
    )

    assert AdminNetworkOverviewService.build("30").citation_count == 0
    assert AdminNetworkOverviewService.build("all").citation_count == 1


@pytest.mark.django_db
def test_admin_panel_renders_network_period_and_requires_superuser(auth_client, user):
    response = auth_client.get(reverse("admin_panel"), {"period": "90"})
    assert response.status_code == 302

    user.is_superuser = True
    user.save(update_fields=["is_superuser"])
    response = auth_client.get(reverse("admin_panel"), {"period": "90"})
    content = response.content.decode()

    assert response.status_code == 200
    assert response.context["network_overview"].period.key == "90"
    assert "Network overview" in content
    assert 'aria-label="Network activity period"' in content
    assert "No active cross-site citations were detected in this period." in content


@pytest.mark.django_db
def test_admin_network_overview_falls_back_to_thirty_days_for_unknown_period():
    assert AdminNetworkOverviewService.build("unexpected").period.key == "30"


def test_admin_network_overview_separates_reciprocal_connections():
    connections = [
        {
            "source_article__project_id": 1,
            "source_article__project__normalized_host": "one.example",
            "target_project_id": 2,
            "target_project__normalized_host": "two.example",
            "citation_count": 3,
        },
        {
            "source_article__project_id": 2,
            "source_article__project__normalized_host": "two.example",
            "target_project_id": 1,
            "target_project__normalized_host": "one.example",
            "citation_count": 2,
        },
    ]

    _nodes, edges = AdminNetworkOverviewService._layout(connections)

    assert len(edges) == 2
    assert edges[0].path != edges[1].path
    assert (edges[0].label_x, edges[0].label_y) != (edges[1].label_x, edges[1].label_y)
