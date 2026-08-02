from datetime import timedelta
from threading import Event, Thread

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone
from django_q.models import Schedule
from qdrant_client import QdrantClient

from apps.core.article_embeddings import EmbeddingError, EmbeddingResponse
from apps.core.article_ingestion import ArticleIngestionService
from apps.core.choices import (
    ExtractionStates,
    PageCrawlStates,
    ProjectStates,
    ProjectSyncStates,
)
from apps.core.crawl_jobs import (
    _claim_page_work,
    _index_ready_article,
    dispatch_page_work,
    enqueue_sitemap_sync,
    enqueue_sitemap_sync_safely,
    recover_crawl_jobs,
    run_page_crawl,
    run_sitemap_sync,
)
from apps.core.html_extraction import HtmlExtraction, PageExtractionService
from apps.core.models import Article, ArticleEmbedding, PageCrawlWork, ProjectSyncRequest
from apps.core.projects import ProjectService
from apps.core.safe_fetch import SafeFetchError, SafeFetchErrorCode
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseError,
    SitemapParseErrorCode,
    SitemapParseResult,
)


@pytest.fixture
def active_project(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    return ProjectService.create(
        owner=profile,
        name="Example",
        sitemap_url="https://example.com/sitemap.xml",
    )


@pytest.fixture
def sync_request(active_project):
    return ProjectSyncRequest.objects.create(
        project=active_project,
        sitemap_kind="urlset",
        idempotency_key=f"test:{active_project.uuid}",
    )


def parse_result(*paths):
    candidates = tuple(
        ParsedCandidate(
            f"https://example.com/{path}",
            f"https://example.com/{path}",
        )
        for path in paths
    )
    return SitemapParseResult(
        candidates,
        SitemapDiagnostics(1, len(candidates), len(candidates), 0, 0, 0, 0),
    )


@pytest.mark.django_db
def test_sync_enqueue_is_deduplicated_and_uses_uuid_only(sync_request, monkeypatch):
    calls = []

    def fake_async_task(*args, **kwargs):
        calls.append((args, kwargs))
        return "broker-task-1"

    monkeypatch.setattr("apps.core.crawl_jobs.async_task", fake_async_task)

    first = enqueue_sitemap_sync(sync_request.uuid)
    second = enqueue_sitemap_sync(sync_request.uuid)

    assert first == second == "broker-task-1"
    assert len(calls) == 1
    assert calls[0][0] == (
        "apps.core.crawl_jobs.run_sitemap_sync",
        str(sync_request.uuid),
    )
    assert "example.com" not in repr(calls)


@pytest.mark.django_db
def test_broker_failure_keeps_committed_sync_recoverable(sync_request, monkeypatch):
    monkeypatch.setattr(
        "apps.core.crawl_jobs.async_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("redis down")),
    )

    assert enqueue_sitemap_sync_safely(sync_request.uuid) == ""
    sync_request.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.QUEUED
    assert sync_request.broker_task_id == ""


@pytest.mark.django_db
def test_database_prevents_two_active_syncs_for_one_project(active_project):
    ProjectSyncRequest.objects.create(
        project=active_project,
        sitemap_kind="urlset",
        idempotency_key="first",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        ProjectSyncRequest.objects.create(
            project=active_project,
            sitemap_kind="urlset",
            idempotency_key="second",
        )


@pytest.mark.django_db
def test_successful_sync_creates_one_page_work_per_candidate(sync_request, monkeypatch, settings):
    settings.CRAWL_MAX_ATTEMPTS = 3
    dispatched = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result("b", "a"),
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs.dispatch_page_work",
        lambda sync_uuid: dispatched.append(sync_uuid) or 2,
    )

    assert run_sitemap_sync(str(sync_request.uuid)) == ProjectSyncStates.RUNNING
    assert run_sitemap_sync(str(sync_request.uuid)) == "noop"

    sync_request.refresh_from_db()
    assert sync_request.attempt_count == 1
    assert sync_request.total_count == 2
    assert sync_request.page_work.count() == 2
    assert dispatched == [str(sync_request.uuid)]


@pytest.mark.django_db
def test_retryable_sync_failure_uses_bounded_backoff(sync_request, monkeypatch, settings):
    settings.CRAWL_MAX_ATTEMPTS = 3
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: (_ for _ in ()).throw(
            SitemapParseError(SitemapParseErrorCode.FETCH_FAILED, retryable=True)
        ),
    )

    assert run_sitemap_sync(str(sync_request.uuid)) == ProjectSyncStates.QUEUED
    sync_request.refresh_from_db()
    assert sync_request.attempt_count == 1
    assert sync_request.next_attempt_at > timezone.now()
    assert sync_request.error_code == "fetch_failed"

    sync_request.attempt_count = 2
    sync_request.next_attempt_at = None
    sync_request.save(update_fields=["attempt_count", "next_attempt_at", "updated_at"])
    assert run_sitemap_sync(str(sync_request.uuid)) == ProjectSyncStates.FAILED


