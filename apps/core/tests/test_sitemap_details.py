from unittest.mock import patch

import pytest
from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.models import DetectedNetworkLink, OutboundLinkObservation, Project
from apps.core.network_graph import DetectedNetworkLinkService
from apps.core.projects import ProjectService

from .test_network_graph import (
    create_article,
    create_articles_for_project,
    create_other_profile,
)


def subscribe(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])


def test_link_pagination_renders_valid_multi_parameter_query_string():
    page = Paginator(range(21), 20).get_page(1)

    content = render_to_string(
        "components/link_pagination.html",
        {
            "page": page,
            "parameter": "given_page",
            "other_parameter": "received_page",
            "other_page": 3,
            "label": "given links",
        },
    )

    assert "?given_page=2&amp;received_page=3#given_page" in content
    assert "&amp;amp;" not in content


@pytest.mark.django_db
def test_sitemap_details_shows_owned_site_and_cross_site_link_details(auth_client, profile):
    owned_target = create_article(profile, "owned-target.example", "guide")
    other_profile = create_other_profile("details-network-member")
    other_source = create_article(
        other_profile,
        "other-source.example",
        "post",
        links=(
            {
                "url": owned_target.normalized_canonical_url,
                "anchor_text": "A useful target",
            },
        ),
    )
    DetectedNetworkLinkService.reconcile_article(other_source)

    other_target = create_article(other_profile, "other-target.example", "reference")
    owned_source = create_article(
        profile,
        "owned-source.example",
        "article",
        links=(
            {
                "url": other_target.normalized_canonical_url,
                "anchor_text": "A useful reference",
            },
        ),
    )
    DetectedNetworkLinkService.reconcile_article(owned_source)

    response = auth_client.get(reverse("sitemap_details", args=[owned_target.project.uuid]))
    content = response.content.decode()

    assert response.status_code == 200
    assert "pages/sitemap_details.html" in [template.name for template in response.templates]
    assert owned_target.project.name in content
    assert owned_target.project.normalized_sitemap_url in content
    assert "Links received" in content
    assert "A useful target" in content
    assert other_source.normalized_canonical_url in content
    assert "other-source.example" in content
    assert response.context["details"].links_received.paginator.per_page == 20

    response = auth_client.get(reverse("sitemap_details", args=[owned_source.project.uuid]))
    content = response.content.decode()

    assert "Links given" in content
    assert "A useful reference" in content
    assert other_target.normalized_canonical_url in content
    assert "other-target.example" in content
    assert response.context["details"].links_given.paginator.per_page == 20


@pytest.mark.django_db
def test_sitemap_details_excludes_preserved_same_site_edges(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Legacy self links",
        sitemap_url="https://legacy-details.example/sitemap.xml",
    )
    target, source = create_articles_for_project(
        project,
        ("about", ()),
        (
            "post",
            ({"url": "https://legacy-details.example/about", "anchor_text": "Self only"},),
        ),
    )
    observation = OutboundLinkObservation.objects.get(source_article=source)
    DetectedNetworkLink.objects.create(
        observation=observation,
        source_article=source,
        target_project=project,
        target_article=target,
        normalized_destination_url=target.normalized_canonical_url,
        anchor_text="Self only",
        first_detected_at=observation.first_seen_at,
        last_detected_at=observation.last_seen_at,
    )

    response = auth_client.get(reverse("sitemap_details", args=[project.uuid]))
    content = response.content.decode()

    assert response.status_code == 200
    assert "Self only" not in content
    assert response.context["details"].links_given.paginator.count == 0
    assert response.context["details"].links_received.paginator.count == 0


@pytest.mark.django_db
def test_sitemap_details_is_owner_scoped(auth_client, profile):
    other_profile = create_other_profile("private-details-owner")
    project = create_article(other_profile, "private-details.example", "post").project

    response = auth_client.get(reverse("sitemap_details", args=[project.uuid]))

    assert response.status_code == 404
    assert "private-details.example" not in response.content.decode()


