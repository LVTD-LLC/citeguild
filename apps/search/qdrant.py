"""Authenticated Qdrant collection and article index operations.

PostgreSQL remains authoritative for ownership and article lifecycle. Qdrant payload
filters reduce the candidate set, but callers must supply already-authorized projects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django_q.tasks import async_task
from qdrant_client import QdrantClient, models

from apps.core.choices import (
    ArticleEmbeddingStates,
    ArticleStates,
    ExtractionStates,
    ProjectStates,
)
from apps.core.models import Article, Project

ARTICLE_OBJECTS = Article.objects  # ty: ignore[unresolved-attribute]
PROJECT_OBJECTS = Project.objects  # ty: ignore[unresolved-attribute]

MAX_SEARCH_LIMIT = 50
PAYLOAD_INDEXES = {
    "active": models.PayloadSchemaType.BOOL,
    "project_uuid": models.PayloadSchemaType.KEYWORD,
    "site_host": models.PayloadSchemaType.KEYWORD,
    "language": models.PayloadSchemaType.KEYWORD,
}


class QdrantContractError(Exception):
    """A stable, privacy-safe Qdrant contract failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ArticleSearchHit:
    article_uuid: UUID
    score: float
    title: str
    canonical_url: str
    site_host: str
    language: str
    content: str
    last_seen_at: datetime


@dataclass(frozen=True)
class RebuildResult:
    indexed: int
    removed: int


@cache
def get_qdrant_client() -> QdrantClient:
    if not settings.QDRANT_URL:
        raise ImproperlyConfigured("QDRANT_URL must be configured before using Qdrant.")
    if not settings.QDRANT_API_KEY:
        raise ImproperlyConfigured("QDRANT_API_KEY must be configured before using Qdrant.")

    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def _vector_params(collection_info):
    vectors = collection_info.config.params.vectors
    if isinstance(vectors, dict):
        raise QdrantContractError("named_vectors_not_supported")
    return vectors


def validate_article_collection(*, client: QdrantClient | None = None):
    client = client or get_qdrant_client()
    collection = settings.QDRANT_COLLECTION
    if not client.collection_exists(collection):
        raise QdrantContractError("collection_missing")
    collection_info = client.get_collection(collection)
    params = _vector_params(collection_info)
    if params.size != settings.EMBEDDING_DIMENSIONS:
        raise QdrantContractError("collection_dimension_mismatch")
    if params.distance != models.Distance.COSINE:
        raise QdrantContractError("collection_distance_mismatch")
    return collection_info


def _ensure_payload_indexes(*, client: QdrantClient, collection_info) -> None:
    missing_indexes = []
    for field_name, field_schema in PAYLOAD_INDEXES.items():
        existing = collection_info.payload_schema.get(field_name)
        if existing is None:
            missing_indexes.append((field_name, field_schema))
        elif existing.data_type != field_schema:
            raise QdrantContractError("payload_index_schema_mismatch")

    for field_name, field_schema in missing_indexes:
        try:
            client.create_payload_index(
                collection_name=settings.QDRANT_COLLECTION,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )
        except Exception as error:
            # A concurrent bootstrapper may have created the index first.
            concurrent = client.get_collection(settings.QDRANT_COLLECTION).payload_schema.get(
                field_name
            )
            if concurrent and concurrent.data_type == field_schema:
                continue
            raise QdrantContractError("payload_index_create_failed") from error


def ensure_article_collection(*, client: QdrantClient | None = None) -> bool:
    """Create the collection once and reject incompatible existing collections."""
    client = client or get_qdrant_client()
    collection = settings.QDRANT_COLLECTION
    created = False
    if not client.collection_exists(collection):
        try:
            client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIMENSIONS,
                    distance=models.Distance.COSINE,
                ),
            )
            created = True
        except Exception as error:
            # Concurrent bootstrappers may both observe a missing collection.
            if not client.collection_exists(collection):
                raise QdrantContractError("collection_create_failed") from error

    collection_info = validate_article_collection(client=client)

    _ensure_payload_indexes(client=client, collection_info=collection_info)
    return created


