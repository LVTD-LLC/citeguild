from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from qdrant_client import QdrantClient, models
from redis import Redis

from apps.core.article_ingestion import ArticleIngestionService
from apps.core.choices import ProjectSyncStates
from apps.core.models import DetectedNetworkLink, PageCrawlWork
from apps.core.network_graph import DetectedNetworkLinkService
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseResult,
)
from apps.core.sitemap_submission import SitemapSubmissionService
from apps.core.tests.test_article_embeddings import FakeEmbeddingClient
from apps.core.tests.test_article_ingestion import extraction_for
from apps.core.tests.test_sitemap_submission import RecordingFetchClient, fetch_result
from apps.search.qdrant import ensure_article_collection, upsert_article
from apps.search.service import SearchService
from apps.search.tests.test_qdrant import add_embedding

pytestmark = [
    pytest.mark.acceptance,
    pytest.mark.skipif(
        os.environ.get("CITEGUILD_RUN_ACCEPTANCE") != "1",
        reason="requires the dedicated PostgreSQL, Redis, and Qdrant services",
    ),
]

SEARCH_SMOKE_BUDGET_SECONDS = 2.0
REPRESENTATIVE_POINT_COUNT = 250


@pytest.fixture
def qdrant_client(settings):
    settings.QDRANT_COLLECTION = f"cg030-acceptance-{uuid4().hex}"
    client = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )
    ensure_article_collection(client=client)
    try:
        yield client
    finally:
        client.delete_collection(settings.QDRANT_COLLECTION)
        client.close()


def _paid_profile(username: str):
    user = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="acceptance-only-password",
    )
    profile = user.profile
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    return profile


def _submit_site(profile, host: str):
    return SitemapSubmissionService.submit(
        owner=profile,
        name=host,
        sitemap_url=f"https://{host}/sitemap.xml",
        client=RecordingFetchClient(fetch_result(b"<urlset />")),
    ).project


def _crawl_article(project, url: str, *, links=()):
    sync = project.sync_requests.get()
    sync.state = ProjectSyncStates.RUNNING
    sync.save(update_fields=["state", "updated_at"])
    inventory = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=SitemapParseResult(
            (ParsedCandidate(url, url),),
            SitemapDiagnostics(1, 1, 1, 0, 0, 0, 0),
        ),
    )
    work = PageCrawlWork.objects.create(
        sync_request=sync,
        candidate=inventory.candidates.get(),
    )
    extraction_for(
        work,
        text=f"Useful editorial source for {url}",
        links=links,
    )
    return ArticleIngestionService.ingest(work=work, queue_embedding=False)


def _add_decoy_points(client: QdrantClient) -> None:
    project_uuid = uuid4()
    points = [
        models.PointStruct(
            id=str(uuid4()),
            vector=[0.0, 1.0, 0.0],
            payload={
                "active": True,
                "article_uuid": str(uuid4()),
                "project_uuid": str(project_uuid),
                "site_host": "decoy.example",
                "language": "en",
                "content_hash": "d" * 64,
                "embedding_model": settings.EMBEDDING_MODEL,
            },
        )
        for _ in range(REPRESENTATIVE_POINT_COUNT)
    ]
    client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=points,
        wait=True,
    )


@pytest.mark.django_db(transaction=True)
def test_paid_sites_become_searchable_and_form_a_detected_link(qdrant_client):
    target_owner = _paid_profile("acceptance-target")
    source_owner = _paid_profile("acceptance-source")
    target_project = _submit_site(target_owner, "target.acceptance.example")
    source_project = _submit_site(source_owner, "source.acceptance.example")

    target = _crawl_article(
        target_project,
        "https://target.acceptance.example/guide",
    )
    add_embedding(target)
    upsert_article(article=target, client=qdrant_client)

    source = _crawl_article(
        source_project,
        "https://source.acceptance.example/post",
        links=({"url": target.normalized_canonical_url, "anchor_text": "Useful guide"},),
    )
    add_embedding(source)
    upsert_article(article=source, client=qdrant_client)
    DetectedNetworkLinkService.reconcile_article(source)
    _add_decoy_points(qdrant_client)

    started_at = time.perf_counter()
    response = SearchService(
        embedding_client=FakeEmbeddingClient(vectors=[[1.0, 0.0, 0.0]]),
        qdrant_client=qdrant_client,
    ).search(profile=target_owner, query="editorial source", limit=10, transport="acceptance")
    elapsed = time.perf_counter() - started_at

    assert target.uuid in {result.article_id for result in response.results}
    assert DetectedNetworkLink.objects.filter(
        source_article=source,
        target_article=target,
        is_active=True,
    ).exists()
    assert qdrant_client.get_collection(settings.QDRANT_COLLECTION).points_count == (
        REPRESENTATIVE_POINT_COUNT + 2
    )
    assert elapsed < SEARCH_SMOKE_BUDGET_SECONDS


def test_configured_redis_round_trip_is_namespaced_and_ephemeral():
    client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    key = f"cg030:acceptance:{uuid4().hex}"
    try:
        assert client.set(key, "ok", ex=30, nx=True) is True
        assert client.get(key) == "ok"
    finally:
        client.delete(key)
        client.close()