@pytest.mark.django_db
def test_dashboard_links_each_site_to_sitemap_details(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Dashboard details",
        sitemap_url="https://dashboard-details.example/sitemap.xml",
    )

    content = auth_client.get(reverse("home")).content.decode()

    assert reverse("sitemap_details", args=[project.uuid]) in content
    assert "View details" in content


@pytest.mark.django_db
def test_owner_can_update_sitemap_name_and_url_from_details(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Before",
        sitemap_url="https://before-details.example/sitemap.xml",
    )

    response = auth_client.post(
        reverse("update_sitemap", args=[project.uuid]),
        {
            "name": "After",
            "sitemap_url": "https://AFTER-details.example:443/news-sitemap.xml#ignored",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("sitemap_details", args=[project.uuid])
    project.refresh_from_db()
    assert project.name == "After"
    assert project.sitemap_url == "https://AFTER-details.example:443/news-sitemap.xml#ignored"
    assert project.normalized_sitemap_url == "https://after-details.example/news-sitemap.xml"


@pytest.mark.django_db
def test_invalid_sitemap_update_renders_details_without_changing_project(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Keep me",
        sitemap_url="https://keep-details.example/sitemap.xml",
    )

    response = auth_client.post(
        reverse("update_sitemap", args=[project.uuid]),
        {"name": "", "sitemap_url": "not-a-url"},
    )

    assert response.status_code == 400
    assert "This field is required" in response.content.decode()
    project.refresh_from_db()
    assert project.name == "Keep me"
    assert project.normalized_sitemap_url == "https://keep-details.example/sitemap.xml"


@pytest.mark.django_db
def test_delete_sitemap_requires_exact_name_confirmation(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Delete carefully",
        sitemap_url="https://delete-carefully.example/sitemap.xml",
    )

    response = auth_client.post(
        reverse("delete_sitemap", args=[project.uuid]),
        {"confirmation": "wrong"},
    )

    assert response.status_code == 400
    assert "Enter the site name exactly" in response.content.decode()
    assert Project.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
def test_delete_sitemap_requires_an_active_subscription(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Keep after cancellation",
        sitemap_url="https://keep-after-cancellation.example/sitemap.xml",
    )
    profile.stripe_subscription_status = "canceled"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])

    response = auth_client.post(
        reverse("delete_sitemap", args=[project.uuid]),
        {"confirmation": project.name},
    )

    assert response.status_code == 403
    assert "active subscription is required" in response.content.decode()
    assert Project.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_owner_can_delete_sitemap_and_queue_vector_cleanup(auth_client, profile):
    subscribe(profile)
    project = ProjectService.create(
        owner=profile,
        name="Delete me",
        sitemap_url="https://delete-me.example/sitemap.xml",
    )
    project_uuid = project.uuid

    with patch("apps.search.qdrant.queue_project_deletion") as queue_cleanup:
        response = auth_client.post(
            reverse("delete_sitemap", args=[project_uuid]),
            {"confirmation": "Delete me"},
        )

    assert response.status_code == 302
    assert response.url == reverse("home")
    assert not Project.objects.filter(uuid=project_uuid).exists()
    queue_cleanup.assert_called_once_with(project_uuid)


@pytest.mark.django_db
def test_user_cannot_update_or_delete_another_accounts_sitemap(auth_client, profile):
    other_profile = create_other_profile("private-site-manager")
    project = create_article(other_profile, "private-manager.example", "post").project

    update_response = auth_client.post(
        reverse("update_sitemap", args=[project.uuid]),
        {"name": "Taken", "sitemap_url": "https://taken.example/sitemap.xml"},
    )
    delete_response = auth_client.post(
        reverse("delete_sitemap", args=[project.uuid]),
        {"confirmation": project.name},
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    project.refresh_from_db()
    assert project.normalized_host == "private-manager.example"
