from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.core.article_ingestion import ArticleIngestionService
from apps.core.choices import ArticleStates
from apps.core.models import DetectedNetworkLink, OutboundLinkObservation
from apps.core.network_graph import DetectedNetworkLinkQueries, DetectedNetworkLinkService
from apps.core.projects import ProjectService
from apps.search.tests.test_qdrant import add_embedding, article_client

from .test_article_ingestion import create_project, create_sync, extraction_for


def create_article(profile, host, path, *, links=()):
    project = create_project(profile, host)
    _sync, [work] = create_sync(project, f"sync-{host}-{path}", f"https://{host}/{path}")
    extraction_for(work, links=links)
    article = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    article.state = ArticleStates.ACTIVE
    article.is_active = True
    article.save(update_fields=["state", "is_active", "updated_at"])
    return article


def create_other_profile(name):
    user = get_user_model().objects.create_user(
        username=name,
        email=f"{name}@example.com",
        password="password123",
    )
    return user.profile


@pytest.mark.django_db
def test_resolver_builds_known_cross_site_edges_and_ignores_external_links(profile, monkeypatch):
    tracked = []
    monkeypatch.setattr(
        "apps.core.network_graph.track_funnel_event",
        lambda *args, **kwargs: tracked.append((args, kwargs)),
    )
    target = create_article(profile, "target.example", "guide")
    other_profile = create_other_profile("network-source")
    source = create_article(
        other_profile,
        "source.example",
        "post",
        links=(
            {"url": target.normalized_canonical_url, "anchor_text": "Useful guide"},
            {"url": "https://external.example/reference", "anchor_text": "External"},
        ),
    )

    DetectedNetworkLinkService.reconcile_article(source)

    edge = DetectedNetworkLink.objects.get()
    assert edge.source_article == source
    assert edge.target_article == target
    assert edge.normalized_destination_url == target.normalized_canonical_url
    assert edge.anchor_text == "Useful guide"
    assert edge.is_active is True
    assert edge.detection_kind == "detected"
    assert not DetectedNetworkLink.objects.filter(
        normalized_destination_url="https://external.example/reference"
    ).exists()
    directions = [call[0][2]["direction"] for call in tracked]
    assert directions.count("given") == directions.count("received") == 2
    assert all(call[0][1] == "citeguild_citation_detected" for call in tracked)
    assert "source.example" not in repr(tracked)


@pytest.mark.django_db
def test_known_member_host_resolves_without_an_exact_article(profile):
    target_project = create_project(profile, "site-only.example")
    source = create_article(
        profile,
        "site-link-source.example",
        "post",
        links=({"url": "https://site-only.example/about", "anchor_text": "Member site"},),
    )

    DetectedNetworkLinkService.reconcile_article(source)

    edge = DetectedNetworkLink.objects.get()
    assert edge.target_project == target_project
    assert edge.target_article is None
    assert edge.is_active is True


@pytest.mark.django_db
def test_queries_are_account_scoped_and_aggregates_match_details(profile):
    target = create_article(profile, "owned-target.example", "guide")
    same_account_source = create_article(
        profile,
        "owned-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Same account"},),
    )
    other_profile = create_other_profile("external-member")
    cross_account_source = create_article(
        other_profile,
        "other-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Cross account"},),
    )
    DetectedNetworkLinkService.reconcile_article(same_account_source)
    DetectedNetworkLinkService.reconcile_article(cross_account_source)

    assert DetectedNetworkLinkQueries.links_given(profile).count() == 1
    assert DetectedNetworkLinkQueries.links_received(profile).count() == 2
    assert DetectedNetworkLinkQueries.links_given(other_profile).count() == 1
    assert DetectedNetworkLinkQueries.links_received(other_profile).count() == 0
    page = DetectedNetworkLinkQueries.most_cited_pages(profile).get(pk=target.pk)
    site = DetectedNetworkLinkQueries.most_cited_sites(profile).get(pk=target.project_id)
    assert page.detected_link_count == DetectedNetworkLinkQueries.links_received(profile).count()
    assert site.detected_link_count == DetectedNetworkLinkQueries.links_received(profile).count()