@pytest.mark.django_db
def test_suspended_project_cancels_sync_and_page_work(sync_request, monkeypatch):
    inventory = SitemapInventoryService.promote(
        project=sync_request.project,
        sync_request=sync_request,
        result=parse_result("a"),
    )
    work = PageCrawlWork.objects.create(
        sync_request=sync_request,
        candidate=inventory.candidates.get(),
    )
    sync_request.project.state = ProjectStates.SUSPENDED
    sync_request.project.save(update_fields=["state", "updated_at"])
    parse_called = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda *args: parse_called.append(True),
    )

    assert run_sitemap_sync(str(sync_request.uuid)) == "noop"
    sync_request.refresh_from_db()
    work.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.CANCELLED
    assert work.state == PageCrawlStates.CANCELLED
    assert parse_called == []


def _page_work(sync_request, path="a"):
    inventory = SitemapInventoryService.promote(
        project=sync_request.project,
        sync_request=sync_request,
        result=parse_result(path),
    )
    sync_request.state = ProjectSyncStates.RUNNING
    sync_request.save(update_fields=["state", "updated_at"])
    return PageCrawlWork.objects.create(
        sync_request=sync_request,
        candidate=inventory.candidates.get(),
    )


def _extraction(work):
    return HtmlExtraction(
        state=ExtractionStates.READY,
        final_url=work.candidate.normalized_url,
        canonical_url=work.candidate.normalized_url,
        http_status=200,
        title="Article",
        description="",
        language="en",
        text="Useful article text",
        noindex=False,
        source_bytes=100,
        text_chars=19,
        diagnostics={"canonical_rejected": False},
    )


@pytest.mark.django_db
def test_page_retry_then_success_finalizes_sync(sync_request, monkeypatch, settings):
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    work = _page_work(sync_request)
    monkeypatch.setattr(
        "apps.core.crawl_jobs._fetch_page",
        lambda work: (_ for _ in ()).throw(
            SafeFetchError(SafeFetchErrorCode.TIMEOUT, retryable=True)
        ),
    )

    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.QUEUED
    work.refresh_from_db()
    assert work.attempt_count == 1
    work.next_attempt_at = None
    work.save(update_fields=["next_attempt_at", "updated_at"])
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)

    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.SUCCEEDED
    sync_request.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.SUCCEEDED
    assert sync_request.succeeded_count == 1
    assert work.extraction.text == "Useful article text"


@pytest.mark.django_db
def test_page_retry_finishes_existing_extraction_without_refetch(
    sync_request,
    monkeypatch,
    settings,
):
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    work = _page_work(sync_request)
    extraction = _extraction(work)
    PageExtractionService.persist(work=work, extraction=extraction)
    monkeypatch.setattr(
        "apps.core.crawl_jobs._fetch_page",
        lambda work: pytest.fail("an existing extraction must not be fetched again"),
    )

    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.SUCCEEDED
    work.refresh_from_db()
    assert work.attempt_count == 1
    assert work.extraction.text == extraction.text


@pytest.mark.django_db
def test_mixed_terminal_page_outcomes_finalize_partial(sync_request, monkeypatch, settings):
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    first = _page_work(sync_request, "first")
    second_candidate = sync_request.sitemap_inventory.candidates.create(
        url="https://example.com/second",
        normalized_url="https://example.com/second",
    )
    second = PageCrawlWork.objects.create(
        sync_request=sync_request,
        candidate=second_candidate,
        max_attempts=1,
    )
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)
    assert run_page_crawl(str(first.uuid)) == PageCrawlStates.SUCCEEDED
    monkeypatch.setattr(
        "apps.core.crawl_jobs._fetch_page",
        lambda work: (_ for _ in ()).throw(SafeFetchError(SafeFetchErrorCode.HTTP_ERROR)),
    )

    assert run_page_crawl(str(second.uuid)) == PageCrawlStates.FAILED
    sync_request.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.PARTIAL
    assert sync_request.succeeded_count == 1
    assert sync_request.failed_count == 1