def article_collection_healthy(*, client: QdrantClient | None = None) -> bool:
    """Return whether the authenticated collection matches the runtime contract."""
    try:
        client = client or get_qdrant_client()
        validate_article_collection(client=client)
        return True
    except Exception:
        return False


def _eligible_embedding(article: Article):
    try:
        embedding = article.embedding  # ty: ignore[unresolved-attribute]
    except ObjectDoesNotExist as error:
        raise QdrantContractError("embedding_missing") from error
    if (
        article.project.state  # ty: ignore[unresolved-attribute]
        != ProjectStates.ACTIVE
        or article.state == ArticleStates.INACTIVE
        or article.extraction_state != ExtractionStates.READY
        or embedding.state != ArticleEmbeddingStates.SUCCEEDED
        or embedding.content_hash != article.content_hash
        or embedding.model != settings.EMBEDDING_MODEL
        or embedding.dimensions != settings.EMBEDDING_DIMENSIONS
        or len(embedding.vector) != settings.EMBEDDING_DIMENSIONS
        or not all(
            isinstance(value, (float, int)) and math.isfinite(float(value))
            for value in embedding.vector
        )
    ):
        raise QdrantContractError("article_not_indexable")
    return embedding


def _article_payload(article: Article) -> dict:
    return {
        "article_uuid": str(article.uuid),
        "project_uuid": str(article.project.uuid),  # ty: ignore[unresolved-attribute]
        "site_host": article.project.normalized_host,  # ty: ignore[unresolved-attribute]
        "language": article.language,
        "content_hash": article.content_hash,
        "embedding_model": settings.EMBEDDING_MODEL,
        "active": True,
    }


def _point_for_article(article: Article) -> models.PointStruct:
    embedding = _eligible_embedding(article)
    return models.PointStruct(
        id=str(article.qdrant_point_id),
        vector=embedding.vector,
        payload=_article_payload(article),
    )


def _mark_active(article: Article) -> None:
    with transaction.atomic():
        current = ARTICLE_OBJECTS.select_for_update().select_related("project").get(pk=article.pk)
        embedding = current.embedding
        if (
            current.content_hash != article.content_hash
            or current.project.state != ProjectStates.ACTIVE
            or current.state == ArticleStates.INACTIVE
            or current.extraction_state != ExtractionStates.READY
            or embedding.state != ArticleEmbeddingStates.SUCCEEDED
            or embedding.content_hash != current.content_hash
            or embedding.model != settings.EMBEDDING_MODEL
            or embedding.dimensions != settings.EMBEDDING_DIMENSIONS
        ):
            raise QdrantContractError("article_changed_during_upsert")
        if not current.is_active:
            PROJECT_OBJECTS.filter(pk=current.project_id).update(
                active_article_count=F("active_article_count") + 1
            )
        current.state = ArticleStates.ACTIVE
        current.is_active = True
        current.inactivity_reason = ""
        current.inactive_at = None
        current.save(
            update_fields=[
                "state",
                "is_active",
                "inactivity_reason",
                "inactive_at",
                "updated_at",
            ]
        )


def upsert_article(*, article: Article, client: QdrantClient | None = None) -> None:
    client = client or get_qdrant_client()
    validate_article_collection(client=client)
    article = ARTICLE_OBJECTS.select_related("project", "embedding").get(pk=article.pk)
    point = _point_for_article(article)
    client.upsert(
        collection_name=settings.QDRANT_COLLECTION,
        points=[point],
        wait=True,
    )
    _mark_active(article)


