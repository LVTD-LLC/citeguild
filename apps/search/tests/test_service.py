from dataclasses import asdict, dataclass

import pytest
from django.test import override_settings
from qdrant_client import QdrantClient

from apps.core.article_embeddings import EmbeddingError, EmbeddingResponse
from apps.core.article_ingestion import ArticleIngestionService
from apps.core.choices import ArticleEmbeddingStates, ArticleStates
from apps.core.models import ArticleEmbedding
from apps.core.tests.test_article_ingestion import (
    create_project,
    create_sync,
    extraction_for,
)
from apps.search.qdrant import ensure_article_collection, upsert_article


@dataclass
class FakeQueryEmbedder:
    vector: list[float] | None = None
    error: EmbeddingError | None = None

    def __post_init__(self):
        self.calls = []

    def embed(self, text: str, *, dimensions: int) -> EmbeddingResponse:
        self.calls.append((text, dimensions))
        if self.error:
            raise self.error
        return EmbeddingResponse(vector=list(self.vector or []), input_tokens=4)


def _indexed_article(
    profile,
    client,
    *,
    host,
    text,
    vector,
    language="en",
):
    project = create_project(profile, host)
    _sync, [work] = create_sync(
        project,
        f"search:{host}",
        f"https://{host}/guide",
    )
    extraction = extraction_for(work, text=text)
    extraction.language = language
    extraction.save(update_fields=["language", "updated_at"])
    article = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    ArticleEmbedding.objects.create(
        article=article,
        state=ArticleEmbeddingStates.SUCCEEDED,
        vector=vector,
        content_hash=article.content_hash,
        model="test:search-v1",
        dimensions=3,
    )
    upsert_article(article=article, client=client)
    return article


@pytest.fixture
def search_client(settings):
    settings.QDRANT_COLLECTION = "test-search-service"
    settings.EMBEDDING_MODEL = "test:search-v1"
    settings.EMBEDDING_DIMENSIONS = 3
    client = QdrantClient(":memory:")
    ensure_article_collection(client=client)
    return client


@pytest.mark.django_db
def test_golden_corpus_ranks_relevant_above_unrelated_and_normalizes_contract(
    profile,
    search_client,
):
    from apps.search.service import SEARCH_CONTRACT_VERSION, SearchService

    relevant = _indexed_article(
        profile,
        search_client,
        host="relevant.example",
        text=(
            "A short preface. Django transaction.on_commit schedules work only after "
            "a successful database commit. This prevents jobs from seeing rolled-back rows."
        ),
        vector=[1.0, 0.0, 0.0],
    )
    _indexed_article(
        profile,
        search_client,
        host="unrelated.example",
        text="A practical guide to pruning apple trees during winter.",
        vector=[0.0, 1.0, 0.0],
    )
    _indexed_article(
        profile,
        search_client,
        host="own.example",
        text="Another accurate Django transaction.on_commit reference.",
        vector=[0.99, 0.01, 0.0],
    )
    embedder = FakeQueryEmbedder(vector=[1.0, 0.0, 0.0])
    response = SearchService(
        embedding_client=embedder,
        qdrant_client=search_client,
    ).search(
        profile=profile,
        query="How do I enqueue a job after a Django transaction commits?",
        limit=5,
        language="en",
        excluded_domains=["OWN.example."],
    )

    assert response.contract_version == SEARCH_CONTRACT_VERSION == "v1"
    assert [result.domain for result in response.results] == [
        "relevant.example",
        "unrelated.example",
    ]
    assert response.results[0].article_id == relevant.uuid
    assert response.results[0].relevance > response.results[1].relevance
    assert "transaction.on_commit" in response.results[0].excerpt
    assert len(response.results[0].excerpt) <= 320
    assert set(asdict(response.results[0])) == {
        "article_id",
        "title",
        "canonical_url",
        "domain",
        "excerpt",
        "relevance",
        "language",
        "last_seen_at",
    }
    assert embedder.calls == [("How do I enqueue a job after a Django transaction commits?", 3)]


@pytest.mark.django_db
def test_search_reauthorizes_active_members_and_applies_language_filter(
    profile,
    search_client,
):
    from apps.search.service import SearchService

    stale = _indexed_article(
        profile,
        search_client,
        host="stale.example",
        text="Django transaction commit hooks.",
        vector=[1.0, 0.0, 0.0],
    )
    german = _indexed_article(
        profile,
        search_client,
        host="german.example",
        text="Django Transaktionen und Commit Hooks.",
        vector=[0.9, 0.1, 0.0],
        language="de",
    )
    stale.state = ArticleStates.INACTIVE
    stale.is_active = False
    stale.save(update_fields=["state", "is_active", "updated_at"])

    response = SearchService(
        embedding_client=FakeQueryEmbedder(vector=[1.0, 0.0, 0.0]),
        qdrant_client=search_client,
    ).search(profile=profile, query="Django commit hooks", language="de")

    assert [result.article_id for result in response.results] == [german.uuid]