@pytest.mark.django_db
def test_terminal_gone_response_deactivates_but_transient_failure_does_not(
    sync_request,
    monkeypatch,
    settings,
):
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    first = _page_work(sync_request, "gone")
    PageExtractionService.persist(work=first, extraction=_extraction(first))
    article = ArticleIngestionService.ingest(work=first, queue_embedding=False)
    article.state = "active"
    article.is_active = True
    article.save(update_fields=["state", "is_active", "updated_at"])
    sync_request.project.active_article_count = 1
    sync_request.project.save(update_fields=["active_article_count", "updated_at"])
    first.state = PageCrawlStates.SUCCEEDED
    first.save(update_fields=["state", "updated_at"])
    sync_request.state = ProjectSyncStates.SUCCEEDED
    sync_request.save(update_fields=["state", "updated_at"])

    transient_sync = ProjectSyncRequest.objects.create(
        project=sync_request.project,
        sitemap_kind="urlset",
        idempotency_key="transient",
    )
    transient = _page_work(transient_sync, "gone")
    monkeypatch.setattr(
        "apps.core.crawl_jobs._fetch_page",
        lambda work: (_ for _ in ()).throw(
            SafeFetchError(SafeFetchErrorCode.TIMEOUT, retryable=True)
        ),
    )
    assert run_page_crawl(str(transient.uuid)) == PageCrawlStates.QUEUED
    article.refresh_from_db()
    assert article.is_active is True

    transient.state = PageCrawlStates.CANCELLED
    transient.save(update_fields=["state", "updated_at"])
    transient_sync.state = ProjectSyncStates.CANCELLED
    transient_sync.save(update_fields=["state", "updated_at"])
    gone_sync = ProjectSyncRequest.objects.create(
        project=sync_request.project,
        sitemap_kind="urlset",
        idempotency_key="gone",
    )
    gone = _page_work(gone_sync, "gone")
    monkeypatch.setattr(
        "apps.core.crawl_jobs._fetch_page",
        lambda work: (_ for _ in ()).throw(
            SafeFetchError(
                SafeFetchErrorCode.HTTP_ERROR,
                http_status=410,
            )
        ),
    )

    assert run_page_crawl(str(gone.uuid)) == PageCrawlStates.FAILED
    article.refresh_from_db()
    article.project.refresh_from_db()
    source = article.source_urls.get()
    attempt = gone.article_attempts.get()
    assert article.is_active is False
    assert article.state == "inactive"
    assert article.inactivity_reason == "http_410"
    assert article.content == "Useful article text"
    assert article.project.active_article_count == 0
    assert source.is_active is False
    assert attempt.http_status == 410