def deactivate_article(*, article: Article, client: QdrantClient | None = None) -> None:
    """Remove the search point and mark the PostgreSQL article inactive."""
    client = client or get_qdrant_client()
    if client.collection_exists(settings.QDRANT_COLLECTION):
        client.delete(
            collection_name=settings.QDRANT_COLLECTION,
            points_selector=models.PointIdsList(points=[str(article.qdrant_point_id)]),
            wait=True,
        )
    with transaction.atomic():
        current = ARTICLE_OBJECTS.select_for_update().get(pk=article.pk)
        if current.is_active:
            PROJECT_OBJECTS.filter(pk=current.project_id).update(
                active_article_count=F("active_article_count") - 1
            )
        current.state = ArticleStates.INACTIVE
        current.is_active = False
        current.inactivity_reason = current.inactivity_reason or "deactivated"
        current.inactive_at = current.inactive_at or timezone.now()
        current.save(
            update_fields=[
                "state",
                "is_active",
                "inactivity_reason",
                "inactive_at",
                "updated_at",
            ]
        )


def _authorized_search_hits(
    scored_uuids: list[tuple[UUID, float]],
    *,
    authorized_project_uuids: set[UUID],
    limit: int,
) -> list[ArticleSearchHit]:
    eligible_owner = Q(project__owner__stripe_subscription_status__in=("active", "past_due"))
    if settings.ENVIRONMENT == "prod":
        eligible_owner |= Q(project__owner__user__is_superuser=True)
    authorized_articles = {
        article.uuid: article
        for article in ARTICLE_OBJECTS.filter(
            eligible_owner,
            uuid__in=[value for value, _score in scored_uuids],
            project__uuid__in=authorized_project_uuids,
            project__state=ProjectStates.ACTIVE,
            state=ArticleStates.ACTIVE,
            is_active=True,
            extraction_state=ExtractionStates.READY,
            embedding__state=ArticleEmbeddingStates.SUCCEEDED,
            embedding__content_hash=F("content_hash"),
            embedding__model=settings.EMBEDDING_MODEL,
            embedding__dimensions=settings.EMBEDDING_DIMENSIONS,
        ).select_related("project")
    }
    hits = []
    for article_uuid, score in sorted(scored_uuids, key=lambda item: (-item[1], str(item[0]))):
        article = authorized_articles.get(article_uuid)
        if article is None:
            continue
        hits.append(
            ArticleSearchHit(
                article_uuid=article.uuid,
                score=score,
                title=article.title,
                canonical_url=article.normalized_canonical_url,
                site_host=article.project.normalized_host,
                language=article.language,
                content=article.content,
                last_seen_at=article.last_seen_at,
            )
        )
        if len(hits) >= limit:
            break
    return hits


def semantic_search(
    vector: list[float],
    *,
    authorized_project_uuids: set[UUID],
    language: str | None = None,
    site_host: str | None = None,
    excluded_site_hosts: set[str] | None = None,
    limit: int = 10,
    client: QdrantClient | None = None,
) -> list[ArticleSearchHit]:
    """Search only an application-authorized project scope with bounded output."""
    if not authorized_project_uuids:
        raise QdrantContractError("authorized_project_scope_required")
    if len(vector) != settings.EMBEDDING_DIMENSIONS:
        raise QdrantContractError("query_dimension_mismatch")
    limit = max(1, min(int(limit), MAX_SEARCH_LIMIT))
    conditions = [
        models.FieldCondition(key="active", match=models.MatchValue(value=True)),
        models.FieldCondition(
            key="project_uuid",
            match=models.MatchAny(any=[str(value) for value in authorized_project_uuids]),
        ),
    ]
    if language:
        conditions.append(
            models.FieldCondition(key="language", match=models.MatchValue(value=language))
        )
    if site_host:
        conditions.append(
            models.FieldCondition(key="site_host", match=models.MatchValue(value=site_host))
        )
    excluded_conditions = []
    if excluded_site_hosts:
        excluded_conditions.append(
            models.FieldCondition(
                key="site_host",
                match=models.MatchAny(any=sorted(excluded_site_hosts)),
            )
        )

    client = client or get_qdrant_client()
    validate_article_collection(client=client)
    response = client.query_points(
        collection_name=settings.QDRANT_COLLECTION,
        query=vector,
        query_filter=models.Filter(must=conditions, must_not=excluded_conditions),
        limit=min(limit * 3, 150),
        with_payload=True,
        with_vectors=False,
    )
    scored_uuids = []
    for point in response.points:
        payload = point.payload or {}
        try:
            score = float(point.score)
            if math.isfinite(score):
                scored_uuids.append((UUID(str(payload["article_uuid"])), score))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    if not scored_uuids:
        return []

    # Qdrant is not an authorization or lifecycle source of truth. Re-check every
    # candidate in PostgreSQL and return PostgreSQL metadata.
    return _authorized_search_hits(
        scored_uuids,
        authorized_project_uuids=authorized_project_uuids,
        limit=limit,
    )


