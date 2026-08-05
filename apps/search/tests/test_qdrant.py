from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from qdrant_client import QdrantClient, models

from apps.core.choices import ArticleEmbeddingStates, ArticleStates
from apps.core.models import ArticleEmbedding
from apps.core.tests.test_article_embeddings import create_article


@pytest.fixture(autouse=True)
def clear_qdrant_client_cache():
    from apps.search.qdrant import get_qdrant_client

    get_qdrant_client.cache_clear()
    yield
    get_qdrant_client.cache_clear()


@override_settings(
    QDRANT_URL="http://qdrant:6333",
    QDRANT_API_KEY="test-api-key",
    QDRANT_TIMEOUT_SECONDS=7.5,
)
def test_get_qdrant_client_uses_configured_connection():
    from apps.search.qdrant import get_qdrant_client

    with patch("apps.search.qdrant.QdrantClient") as client_class:
        client = get_qdrant_client()

    assert client is client_class.return_value
    client_class.assert_called_once_with(
        url="http://qdrant:6333",
        api_key="test-api-key",
        timeout=7.5,
    )


@override_settings(QDRANT_URL="", QDRANT_API_KEY="test-api-key")
def test_get_qdrant_client_requires_url():
    from apps.search.qdrant import get_qdrant_client

    with pytest.raises(ImproperlyConfigured, match="QDRANT_URL"):
        get_qdrant_client()


@override_settings(QDRANT_URL="http://qdrant:6333", QDRANT_API_KEY="")
def test_get_qdrant_client_requires_api_key():
    from apps.search.qdrant import get_qdrant_client

    with pytest.raises(ImproperlyConfigured, match="QDRANT_API_KEY"):
        get_qdrant_client()


@override_settings(
    QDRANT_URL="http://qdrant:6333",
    QDRANT_API_KEY="test-api-key",
    QDRANT_TIMEOUT_SECONDS=5.0,
)
def test_get_qdrant_client_reuses_client():
    from apps.search.qdrant import get_qdrant_client

    with patch("apps.search.qdrant.QdrantClient") as client_class:
        first_client = get_qdrant_client()
        second_client = get_qdrant_client()

    assert first_client is second_client
    client_class.assert_called_once()


def memory_client():
    return QdrantClient(":memory:")


def add_embedding(article, *, dimensions=3):
    return ArticleEmbedding.objects.create(
        article=article,
        state=ArticleEmbeddingStates.SUCCEEDED,
        vector=[1.0] + [0.0] * (dimensions - 1),
        content_hash=article.content_hash,
        model="test:embedding-v1",
        dimensions=dimensions,
    )


def article_client():
    from apps.search.qdrant import ensure_article_collection

    client = memory_client()
    ensure_article_collection(client=client)
    return client


@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_collection_creation_is_idempotent_and_uses_cosine():
    from apps.search.qdrant import ensure_article_collection

    client = memory_client()

    assert ensure_article_collection(client=client) is True
    assert ensure_article_collection(client=client) is False
    vectors = client.get_collection("test-articles").config.params.vectors
    assert vectors.size == 3
    assert vectors.distance == models.Distance.COSINE


@override_settings(QDRANT_COLLECTION="test-articles", EMBEDDING_DIMENSIONS=3)
def test_existing_payload_indexes_are_not_recreated():
    from apps.search.qdrant import PAYLOAD_INDEXES, ensure_article_collection

    client = memory_client()
    client.create_collection(
        "test-articles",
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
    )
    collection_info = client.get_collection("test-articles")
    collection_info.payload_schema = {
        name: models.PayloadIndexInfo(data_type=schema, points=0)
        for name, schema in PAYLOAD_INDEXES.items()
    }
    with (
        patch.object(client, "get_collection", return_value=collection_info),
        patch.object(client, "create_payload_index") as create_payload_index,
    ):
        assert ensure_article_collection(client=client) is False

    create_payload_index.assert_not_called()