@pytest.mark.django_db
def test_noindex_removes_qdrant_point_and_keeps_postgres_history(
    sync_request,
    monkeypatch,
    settings,
):
    from apps.search.qdrant import ensure_article_collection, upsert_article

    settings.CITEGUILD_INDEXING_ENABLED = True
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    settings.EMBEDDING_DIMENSIONS = 3
    settings.EMBEDDING_MODEL = "test:whole-article"
    settings.QDRANT_COLLECTION = "test_lifecycle_articles"
    client = QdrantClient(location=":memory:")
    monkeypatch.setattr("apps.search.qdrant.get_qdrant_client", lambda: client)
    ensure_article_collection(client=client)
    first = _page_work(sync_request, "excluded")
    PageExtractionService.persist(work=first, extraction=_extraction(first))
    article = ArticleIngestionService.ingest(work=first, queue_embedding=False)
    ArticleEmbedding.objects.create(
        article=article,
        state="succeeded",
        vector=[1.0, 0.0, 0.0],
        content_hash=article.content_hash,
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
    )
    upsert_article(article=article, client=client)
    original_content = article.content
    first.state = PageCrawlStates.SUCCEEDED
    first.save(update_fields=["state", "updated_at"])
    sync_request.state = ProjectSyncStates.SUCCEEDED
    sync_request.save(update_fields=["state", "updated_at"])
    excluded_sync = ProjectSyncRequest.objects.create(
        project=sync_request.project,
        sitemap_kind="urlset",
        idempotency_key="excluded",
    )
    excluded = _page_work(excluded_sync, "excluded")
    noindex = _extraction(excluded)
    noindex = HtmlExtraction(
        state=ExtractionStates.NOINDEX,
        final_url=noindex.final_url,
        canonical_url=noindex.canonical_url,
        http_status=noindex.http_status,
        title=noindex.title,
        description=noindex.description,
        language=noindex.language,
        text="",
        noindex=True,
        source_bytes=noindex.source_bytes,
        text_chars=0,
        diagnostics=noindex.diagnostics,
    )
    PageExtractionService.persist(work=excluded, extraction=noindex)

    assert run_page_crawl(str(excluded.uuid)) == PageCrawlStates.SUCCEEDED
    article.refresh_from_db()
    assert article.state == "inactive"
    assert article.is_active is False
    assert article.inactivity_reason == "noindex"
    assert article.content == original_content
    assert (
        client.retrieve(
            settings.QDRANT_COLLECTION,
            ids=[str(article.qdrant_point_id)],
        )
        == []
    )


@pytest.mark.django_db
def test_initial_sync_becomes_searchable_and_rerun_is_idempotent(
    sync_request,
    monkeypatch,
    settings,
):
    from apps.search.qdrant import ensure_article_collection, semantic_search

    settings.CITEGUILD_INDEXING_ENABLED = True
    settings.EMBEDDING_DIMENSIONS = 3
    settings.EMBEDDING_MODEL = "test:whole-article"
    settings.QDRANT_COLLECTION = "test_initial_sync_articles"
    tracked = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.track_funnel_event",
        lambda *args, **kwargs: tracked.append((args, kwargs)),
    )
    client = QdrantClient(location=":memory:")
    monkeypatch.setattr("apps.search.qdrant.get_qdrant_client", lambda: client)
    monkeypatch.setattr(
        "apps.core.article_embeddings.PydanticEmbeddingClient.embed",
        lambda self, text, *, dimensions: EmbeddingResponse([1.0, 0.0, 0.0], 7),
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result("article"),
    )
    monkeypatch.setattr("apps.core.crawl_jobs.dispatch_page_work", lambda sync_uuid: 1)
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)
    ensure_article_collection(client=client)

    assert run_sitemap_sync(str(sync_request.uuid)) == ProjectSyncStates.RUNNING
    work = sync_request.page_work.get()
    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.SUCCEEDED

    sync_request.refresh_from_db()
    article = Article.objects.select_related("embedding").get()
    assert sync_request.state == ProjectSyncStates.SUCCEEDED
    assert (sync_request.total_count, sync_request.succeeded_count) == (1, 1)
    assert article.is_active is True
    assert tracked[0][0][1] == "citeguild_initial_index_completed"
    assert tracked[0][0][2]["active_articles"] == 1
    assert (
        semantic_search(
            [1.0, 0.0, 0.0],
            authorized_project_uuids={sync_request.project.uuid},
        )[0].article_uuid
        == article.uuid
    )

    rerun = ProjectSyncRequest.objects.create(
        project=sync_request.project,
        sitemap_kind="urlset",
        idempotency_key=f"rerun:{sync_request.project.uuid}",
    )
    assert run_sitemap_sync(str(rerun.uuid)) == ProjectSyncStates.RUNNING
    assert run_page_crawl(str(rerun.page_work.get().uuid)) == PageCrawlStates.SUCCEEDED

    records, _offset = client.scroll(
        settings.QDRANT_COLLECTION,
        limit=10,
        with_payload=False,
        with_vectors=False,
    )
    assert Article.objects.count() == 1
    assert ArticleEmbedding.objects.count() == 1
    assert len(records) == 1


