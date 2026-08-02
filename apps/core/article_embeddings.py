"""One bounded whole-article embedding with durable idempotency metadata."""

from __future__ import annotations

import logging
import math
import time
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_q.tasks import async_task
from pydantic_ai import Embedder
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError

from apps.core.choices import ArticleEmbeddingStates, ArticleStates, ExtractionStates
from apps.core.models import Article, ArticleEmbedding

logger = logging.getLogger(__name__)

EMBEDDING_METRICS = Counter()
TRUNCATION_MARKER = "\n\n[content truncated]\n\n"


class EmbeddingError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class EmbeddingResponse:
    vector: list[float]
    input_tokens: int = 0


class EmbeddingClient(Protocol):
    def embed(self, text: str, *, dimensions: int) -> EmbeddingResponse: ...


class PydanticEmbeddingClient:
    def __init__(self, model: str):
        self.embedder = Embedder(model)

    def embed(self, text: str, *, dimensions: int) -> EmbeddingResponse:
        try:
            result = self.embedder.embed_documents_sync(
                text,
                settings={"dimensions": dimensions},
            )
        except ModelHTTPError as error:
            retryable = error.status_code in {408, 409, 429} or error.status_code >= 500
            raise EmbeddingError("provider_http_error", retryable=retryable) from error
        except (httpx.TimeoutException, httpx.TransportError) as error:
            raise EmbeddingError("provider_unavailable", retryable=True) from error
        except ModelAPIError as error:
            raise EmbeddingError("provider_error") from error
        except Exception as error:
            raise EmbeddingError("provider_error") from error

        if len(result.embeddings) != 1:
            raise EmbeddingError("unexpected_embedding_count")
        input_tokens = max(0, int(result.usage.input_tokens or 0))
        return EmbeddingResponse(
            vector=[float(value) for value in result.embeddings[0]],
            input_tokens=input_tokens,
        )


def prepare_embedding_text(text: str, *, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        raise EmbeddingError("empty_input")
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= len(TRUNCATION_MARKER):
        raise EmbeddingError("input_limit_too_small")
    retained_chars = max_chars - len(TRUNCATION_MARKER)
    head_chars = retained_chars // 2
    tail_chars = retained_chars - head_chars
    return f"{normalized[:head_chars]}{TRUNCATION_MARKER}{normalized[-tail_chars:]}"


def _validated_vector(values, *, dimensions: int) -> list[float]:
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError) as error:
        raise EmbeddingError("invalid_vector") from error
    if len(vector) != dimensions:
        raise EmbeddingError("dimension_mismatch")
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingError("invalid_vector")
    return vector


def _vector_is_valid(values, *, dimensions: int) -> bool:
    try:
        _validated_vector(values, dimensions=dimensions)
    except EmbeddingError:
        return False
    return True