def index_article(article_uuid: str) -> str:
    article = ARTICLE_OBJECTS.get(uuid=article_uuid)
    upsert_article(article=article)
    return str(article.uuid)


def queue_article_index(article_uuid) -> str | None:
    if not settings.CITEGUILD_INDEXING_ENABLED:
        return None
    return async_task(
        "apps.search.qdrant.index_article",
        str(article_uuid),
        group=f"article-index:{article_uuid}",
    )


def remove_article_point(article_uuid: str) -> str:
    article = ARTICLE_OBJECTS.get(uuid=article_uuid)
    deactivate_article(article=article)
    return str(article.uuid)


def queue_article_deactivation(article_uuid) -> str | None:
    if not settings.CITEGUILD_INDEXING_ENABLED:
        return None
    return async_task(
        "apps.search.qdrant.remove_article_point",
        str(article_uuid),
        group=f"article-deactivate:{article_uuid}",
    )


def rebuild_article_collection(
    *, client: QdrantClient | None = None, batch_size: int = 100
) -> RebuildResult:
    """Reconcile the vector collection to the current PostgreSQL corpus."""
    client = client or get_qdrant_client()
    ensure_article_collection(client=client)
    batch_size = max(1, min(int(batch_size), 500))
    queryset = (
        ARTICLE_OBJECTS.filter(
            project__state=ProjectStates.ACTIVE,
            extraction_state=ExtractionStates.READY,
            embedding__state=ArticleEmbeddingStates.SUCCEEDED,
            embedding__content_hash=F("content_hash"),
            embedding__model=settings.EMBEDDING_MODEL,
            embedding__dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        .exclude(state=ArticleStates.INACTIVE)
        .select_related("project", "embedding")
        .order_by("pk")
    )
    authoritative_ids: set[str] = set()
    indexed = 0
    pending: list[models.PointStruct] = []
    pending_articles: list[Article] = []
    for article in queryset.iterator(chunk_size=batch_size):
        try:
            point = _point_for_article(article)
        except QdrantContractError:
            continue
        authoritative_ids.add(str(article.qdrant_point_id))
        pending.append(point)
        pending_articles.append(article)
        if len(pending) >= batch_size:
            client.upsert(settings.QDRANT_COLLECTION, points=pending, wait=True)
            for item in pending_articles:
                _mark_active(item)
            indexed += len(pending)
            pending = []
            pending_articles = []
    if pending:
        client.upsert(settings.QDRANT_COLLECTION, points=pending, wait=True)
        for item in pending_articles:
            _mark_active(item)
        indexed += len(pending)

    removed = 0
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=settings.QDRANT_COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        stale = [record.id for record in records if str(record.id) not in authoritative_ids]
        if stale:
            client.delete(
                settings.QDRANT_COLLECTION,
                points_selector=models.PointIdsList(points=stale),
                wait=True,
            )
            removed += len(stale)
        if offset is None:
            break
    return RebuildResult(indexed=indexed, removed=removed)