@pytest.mark.django_db
def test_retryable_indexing_failure_is_visible_and_resumable(
    sync_request,
    monkeypatch,
    settings,
):
    settings.CITEGUILD_INDEXING_ENABLED = True
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    work = _page_work(sync_request)
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)
    attempts = []

    def flaky_index(article):
        attempts.append(article.uuid)
        if len(attempts) == 1:
            raise EmbeddingError("provider_unavailable", retryable=True)

    monkeypatch.setattr("apps.core.crawl_jobs._index_ready_article", flaky_index)

    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.QUEUED
    work.refresh_from_db()
    sync_request.refresh_from_db()
    assert work.error_code == "provider_unavailable"
    assert work.next_attempt_at is not None
    assert sync_request.state == ProjectSyncStates.RUNNING
    assert (sync_request.total_count, sync_request.queued_count) == (1, 1)

    work.next_attempt_at = None
    work.save(update_fields=["next_attempt_at", "updated_at"])
    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.SUCCEEDED
    sync_request.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.SUCCEEDED
    assert sync_request.succeeded_count == 1
    assert Article.objects.count() == 1
    assert work.extraction.text == "Useful article text"
    assert attempts[0] == attempts[1]


@pytest.mark.django_db
def test_nonretryable_indexing_failure_contributes_to_partial_progress(
    sync_request,
    monkeypatch,
    settings,
):
    from apps.search.qdrant import QdrantContractError

    settings.CITEGUILD_INDEXING_ENABLED = True
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    first = _page_work(sync_request, "first")
    second_candidate = sync_request.sitemap_inventory.candidates.create(
        url="https://example.com/second",
        normalized_url="https://example.com/second",
    )
    second = PageCrawlWork.objects.create(
        sync_request=sync_request,
        candidate=second_candidate,
    )
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)

    def index_or_reject(article):
        if article.original_url.endswith("/second"):
            raise QdrantContractError("collection_dimension_mismatch")

    monkeypatch.setattr("apps.core.crawl_jobs._index_ready_article", index_or_reject)

    assert run_page_crawl(str(first.uuid)) == PageCrawlStates.SUCCEEDED
    assert run_page_crawl(str(second.uuid)) == PageCrawlStates.FAILED
    sync_request.refresh_from_db()
    second.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.PARTIAL
    assert (sync_request.succeeded_count, sync_request.failed_count) == (1, 1)
    assert second.error_code == "collection_dimension_mismatch"


@pytest.mark.django_db
def test_project_suspension_after_ingestion_cancels_before_indexing(
    sync_request,
    monkeypatch,
    settings,
):
    from apps.core.article_ingestion import ArticleIngestionService

    settings.CITEGUILD_INDEXING_ENABLED = True
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    work = _page_work(sync_request)
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)
    original_ingest = ArticleIngestionService.ingest

    def ingest_then_suspend(*, work, queue_embedding=True):
        article = original_ingest(work=work, queue_embedding=queue_embedding)
        project = work.sync_request.project
        project.state = ProjectStates.SUSPENDED
        project.save(update_fields=["state", "updated_at"])
        return article

    monkeypatch.setattr(
        "apps.core.crawl_jobs.ArticleIngestionService.ingest",
        ingest_then_suspend,
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs._index_ready_article",
        lambda article: pytest.fail("a suspended project must not be indexed"),
    )

    assert run_page_crawl(str(work.uuid)) == PageCrawlStates.CANCELLED
    sync_request.refresh_from_db()
    work.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.CANCELLED
    assert work.state == PageCrawlStates.CANCELLED


@pytest.mark.django_db
def test_vector_publication_retries_if_prefetched_owner_changed(
    sync_request,
    monkeypatch,
):
    from apps.core.article_ingestion import ArticleIngestionService
    from apps.core.crawl_jobs import ArticleIndexingError

    work = _page_work(sync_request)
    PageExtractionService.persist(work=work, extraction=_extraction(work))
    article = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    other_user = get_user_model().objects.create_user(
        username="other-owner",
        email="other-owner@example.com",
    )
    other_user.profile.stripe_subscription_status = "active"
    other_user.profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    monkeypatch.setattr(
        "apps.core.crawl_jobs.EmbeddingService.embed_article",
        lambda self, *, article_uuid: None,
    )

    class StaleOwnerLookup:
        def get(self, **kwargs):
            return other_user.profile.pk

    monkeypatch.setattr(
        "apps.core.crawl_jobs.Project.objects.values_list",
        lambda *args, **kwargs: StaleOwnerLookup(),
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs.upsert_article",
        lambda **kwargs: pytest.fail("owner mismatch must stop publication"),
    )

    with pytest.raises(ArticleIndexingError) as raised:
        _index_ready_article(article)
    assert raised.value.code == "project_owner_changed"
    assert raised.value.retryable is True