class EmbeddingService:
    def __init__(
        self,
        *,
        client: EmbeddingClient | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        max_input_chars: int | None = None,
    ):
        self.model = model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIMENSIONS
        self.max_input_chars = max_input_chars or settings.EMBEDDING_MAX_INPUT_CHARS
        self.client = client or PydanticEmbeddingClient(self.model)

    @staticmethod
    def _eligible(article: Article) -> bool:
        return (
            article.state != ArticleStates.INACTIVE
            and article.extraction_state == ExtractionStates.READY
        )

    def _record_failure(
        self,
        *,
        article: Article,
        error: EmbeddingError,
        input_chars: int,
        latency_ms: int,
    ) -> None:
        with transaction.atomic():
            current = Article.objects.select_for_update().get(  # ty: ignore[unresolved-attribute]
                pk=article.pk
            )
            existing = (
                ArticleEmbedding.objects.select_for_update()
                .filter(  # ty: ignore[unresolved-attribute]
                    article=current
                )
                .first()
            )
            failure_is_stale = current.content_hash != article.content_hash
            matching_success_exists = (
                existing
                and existing.state == ArticleEmbeddingStates.SUCCEEDED
                and existing.content_hash == current.content_hash
                and existing.model == self.model
                and existing.dimensions == self.dimensions
                and _vector_is_valid(
                    existing.vector,
                    dimensions=self.dimensions,
                )
            )
            if not failure_is_stale and not matching_success_exists:
                ArticleEmbedding.objects.update_or_create(  # ty: ignore[unresolved-attribute]
                    article=current,
                    defaults={
                        "state": ArticleEmbeddingStates.FAILED,
                        "vector": [],
                        "content_hash": current.content_hash,
                        "model": self.model,
                        "dimensions": self.dimensions,
                        "input_chars": input_chars,
                        "input_tokens": 0,
                        "latency_ms": latency_ms,
                        "error_code": error.code,
                        "embedded_at": None,
                    },
                )
        EMBEDDING_METRICS[f"{self.model}:failed"] += 1
        logger.warning(
            "article.embedding.completed",
            extra={
                "event.name": "article.embedding.completed",
                "article_uuid": str(article.uuid),
                "embedding.model": self.model,
                "embedding.dimensions": self.dimensions,
                "embedding.input_chars": input_chars,
                "duration_ms": latency_ms,
                "error.type": error.code,
                "operation.status": "failed",
                "outcome": "failure",
                "retryable": error.retryable,
            },
        )

    def embed_article(self, *, article_uuid) -> ArticleEmbedding:
        article = Article.objects.get(uuid=article_uuid)  # ty: ignore[unresolved-attribute]
        if not self._eligible(article):
            raise EmbeddingError("article_not_eligible")

        existing = ArticleEmbedding.objects.filter(  # ty: ignore[unresolved-attribute]
            article=article
        ).first()
        if (
            existing
            and existing.state == ArticleEmbeddingStates.SUCCEEDED
            and existing.content_hash == article.content_hash
            and existing.model == self.model
            and existing.dimensions == self.dimensions
            and _vector_is_valid(existing.vector, dimensions=self.dimensions)
        ):
            EMBEDDING_METRICS[f"{self.model}:skipped"] += 1
            return existing

        try:
            prepared = prepare_embedding_text(
                article.content,
                max_chars=self.max_input_chars,
            )
        except EmbeddingError as error:
            self._record_failure(
                article=article,
                error=error,
                input_chars=0,
                latency_ms=0,
            )
            raise

        started_at = time.perf_counter()
        try:
            response = self.client.embed(prepared, dimensions=self.dimensions)
            vector = _validated_vector(response.vector, dimensions=self.dimensions)
        except EmbeddingError as error:
            latency_ms = max(0, round((time.perf_counter() - started_at) * 1_000))
            self._record_failure(
                article=article,
                error=error,
                input_chars=len(prepared),
                latency_ms=latency_ms,
            )
            raise

        latency_ms = max(0, round((time.perf_counter() - started_at) * 1_000))
        with transaction.atomic():
            current = Article.objects.select_for_update().get(  # ty: ignore[unresolved-attribute]
                pk=article.pk
            )
            if current.content_hash != article.content_hash:
                raise EmbeddingError("content_changed_during_embedding", retryable=True)
            embedding, _created = ArticleEmbedding.objects.update_or_create(  # ty: ignore[unresolved-attribute]
                article=current,
                defaults={
                    "state": ArticleEmbeddingStates.SUCCEEDED,
                    "vector": vector,
                    "content_hash": current.content_hash,
                    "model": self.model,
                    "dimensions": self.dimensions,
                    "input_chars": len(prepared),
                    "input_tokens": response.input_tokens,
                    "latency_ms": latency_ms,
                    "error_code": "",
                    "embedded_at": timezone.now(),
                },
            )

        EMBEDDING_METRICS[f"{self.model}:succeeded"] += 1
        logger.info(
            "article.embedding.completed",
            extra={
                "event.name": "article.embedding.completed",
                "article_uuid": str(article.uuid),
                "embedding.model": self.model,
                "embedding.dimensions": self.dimensions,
                "embedding.input_chars": len(prepared),
                "ai.usage.input_tokens": response.input_tokens,
                "duration_ms": latency_ms,
                "operation.status": "succeeded",
                "outcome": "success",
            },
        )
        return embedding


def embed_article(article_uuid: str) -> str:
    try:
        embedding = EmbeddingService().embed_article(article_uuid=article_uuid)
    except EmbeddingError as error:
        if error.retryable:
            raise
        return f"failed:{error.code}"
    return str(embedding.uuid)


def queue_article_embedding(article_uuid) -> str | None:
    if not settings.CITEGUILD_INDEXING_ENABLED:
        return None
    return async_task(
        "apps.core.article_embeddings.embed_article",
        str(article_uuid),
        group=f"article-embedding:{article_uuid}",
    )
