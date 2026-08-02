"""Versioned member-corpus semantic search shared by every transport adapter."""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ApiException

from apps.core.article_embeddings import (
    EmbeddingClient,
    EmbeddingError,
    PydanticEmbeddingClient,
)
from apps.core.choices import ProjectStates
from apps.core.models import Profile, Project
from apps.search.qdrant import QdrantContractError, semantic_search

logger = logging.getLogger(__name__)
PROJECT_OBJECTS = Project.objects  # ty: ignore[unresolved-attribute]

SEARCH_CONTRACT_VERSION = "v1"
MAX_QUERY_CHARS = 8_000
MAX_SEARCH_LIMIT = 50
MAX_EXCLUDED_DOMAINS = 20
MAX_EXCERPT_CHARS = 320
SEARCH_METRICS = Counter()

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z"
)
_QUERY_TERM_RE = re.compile(r"[^\W_]{3,}", re.UNICODE)


class SearchError(Exception):
    """Stable adapter-safe failure without user text or provider details."""

    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class SearchResult:
    article_id: UUID
    title: str
    canonical_url: str
    domain: str
    excerpt: str
    relevance: float
    language: str
    last_seen_at: datetime


@dataclass(frozen=True, slots=True)
class SearchResponse:
    contract_version: str
    results: tuple[SearchResult, ...]


def _normalize_query(value: str) -> str:
    if not isinstance(value, str):
        raise SearchError("invalid_query")
    normalized = " ".join(value.split())
    if not normalized:
        raise SearchError("query_required")
    if len(normalized) > MAX_QUERY_CHARS:
        raise SearchError("query_too_long")
    return normalized