@pytest.mark.django_db(transaction=True)
def test_vector_publication_serializes_subscription_changes(
    sync_request,
    monkeypatch,
):
    if connection.vendor != "postgresql":
        pytest.skip("row-lock concurrency is exercised by PostgreSQL CI")

    from apps.core.article_ingestion import ArticleIngestionService
    from apps.core.models import Profile

    work = _page_work(sync_request)
    PageExtractionService.persist(work=work, extraction=_extraction(work))
    article = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    owner_id = sync_request.project.owner_id
    monkeypatch.setattr(
        "apps.core.crawl_jobs.EmbeddingService.embed_article",
        lambda self, *, article_uuid: None,
    )
    publication_entered = Event()
    publication_release = Event()
    subscription_updated = Event()
    thread_errors = []

    def held_upsert(*, article):
        publication_entered.set()
        if not publication_release.wait(timeout=5):
            raise TimeoutError("test did not release publication")

    monkeypatch.setattr("apps.core.crawl_jobs.upsert_article", held_upsert)

    def publish():
        close_old_connections()
        try:
            _index_ready_article(article)
        except Exception as error:  # pragma: no cover - asserted in parent thread
            thread_errors.append(error)
        finally:
            close_old_connections()

    def cancel_subscription():
        close_old_connections()
        try:
            with transaction.atomic():
                owner = Profile.objects.select_for_update().get(pk=owner_id)
                owner.stripe_subscription_status = "canceled"
                owner.save(update_fields=["stripe_subscription_status", "updated_at"])
            subscription_updated.set()
        except Exception as error:  # pragma: no cover - asserted in parent thread
            thread_errors.append(error)
        finally:
            close_old_connections()

    publisher = Thread(target=publish)
    publisher.start()
    assert publication_entered.wait(timeout=5)
    canceller = Thread(target=cancel_subscription)
    canceller.start()

    assert subscription_updated.wait(timeout=0.25) is False
    publication_release.set()
    publisher.join(timeout=5)
    canceller.join(timeout=5)

    assert publisher.is_alive() is False
    assert canceller.is_alive() is False
    assert subscription_updated.is_set()
    assert thread_errors == []


@pytest.mark.django_db
def test_per_site_concurrency_defers_extra_work(sync_request, settings):
    settings.CRAWL_PER_SITE_CONCURRENCY = 1
    first = _page_work(sync_request, "first")
    second_candidate = sync_request.sitemap_inventory.candidates.create(
        url="https://example.com/second",
        normalized_url="https://example.com/second",
    )
    second = PageCrawlWork.objects.create(
        sync_request=sync_request,
        candidate=second_candidate,
        broker_task_id="broker-2",
    )
    first.state = PageCrawlStates.RUNNING
    first.save(update_fields=["state", "updated_at"])

    assert _claim_page_work(second.uuid) is None
    second.refresh_from_db()
    assert second.state == PageCrawlStates.QUEUED
    assert second.broker_task_id == ""


@pytest.mark.django_db
def test_dispatch_limits_brokered_work_to_available_site_slots(
    sync_request,
    monkeypatch,
    settings,
):
    settings.CRAWL_PER_SITE_CONCURRENCY = 2
    first = _page_work(sync_request, "first")
    first.state = PageCrawlStates.RUNNING
    first.save(update_fields=["state", "updated_at"])
    for path in ("second", "third", "fourth"):
        candidate = sync_request.sitemap_inventory.candidates.create(
            url=f"https://example.com/{path}",
            normalized_url=f"https://example.com/{path}",
        )
        PageCrawlWork.objects.create(sync_request=sync_request, candidate=candidate)
    published = []

    def publish(*args, **kwargs):
        published.append((args, kwargs))
        return f"broker-{len(published)}"

    monkeypatch.setattr("apps.core.crawl_jobs.async_task", publish)

    assert dispatch_page_work(str(sync_request.uuid)) == 1
    assert len(published) == 1
    assert (
        PageCrawlWork.objects.filter(
            sync_request=sync_request,
            state=PageCrawlStates.QUEUED,
        )
        .exclude(broker_task_id="")
        .count()
        == 1
    )