@override_settings(QDRANT_COLLECTION="test-articles", EMBEDDING_DIMENSIONS=3)
def test_incompatible_payload_index_fails_with_stable_error():
    from apps.search.qdrant import QdrantContractError, ensure_article_collection

    client = memory_client()
    client.create_collection(
        "test-articles",
        vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE),
    )
    collection_info = client.get_collection("test-articles")
    collection_info.payload_schema = {
        "active": models.PayloadIndexInfo(
            data_type=models.PayloadSchemaType.KEYWORD,
            points=0,
        )
    }
    with patch.object(client, "get_collection", return_value=collection_info):
        with pytest.raises(QdrantContractError) as raised:
            ensure_article_collection(client=client)

    assert raised.value.code == "payload_index_schema_mismatch"


@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_DIMENSIONS=3,
)
def test_incompatible_collection_dimensions_fail_with_stable_error():
    from apps.search.qdrant import QdrantContractError, ensure_article_collection

    client = memory_client()
    client.create_collection(
        "test-articles",
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )

    with pytest.raises(QdrantContractError) as raised:
        ensure_article_collection(client=client)

    assert raised.value.code == "collection_dimension_mismatch"


@override_settings(QDRANT_COLLECTION="test-articles", EMBEDDING_DIMENSIONS=3)
def test_collection_health_rejects_missing_or_incompatible_collection():
    from apps.search.qdrant import article_collection_healthy

    client = memory_client()
    assert article_collection_healthy(client=client) is False
    client.create_collection(
        "test-articles",
        vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE),
    )
    assert article_collection_healthy(client=client) is False


