from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic_ai.embeddings.openai import OpenAIEmbeddingModel
from pydantic_ai.exceptions import ModelHTTPError

from apps.core.article_embeddings import (
    EmbeddingError,
    EmbeddingResponse,
    EmbeddingService,
    PydanticEmbeddingClient,
    embed_article,
    prepare_embedding_text,
    queue_article_embedding,
)
from apps.core.article_ingestion import ArticleIngestionService
from apps.core.choices import ArticleEmbeddingStates
from apps.core.models import ArticleEmbedding

from .test_article_ingestion import create_project, create_sync, extraction_for


@dataclass
class FakeEmbeddingClient:
    vectors: list[list[float]]
    input_tokens: int = 7
    error: EmbeddingError | None = None

    def __post_init__(self):
        self.calls: list[tuple[str, int]] = []

    def embed(self, text: str, *, dimensions: int) -> EmbeddingResponse:
        self.calls.append((text, dimensions))
        if self.error:
            raise self.error
        return EmbeddingResponse(
            vector=self.vectors.pop(0),
            input_tokens=self.input_tokens,
        )


def create_article(profile, *, text="Stable useful article text."):
    project = create_project(profile)
    _sync, [work] = create_sync(project, "embedding", "https://example.com/post")
    extraction_for(work, text=text)
    return ArticleIngestionService.ingest(work=work)


@pytest.mark.django_db
def test_embedding_is_one_current_record_and_unchanged_content_skips_provider(
    profile,
    monkeypatch,
):
    article = create_article(profile)
    tracked = []
    monkeypatch.setattr(
        "apps.core.article_embeddings.track_funnel_event",
        lambda *args, **kwargs: tracked.append((args, kwargs)),
    )
    times = iter([10.0, 10.125])
    monkeypatch.setattr(
        "apps.core.article_embeddings.time.perf_counter",
        lambda: next(times),
    )
    client = FakeEmbeddingClient(vectors=[[0.1, 0.2, 0.3]])
    service = EmbeddingService(
        client=client,
        model="fake:article-v1",
        dimensions=3,
        max_input_chars=100,
    )

    first = service.embed_article(article_uuid=article.uuid)
    second = service.embed_article(article_uuid=article.uuid)

    assert first.pk == second.pk
    assert ArticleEmbedding.objects.filter(article=article).count() == 1
    assert first.state == ArticleEmbeddingStates.SUCCEEDED
    assert first.vector == [0.1, 0.2, 0.3]
    assert first.content_hash == article.content_hash
    assert first.model == "fake:article-v1"
    assert first.dimensions == 3
    assert first.input_tokens == 7
    assert first.latency_ms == 125
    assert len(client.calls) == 1
    assert client.calls[0] == (article.content, 3)
    assert len(tracked) == 1
    assert tracked[0][0][1] == "citeguild_embedding_completed"
    assert tracked[0][0][2]["input_tokens"] == 7
    assert tracked[0][0][2]["duration_ms"] == 125


@pytest.mark.django_db
def test_changed_content_refreshes_same_embedding_record(profile):
    article = create_article(profile)
    client = FakeEmbeddingClient(vectors=[[0.1, 0.2], [0.3, 0.4]])
    service = EmbeddingService(
        client=client,
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    )
    original = service.embed_article(article_uuid=article.uuid)
    article.content = "Changed article content."
    article.content_hash = "b" * 64
    article.save(update_fields=["content", "content_hash", "updated_at"])

    refreshed = service.embed_article(article_uuid=article.uuid)

    assert refreshed.pk == original.pk
    assert refreshed.vector == [0.3, 0.4]
    assert refreshed.content_hash == "b" * 64
    assert len(client.calls) == 2


def test_long_article_is_one_deterministic_bounded_input():
    text = "START " + ("middle " * 100) + " END"

    prepared = prepare_embedding_text(text, max_chars=80)

    assert len(prepared) == 80
    assert prepared.startswith("START")
    assert prepared.endswith("END")
    assert "[content truncated]" in prepared
    assert prepare_embedding_text(text, max_chars=80) == prepared


@pytest.mark.django_db
def test_empty_article_is_explicit_nonretryable_error(profile):
    article = create_article(profile)
    article.content = " \n\t "
    article.content_hash = ""
    article.save(update_fields=["content", "content_hash", "updated_at"])
    service = EmbeddingService(
        client=FakeEmbeddingClient(vectors=[]),
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    )

    with pytest.raises(EmbeddingError) as raised:
        service.embed_article(article_uuid=article.uuid)

    assert raised.value.code == "empty_input"
    assert raised.value.retryable is False