@pytest.mark.django_db
def test_completed_page_refills_available_site_slot(sync_request, monkeypatch, settings):
    settings.CRAWL_PER_SITE_CONCURRENCY = 1
    first = _page_work(sync_request, "first")
    candidate = sync_request.sitemap_inventory.candidates.create(
        url="https://example.com/second",
        normalized_url="https://example.com/second",
    )
    PageCrawlWork.objects.create(sync_request=sync_request, candidate=candidate)
    monkeypatch.setattr("apps.core.crawl_jobs._fetch_page", _extraction)
    monkeypatch.setattr("apps.core.crawl_jobs._index_ready_article", lambda article: None)
    refills = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.dispatch_page_work",
        lambda sync_uuid: refills.append(sync_uuid) or 1,
    )

    assert run_page_crawl(str(first.uuid)) == PageCrawlStates.SUCCEEDED
    assert refills == [sync_request.uuid]


@pytest.mark.django_db
def test_recovery_requeues_stale_worker_state(sync_request, monkeypatch, settings):
    settings.CRAWL_STALE_AFTER_SECONDS = 60
    work = _page_work(sync_request)
    old = timezone.now() - timedelta(minutes=5)
    sync_request.state = ProjectSyncStates.RUNNING
    sync_request.started_at = old
    sync_request.save(update_fields=["state", "started_at", "updated_at"])
    work.state = PageCrawlStates.RUNNING
    work.started_at = old
    work.save(update_fields=["state", "started_at", "updated_at"])
    enqueued = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.enqueue_sitemap_sync",
        lambda sync_uuid: enqueued.append(sync_uuid) or "task",
    )

    result = recover_crawl_jobs()

    sync_request.refresh_from_db()
    work.refresh_from_db()
    assert result["stale_syncs"] == 1
    assert result["stale_pages"] == 1
    assert sync_request.state == ProjectSyncStates.QUEUED
    assert work.state == PageCrawlStates.QUEUED
    assert enqueued == [sync_request.uuid]


@pytest.mark.django_db
def test_recovery_clears_stale_queued_broker_reservations(sync_request, monkeypatch, settings):
    settings.CRAWL_STALE_AFTER_SECONDS = 60
    work = _page_work(sync_request)
    old = timezone.now() - timedelta(minutes=5)
    PageCrawlWork.objects.filter(pk=work.pk).update(
        broker_task_id="broker-task-that-no-longer-exists",
        updated_at=old,
    )
    dispatched = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.dispatch_page_work",
        lambda sync_uuid: dispatched.append(sync_uuid) or 1,
    )

    result = recover_crawl_jobs()

    work.refresh_from_db()
    assert result["stale_page_reservations"] == 1
    assert work.state == PageCrawlStates.QUEUED
    assert work.broker_task_id == ""
    assert dispatched == [str(sync_request.uuid)]


@pytest.mark.django_db
def test_recovery_finalizes_completed_page_work(sync_request, monkeypatch):
    work = _page_work(sync_request)
    work.state = PageCrawlStates.SUCCEEDED
    work.completed_at = timezone.now()
    work.save(update_fields=["state", "completed_at", "updated_at"])
    monkeypatch.setattr("apps.core.crawl_jobs.dispatch_page_work", lambda sync_uuid: 0)

    recover_crawl_jobs()

    sync_request.refresh_from_db()
    assert sync_request.state == ProjectSyncStates.SUCCEEDED


@pytest.mark.django_db
def test_recovery_schedule_is_named_and_idempotent(monkeypatch):
    monkeypatch.setattr(
        "apps.core.management.commands.ensure_crawl_schedules.recover_crawl_jobs",
        lambda: {},
    )

    call_command("ensure_crawl_schedules")
    call_command("ensure_crawl_schedules")

    schedule = Schedule.objects.get(name="citeguild-crawl-recovery")
    assert schedule.func == "apps.core.crawl_jobs.recover_crawl_jobs"
    assert schedule.schedule_type == Schedule.MINUTES
    assert schedule.minutes == 5