@pytest.mark.django_db
def test_target_ingestion_backfills_an_earlier_unresolved_observation(profile):
    destination = "https://late-target.example/guide"
    source = create_article(
        profile,
        "early-source.example",
        "post",
        links=({"url": destination, "anchor_text": "Later member"},),
    )
    assert not DetectedNetworkLink.objects.exists()

    target = create_article(profile, "late-target.example", "guide")
    DetectedNetworkLinkService.reconcile_article(target)

    edge = DetectedNetworkLink.objects.get()
    assert edge.source_article == source
    assert edge.target_article == target


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_removal_and_target_lifecycle_reconcile_without_losing_first_seen(profile):
    target = create_article(profile, "lifecycle-target.example", "guide")
    source = create_article(
        profile,
        "lifecycle-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Guide"},),
    )
    observation = OutboundLinkObservation.objects.get(source_article=source)
    DetectedNetworkLinkService.reconcile_observation(observation)
    edge = DetectedNetworkLink.objects.get()
    first_detected_at = edge.first_detected_at

    removed_at = timezone.now() + timedelta(minutes=1)
    observation.is_active = False
    observation.inactive_at = removed_at
    observation.save(update_fields=["is_active", "inactive_at", "updated_at"])
    DetectedNetworkLinkService.reconcile_observation(observation, now=removed_at)
    edge.refresh_from_db()
    assert edge.is_active is False
    assert edge.inactive_at == removed_at
    assert edge.first_detected_at == first_detected_at

    returned_at = removed_at + timedelta(minutes=1)
    observation.is_active = True
    observation.last_seen_at = returned_at
    observation.inactive_at = None
    observation.save(update_fields=["is_active", "last_seen_at", "inactive_at", "updated_at"])
    target.state = ArticleStates.INACTIVE
    target.is_active = False
    target.inactive_at = returned_at
    target.save(update_fields=["state", "is_active", "inactive_at", "updated_at"])
    DetectedNetworkLinkService.reconcile_article(target, now=returned_at)
    edge.refresh_from_db()
    assert edge.is_active is False

    target.state = ArticleStates.DISCOVERED
    target.is_active = False
    target.inactive_at = None
    target.save(update_fields=["state", "is_active", "inactive_at", "updated_at"])
    add_embedding(target)
    from apps.search.qdrant import upsert_article

    upsert_article(article=target, client=article_client())
    edge.refresh_from_db()
    assert edge.is_active is True
    assert edge.inactive_at is None
    assert edge.first_detected_at == first_detected_at
    assert edge.last_detected_at == returned_at


@pytest.mark.django_db
def test_historical_source_url_resolves_after_target_canonical_change(profile):
    target = create_article(profile, "canonical-target.example", "old")
    old_url = target.normalized_canonical_url
    target.normalized_canonical_url = "https://canonical-target.example/new"
    target.canonical_url = target.normalized_canonical_url
    target.final_url = target.normalized_canonical_url
    target.save(
        update_fields=[
            "normalized_canonical_url",
            "canonical_url",
            "final_url",
            "updated_at",
        ]
    )
    source = create_article(
        profile,
        "canonical-source.example",
        "post",
        links=({"url": old_url, "anchor_text": "Historical URL"},),
    )

    DetectedNetworkLinkService.reconcile_article(source)

    edge = DetectedNetworkLink.objects.get()
    assert edge.target_article == target
    assert edge.normalized_destination_url == old_url


@pytest.mark.django_db
def test_suspended_project_edges_are_historical_not_active(profile):
    target = create_article(profile, "suspended-target.example", "guide")
    source = create_article(
        profile,
        "suspended-source.example",
        "post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Guide"},),
    )
    DetectedNetworkLinkService.reconcile_article(source)

    ProjectService.suspend(
        owner=profile,
        project_uuid=target.project.uuid,
        reason="Operator review",
    )

    edge = DetectedNetworkLink.objects.get()
    assert edge.is_active is False
    assert DetectedNetworkLinkQueries.links_received(profile).count() == 0
    assert DetectedNetworkLinkQueries.links_received(profile, active_only=False).count() == 1

    ProjectService.reactivate(owner=profile, project_uuid=target.project.uuid)
    edge.refresh_from_db()
    assert edge.is_active is True