def _normalize_language(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = value.strip().lower()
    if len(normalized) > 35 or not re.fullmatch(
        r"[a-z]{2,8}(?:-[a-z0-9]{1,8})*",
        normalized,
    ):
        raise SearchError("invalid_language")
    return normalized


def _normalize_domain(value: str) -> str:
    raw = str(value or "").strip().rstrip(".").lower()
    if not raw or "://" in raw or any(character in raw for character in "/?#@:"):
        raise SearchError("invalid_excluded_domain")
    try:
        host = urlsplit(f"//{raw}").hostname
        ascii_raw = raw.encode("idna").decode("ascii").lower()
        normalized = (host or "").encode("idna").decode("ascii").lower()
    except (UnicodeError, ValueError) as error:
        raise SearchError("invalid_excluded_domain") from error
    if normalized != ascii_raw or not _DOMAIN_RE.fullmatch(normalized):
        raise SearchError("invalid_excluded_domain")
    return normalized


def _normalize_excluded_domains(values: Iterable[str]) -> set[str]:
    materialized = list(islice(values, MAX_EXCLUDED_DOMAINS + 1))
    if len(materialized) > MAX_EXCLUDED_DOMAINS:
        raise SearchError("too_many_excluded_domains")
    return {_normalize_domain(value) for value in materialized}


def _eligible_project_uuids() -> set[UUID]:
    paid_owner = Q(owner__stripe_subscription_status__in={"active", "past_due"})
    if settings.ENVIRONMENT == "prod":
        paid_owner |= Q(owner__user__is_superuser=True)
    return set(
        PROJECT_OBJECTS.filter(paid_owner, state=ProjectStates.ACTIVE).values_list(
            "uuid",
            flat=True,
        )
    )


def _excerpt(text: str, *, query: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= MAX_EXCERPT_CHARS:
        return normalized

    lowered = normalized.casefold()
    positions = [
        lowered.find(term)
        for term in dict.fromkeys(_QUERY_TERM_RE.findall(query.casefold()))
        if lowered.find(term) >= 0
    ]
    pivot = min(positions) if positions else 0
    start = max(0, pivot - MAX_EXCERPT_CHARS // 3)
    end = min(len(normalized), start + MAX_EXCERPT_CHARS)
    if end - start < MAX_EXCERPT_CHARS:
        start = max(0, end - MAX_EXCERPT_CHARS)
    if start:
        next_space = normalized.find(" ", start)
        if 0 <= next_space < end:
            start = next_space + 1
    if end < len(normalized):
        previous_space = normalized.rfind(" ", start, end)
        if previous_space > start:
            end = previous_space
    excerpt = normalized[start:end]
    prefix = "…" if start else ""
    suffix = "…" if end < len(normalized) else ""
    return f"{prefix}{excerpt}{suffix}"[:MAX_EXCERPT_CHARS]


def _relevance(score: float) -> float:
    if not math.isfinite(score):
        return 0.0
    return round(max(0.0, min(1.0, score)), 6)


class SearchService:
    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient | None = None,
        qdrant_client: QdrantClient | None = None,
    ):
        self.embedding_client = embedding_client or PydanticEmbeddingClient(
            settings.EMBEDDING_MODEL
        )
        self.qdrant_client = qdrant_client

    def _record(
        self,
        *,
        started_at: float,
        status: str,
        result_count: int = 0,
        error_code: str = "",
        retryable: bool = False,
    ) -> None:
        SEARCH_METRICS[status] += 1
        log = logger.info if status == "succeeded" else logger.warning
        log(
            "search.completed",
            extra={
                "event.name": "search.completed",
                "search.contract_version": SEARCH_CONTRACT_VERSION,
                "search.result_count": result_count,
                "duration_ms": max(0, round((time.perf_counter() - started_at) * 1_000)),
                "operation.status": status,
                "outcome": "success" if status == "succeeded" else "failure",
                "error.type": error_code,
                "retryable": retryable,
            },
        )

    def search(
        self,
        *,
        profile: Profile,
        query: str,
        limit: int = 10,
        language: str | None = None,
        excluded_domains: Iterable[str] = (),
    ) -> SearchResponse:
        started_at = time.perf_counter()
        try:
            normalized_query = _normalize_query(query)
            if (
                not isinstance(limit, int)
                or isinstance(limit, bool)
                or not 1 <= limit <= MAX_SEARCH_LIMIT
            ):
                raise SearchError("invalid_limit")
            normalized_language = _normalize_language(language)
            normalized_exclusions = _normalize_excluded_domains(excluded_domains)
            profile.refresh_from_db()
            if not profile.has_active_subscription:
                raise SearchError("subscription_required")
            project_uuids = _eligible_project_uuids()
            if not project_uuids:
                response = SearchResponse(SEARCH_CONTRACT_VERSION, ())
                self._record(started_at=started_at, status="succeeded")
                return response

            try:
                embedding = self.embedding_client.embed(
                    normalized_query,
                    dimensions=settings.EMBEDDING_DIMENSIONS,
                )
            except EmbeddingError as error:
                raise SearchError(
                    "query_embedding_unavailable",
                    retryable=error.retryable,
                ) from error
            try:
                vector = [float(value) for value in embedding.vector]
            except (TypeError, ValueError) as error:
                raise SearchError("query_embedding_invalid") from error
            if len(vector) != settings.EMBEDDING_DIMENSIONS or not all(
                math.isfinite(value) for value in vector
            ):
                raise SearchError("query_embedding_invalid")

            try:
                hits = semantic_search(
                    vector,
                    authorized_project_uuids=project_uuids,
                    language=normalized_language,
                    excluded_site_hosts=normalized_exclusions,
                    limit=limit,
                    client=self.qdrant_client,
                )
            except QdrantContractError as error:
                raise SearchError("search_index_invalid") from error
            except (ApiException, ImproperlyConfigured) as error:
                raise SearchError("search_index_unavailable", retryable=True) from error

            results = tuple(
                SearchResult(
                    article_id=hit.article_uuid,
                    title=hit.title,
                    canonical_url=hit.canonical_url,
                    domain=hit.site_host,
                    excerpt=_excerpt(hit.content, query=normalized_query),
                    relevance=_relevance(hit.score),
                    language=hit.language,
                    last_seen_at=hit.last_seen_at,
                )
                for hit in hits
            )
            response = SearchResponse(SEARCH_CONTRACT_VERSION, results)
            self._record(
                started_at=started_at,
                status="succeeded",
                result_count=len(results),
            )
            return response
        except SearchError as error:
            self._record(
                started_at=started_at,
                status="failed",
                error_code=error.code,
                retryable=error.retryable,
            )
            raise
