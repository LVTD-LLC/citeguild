from datetime import timedelta

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from django_q.models import Schedule

from apps.core.choices import (
    ExtractionStates,
    PageCrawlStates,
    ProjectStates,
    ProjectSyncStates,
)
from apps.core.crawl_jobs import (
    _claim_page_work,
    enqueue_sitemap_sync,
    enqueue_sitemap_sync_safely,
    recover_crawl_jobs,
    run_page_crawl,
    run_sitemap_sync,
)
from apps.core.html_extraction import HtmlExtraction, PageExtractionService
from apps.core.models import PageCrawlWork, ProjectSyncRequest
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