def test_index_and_deactivation_queues_are_gated_and_pass_only_durable_ids(settings, monkeypatch):
    from apps.search.qdrant import (
        queue_article_deactivation,
        queue_article_index,
        queue_project_deletion,
    )

    calls = []
    monkeypatch.setattr(
        "apps.search.qdrant.async_task",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "task-id",
    )
    article_uuid = "11111111-1111-1111-1111-111111111111"
    settings.CITEGUILD_INDEXING_ENABLED = False
    assert queue_article_index(article_uuid) is None
    assert queue_article_deactivation(article_uuid) is None
    assert queue_project_deletion(article_uuid) is None

    settings.CITEGUILD_INDEXING_ENABLED = True
    assert queue_article_index(article_uuid) == "task-id"
    assert queue_article_deactivation(article_uuid) == "task-id"
    assert queue_project_deletion(article_uuid) == "task-id"
    assert calls == [
        (
            ("apps.search.qdrant.index_article", article_uuid),
            {"group": f"article-index:{article_uuid}"},
        ),
        (
            ("apps.search.qdrant.remove_article_point", article_uuid),
            {"group": f"article-deactivate:{article_uuid}"},
        ),
        (
            ("apps.search.qdrant.delete_project_points", article_uuid),
            {"group": f"project-delete:{article_uuid}"},
        ),
    ]


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_delete_project_points_removes_only_matching_project(profile):
    from apps.core.article_ingestion import ArticleIngestionService
    from apps.core.tests.test_article_ingestion import create_project, create_sync, extraction_for
    from apps.search.qdrant import delete_project_points, upsert_article

    first = create_article(profile)
    second_project = create_project(profile, "keep-vector.example")
    _sync, [work] = create_sync(
        second_project,
        "keep-vector",
        "https://keep-vector.example/post",
    )
    extraction_for(work)
    second = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    add_embedding(first)
    add_embedding(second)
    client = article_client()
    upsert_article(article=first, client=client)
    upsert_article(article=second, client=client)

    assert delete_project_points(str(first.project.uuid), client=client) == str(first.project.uuid)

    assert client.retrieve("test-articles", ids=[str(first.qdrant_point_id)]) == []
    assert len(client.retrieve("test-articles", ids=[str(second.qdrant_point_id)])) == 1


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_upsert_uses_stable_point_payload_and_activates_article(profile):
    from apps.search.qdrant import upsert_article

    article = create_article(profile)
    add_embedding(article)
    client = article_client()

    upsert_article(article=article, client=client)

    article.refresh_from_db()
    article.project.refresh_from_db()
    point = client.retrieve("test-articles", ids=[str(article.qdrant_point_id)], with_payload=True)[
        0
    ]
    assert article.state == ArticleStates.ACTIVE
    assert article.is_active is True
    assert article.project.active_article_count == 1
    assert point.id == str(article.qdrant_point_id)
    assert point.payload["article_uuid"] == str(article.uuid)
    assert point.payload["project_uuid"] == str(article.project.uuid)
    assert point.payload["active"] is True
    assert "canonical_url" not in point.payload
    assert "title" not in point.payload
    assert "content" not in point.payload


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_search_requires_authorized_scope_and_applies_filters(profile):
    from apps.search.qdrant import QdrantContractError, semantic_search, upsert_article

    article = create_article(profile)
    add_embedding(article)
    client = article_client()
    upsert_article(article=article, client=client)

    with pytest.raises(QdrantContractError) as raised:
        semantic_search([1.0, 0.0, 0.0], authorized_project_uuids=set(), client=client)
    assert raised.value.code == "authorized_project_scope_required"

    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={article.project.uuid},
            language="en",
            site_host="example.com",
            limit=500,
            client=client,
        )[0].article_uuid
        == article.uuid
    )
    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={article.project.uuid},
            language="de",
            client=client,
        )
        == []
    )

    # Qdrant's point may lag behind billing and article changes. PostgreSQL is
    # authoritative even when the caller's project scope is stale.
    profile.stripe_subscription_status = "canceled"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={article.project.uuid},
            client=client,
        )
        == []
    )

    # Lifecycle changes are enforced from PostgreSQL even before an
    # asynchronous Qdrant deletion has removed the stale active point.
    article.content_hash = article.embedding.content_hash
    article.state = ArticleStates.INACTIVE
    article.is_active = False
    article.inactivity_reason = "sitemap_removed"
    article.save(
        update_fields=[
            "content_hash",
            "state",
            "is_active",
            "inactivity_reason",
            "updated_at",
        ]
    )
    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={article.project.uuid},
            client=client,
        )
        == []
    )

    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    article.content_hash = "0" * 64
    article.save(update_fields=["content_hash", "updated_at"])
    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={article.project.uuid},
            client=client,
        )
        == []
    )


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_deactivate_removes_point_and_updates_authoritative_state(profile):
    from apps.search.qdrant import deactivate_article, upsert_article

    article = create_article(profile)
    add_embedding(article)
    client = article_client()
    upsert_article(article=article, client=client)

    deactivate_article(article=article, client=client)

    article.refresh_from_db()
    article.project.refresh_from_db()
    assert article.state == ArticleStates.INACTIVE
    assert article.is_active is False
    assert article.project.active_article_count == 0
    assert client.retrieve("test-articles", ids=[str(article.qdrant_point_id)]) == []


@pytest.mark.django_db
@override_settings(
    QDRANT_COLLECTION="test-articles",
    EMBEDDING_MODEL="test:embedding-v1",
    EMBEDDING_DIMENSIONS=3,
)
def test_rebuild_indexes_eligible_articles_and_removes_stale_points(profile):
    from apps.search.qdrant import ensure_article_collection, rebuild_article_collection

    article = create_article(profile)
    add_embedding(article)
    client = memory_client()
    ensure_article_collection(client=client)
    stale_id = "11111111-1111-1111-1111-111111111111"
    client.upsert(
        "test-articles",
        points=[models.PointStruct(id=stale_id, vector=[0.0, 1.0, 0.0])],
        wait=True,
    )

    result = rebuild_article_collection(client=client, batch_size=1)

    assert result.indexed == 1
    assert result.removed == 1
    assert client.retrieve("test-articles", ids=[stale_id]) == []
    assert len(client.retrieve("test-articles", ids=[str(article.qdrant_point_id)])) == 1