@pytest.mark.django_db
def test_search_enforces_subscription_input_and_limit_bounds(profile, search_client):
    from apps.search.service import SearchError, SearchService

    service = SearchService(
        embedding_client=FakeQueryEmbedder(vector=[1.0, 0.0, 0.0]),
        qdrant_client=search_client,
    )
    cases = [
        ({"query": ""}, "query_required"),
        ({"query": "x" * 8001}, "query_too_long"),
        ({"query": None}, "invalid_query"),
        ({"query": "valid query", "limit": 0}, "invalid_limit"),
        ({"query": "valid query", "limit": 51}, "invalid_limit"),
        ({"query": "valid query", "limit": True}, "invalid_limit"),
        ({"query": "valid query", "language": "not_a_language"}, "invalid_language"),
        (
            {"query": "valid query", "excluded_domains": ["not a domain"]},
            "invalid_excluded_domain",
        ),
        (
            {"query": "valid query", "excluded_domains": ["x.example"] * 21},
            "too_many_excluded_domains",
        ),
    ]
    for kwargs, code in cases:
        with pytest.raises(SearchError) as raised:
            service.search(profile=profile, **kwargs)
        assert raised.value.code == code
        assert raised.value.retryable is False

    profile.stripe_subscription_status = "canceled"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    with pytest.raises(SearchError) as raised:
        service.search(profile=profile, query="valid query")
    assert raised.value.code == "subscription_required"


@pytest.mark.django_db
@override_settings(ENVIRONMENT="prod")
def test_production_superuser_project_is_search_eligible(profile):
    from apps.search.service import _eligible_project_uuids

    project = create_project(profile, "operator-corpus.example")
    profile.stripe_subscription_status = "canceled"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    profile.user.is_superuser = True
    profile.user.save(update_fields=["is_superuser"])

    assert project.uuid in _eligible_project_uuids()


@pytest.mark.django_db
def test_empty_corpus_is_graceful_and_provider_failure_is_observable(
    profile,
    search_client,
    caplog,
):
    from apps.search.service import SearchError, SearchService

    create_project(profile, "empty-corpus.example")
    empty = SearchService(
        embedding_client=FakeQueryEmbedder(vector=[1.0, 0.0, 0.0]),
        qdrant_client=search_client,
    ).search(profile=profile, query="nothing indexed")
    assert empty.results == ()

    query = "private draft text must not enter logs"
    with caplog.at_level("WARNING", logger="apps.search.service"):
        with pytest.raises(SearchError) as raised:
            SearchService(
                embedding_client=FakeQueryEmbedder(
                    error=EmbeddingError("provider_unavailable", retryable=True)
                ),
                qdrant_client=search_client,
            ).search(profile=profile, query=query)

    assert raised.value.code == "query_embedding_unavailable"
    assert raised.value.retryable is True
    assert query not in caplog.text
    assert "search.completed" in caplog.text


@pytest.mark.django_db
def test_search_index_failures_have_stable_retry_classification(
    profile,
    search_client,
    monkeypatch,
):
    from qdrant_client.http.exceptions import ApiException

    from apps.search.qdrant import QdrantContractError
    from apps.search.service import SearchError, SearchService

    create_project(profile, "dependency-failure.example")
    service = SearchService(
        embedding_client=FakeQueryEmbedder(vector=[1.0, 0.0, 0.0]),
        qdrant_client=search_client,
    )

    def invalid_index(*_args, **_kwargs):
        raise QdrantContractError("collection_dimension_mismatch")

    monkeypatch.setattr("apps.search.service.semantic_search", invalid_index)
    with pytest.raises(SearchError) as raised:
        service.search(profile=profile, query="valid query")
    assert (raised.value.code, raised.value.retryable) == (
        "search_index_invalid",
        False,
    )

    def unavailable_index(*_args, **_kwargs):
        raise ApiException("connection unavailable")

    monkeypatch.setattr("apps.search.service.semantic_search", unavailable_index)
    with pytest.raises(SearchError) as raised:
        service.search(profile=profile, query="valid query")
    assert (raised.value.code, raised.value.retryable) == (
        "search_index_unavailable",
        True,
    )