@pytest.mark.django_db
def test_dimension_mismatch_is_persisted_without_vector(profile):
    article = create_article(profile)
    service = EmbeddingService(
        client=FakeEmbeddingClient(vectors=[[0.1]]),
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    )

    with pytest.raises(EmbeddingError) as raised:
        service.embed_article(article_uuid=article.uuid)

    assert raised.value.code == "dimension_mismatch"
    assert raised.value.retryable is False
    embedding = ArticleEmbedding.objects.get(article=article)
    assert embedding.state == ArticleEmbeddingStates.FAILED
    assert embedding.vector == []
    assert embedding.error_code == "dimension_mismatch"


@pytest.mark.django_db
def test_non_finite_provider_vector_is_rejected(profile):
    article = create_article(profile)
    service = EmbeddingService(
        client=FakeEmbeddingClient(vectors=[[0.1, float("nan")]]),
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    )

    with pytest.raises(EmbeddingError) as raised:
        service.embed_article(article_uuid=article.uuid)

    assert raised.value.code == "invalid_vector"
    embedding = ArticleEmbedding.objects.get(article=article)
    assert embedding.vector == []


@pytest.mark.django_db
def test_retryable_provider_failure_records_only_stable_error_code(profile):
    article = create_article(profile)
    client = FakeEmbeddingClient(
        vectors=[],
        error=EmbeddingError("provider_unavailable", retryable=True),
    )
    service = EmbeddingService(
        client=client,
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    )

    with pytest.raises(EmbeddingError) as raised:
        service.embed_article(article_uuid=article.uuid)

    assert raised.value.retryable is True
    embedding = ArticleEmbedding.objects.get(article=article)
    assert embedding.error_code == "provider_unavailable"
    assert embedding.vector == []


@pytest.mark.django_db
def test_model_or_dimension_change_forces_regeneration(profile):
    article = create_article(profile)
    first_client = FakeEmbeddingClient(vectors=[[0.1, 0.2]])
    EmbeddingService(
        client=first_client,
        model="fake:article-v1",
        dimensions=2,
        max_input_chars=100,
    ).embed_article(article_uuid=article.uuid)
    next_client = FakeEmbeddingClient(vectors=[[0.1, 0.2, 0.3]])

    embedding = EmbeddingService(
        client=next_client,
        model="fake:article-v2",
        dimensions=3,
        max_input_chars=100,
    ).embed_article(article_uuid=article.uuid)

    assert embedding.model == "fake:article-v2"
    assert embedding.dimensions == 3
    assert len(next_client.calls) == 1


def test_queue_is_feature_gated_and_contains_no_article_content(settings, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "apps.core.article_embeddings.async_task",
        lambda *args, **kwargs: calls.append((args, kwargs)) or "task-id",
    )
    settings.CITEGUILD_INDEXING_ENABLED = False

    assert queue_article_embedding("article-uuid") is None
    assert calls == []

    settings.CITEGUILD_INDEXING_ENABLED = True
    assert queue_article_embedding("article-uuid") == "task-id"
    assert calls == [
        (
            ("apps.core.article_embeddings.embed_article", "article-uuid"),
            {"group": "article-embedding:article-uuid"},
        )
    ]


def test_provider_http_failure_is_retryable_without_leaking_response_body():
    class FailedEmbedder:
        def embed_documents_sync(self, text, *, settings):
            raise ModelHTTPError(
                429,
                "private-model",
                body={"message": "private provider response"},
            )

    client = PydanticEmbeddingClient.__new__(PydanticEmbeddingClient)
    client.embedder = FailedEmbedder()

    with pytest.raises(EmbeddingError) as raised:
        client.embed("safe input", dimensions=2)

    assert raised.value.code == "provider_http_error"
    assert raised.value.retryable is True
    assert "private" not in str(raised.value)


def test_pydantic_embedding_client_attributes_openrouter_usage_to_citeguild(settings):
    settings.OPENROUTER_API_KEY = "openrouter-test-key"
    settings.OPENROUTER_APP_URL = "https://citeguild.lvtd.dev"
    settings.OPENROUTER_APP_TITLE = "CiteGuild"

    client = PydanticEmbeddingClient("openrouter:openai/text-embedding-3-small")

    model = client.embedder.model
    assert isinstance(model, OpenAIEmbeddingModel)
    headers = model._provider.client.default_headers
    assert headers["HTTP-Referer"] == "https://citeguild.lvtd.dev"
    assert headers["X-Title"] == "CiteGuild"


@pytest.mark.parametrize(
    ("retryable", "expected"),
    [(False, "failed:provider_error"), (True, None)],
)
def test_worker_retries_only_retryable_failures(monkeypatch, retryable, expected):
    monkeypatch.setattr(
        "apps.core.article_embeddings.EmbeddingService.embed_article",
        lambda self, article_uuid: (_ for _ in ()).throw(
            EmbeddingError("provider_error", retryable=retryable)
        ),
    )

    if retryable:
        with pytest.raises(EmbeddingError):
            embed_article("article-uuid")
    else:
        assert embed_article("article-uuid") == expected
