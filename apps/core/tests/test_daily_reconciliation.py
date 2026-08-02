from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest
from django.core.management import call_command
from django.db import close_old_connections, connection
from django_q.models import Schedule

from apps.core.choices import (
    ArticleStates,
    ExtractionStates,
    ProjectStates,
    ProjectSyncKinds,
    ProjectSyncStates,
)
from apps.core.crawl_jobs import (
    RECONCILIATION_TASK,
    reconciliation_due_at,
    retry_project_sync,
    schedule_due_sitemap_reconciliations,
    run_sitemap_sync,
)
from apps.core.models import Article, ArticleSourceURL, PageCrawlWork, Project, ProjectSyncRequest
from apps.core.projects import ProjectService
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseError,
    SitemapParseErrorCode,
    SitemapParseResult,
)


def create_project(profile, *, host="example.com"):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    return ProjectService.create(
        owner=profile,
        name=host,
        sitemap_url=f"https://{host}/sitemap.xml",
    )


def completed_inventory(project, *, completed_at, candidates):
    sync = ProjectSyncRequest.objects.create(
        project=project,
        kind=ProjectSyncKinds.INITIAL,
        state=ProjectSyncStates.SUCCEEDED,
        sitemap_kind="urlset",
        idempotency_key=f"completed:{project.uuid}",
        completed_at=completed_at,
    )
    result = SitemapParseResult(
        tuple(ParsedCandidate(url, url, lastmod) for url, lastmod in candidates),
        SitemapDiagnostics(1, len(candidates), len(candidates), 0, 0, 0, 0),
    )
    inventory = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=result,
    )
    project.last_sync_uuid = sync.uuid
    project.last_sync_at = completed_at
    project.save(update_fields=["last_sync_uuid", "last_sync_at", "updated_at"])
    return inventory


def daily_sync(project, *, key="daily:test"):
    return ProjectSyncRequest.objects.create(
        project=project,
        kind=ProjectSyncKinds.DAILY,
        sitemap_kind="urlset",
        idempotency_key=key,
    )


def parse_result(*candidates):
    return SitemapParseResult(
        tuple(ParsedCandidate(url, url, lastmod) for url, lastmod in candidates),
        SitemapDiagnostics(1, len(candidates), len(candidates), 0, 0, 0, 0),
    )


def create_article_source(project, *, url, fetched_at):
    article = Article.objects.create(
        project=project,
        original_url=url,
        final_url=url,
        canonical_url=url,
        normalized_canonical_url=url,
        extraction_state=ExtractionStates.READY,
        state=ArticleStates.ACTIVE,
        is_active=True,
        first_seen_at=fetched_at,
        last_seen_at=fetched_at,
        last_fetched_at=fetched_at,
        last_changed_at=fetched_at,
    )
    ArticleSourceURL.objects.create(
        project=project,
        article=article,
        normalized_url=url,
        first_seen_at=fetched_at,
        last_seen_at=fetched_at,
    )
    return article


@pytest.mark.django_db
def test_reconciliation_due_at_is_stable_and_jittered(profile, settings):
    settings.RECONCILE_INTERVAL_HOURS = 24
    project = create_project(profile)
    anchor = datetime(2026, 8, 1, tzinfo=UTC)

    first = reconciliation_due_at(project.uuid, anchor)
    second = reconciliation_due_at(project.uuid, anchor)

    assert first == second
    assert anchor + timedelta(hours=24) <= first < anchor + timedelta(hours=25)


@pytest.mark.django_db
def test_due_scheduler_claims_each_site_once_and_keeps_broker_failure_visible(
    profile, monkeypatch, settings
):
    settings.RECONCILE_INTERVAL_HOURS = 24
    project = create_project(profile)
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    completed_inventory(
        project,
        completed_at=anchor,
        candidates=(("https://example.com/post", "2026-08-01"),),
    )
    due_at = reconciliation_due_at(project.uuid, anchor)
    enqueued = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.enqueue_sitemap_sync_safely",
        lambda sync_uuid: enqueued.append(sync_uuid) or "",
    )

    before = schedule_due_sitemap_reconciliations(now=due_at - timedelta(microseconds=1))
    first = schedule_due_sitemap_reconciliations(now=due_at)
    second = schedule_due_sitemap_reconciliations(now=due_at)

    assert before["created_syncs"] == 0
    assert first == {"due_projects": 1, "created_syncs": 1, "enqueued_syncs": 0}
    assert second["created_syncs"] == 0
    sync = ProjectSyncRequest.objects.get(project=project, kind=ProjectSyncKinds.DAILY)
    assert sync.state == ProjectSyncStates.QUEUED
    assert sync.broker_task_id == ""
    assert enqueued == [sync.uuid]
    project.refresh_from_db()
    assert project.current_sync_uuid == sync.uuid


@pytest.mark.django_db(transaction=True)
def test_concurrent_due_schedulers_create_one_sync(profile, monkeypatch, settings):
    if connection.vendor != "postgresql":
        pytest.skip("row-lock concurrency is exercised by PostgreSQL CI")
    settings.RECONCILE_INTERVAL_HOURS = 24
    project = create_project(profile)
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    completed_inventory(project, completed_at=anchor, candidates=())
    due_at = reconciliation_due_at(project.uuid, anchor)
    barrier = Barrier(2)
    errors = []
    results = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.enqueue_sitemap_sync_safely",
        lambda sync_uuid: "task",
    )

    def schedule():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            results.append(schedule_due_sitemap_reconciliations(now=due_at))
        except Exception as error:  # pragma: no cover - asserted in parent thread
            errors.append(error)
        finally:
            close_old_connections()

    threads = [Thread(target=schedule), Thread(target=schedule)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert ProjectSyncRequest.objects.filter(
        project=project,
        kind=ProjectSyncKinds.DAILY,
    ).count() == 1


@pytest.mark.django_db
def test_due_scheduler_skips_suspended_and_unpaid_sites(profile, django_user_model, settings):
    settings.RECONCILE_INTERVAL_HOURS = 24
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    suspended = create_project(profile, host="suspended.example")
    completed_inventory(suspended, completed_at=anchor, candidates=())
    suspended.state = ProjectStates.SUSPENDED
    suspended.save(update_fields=["state", "updated_at"])

    unpaid_user = django_user_model.objects.create_user(
        username="unpaid",
        email="unpaid@example.com",
        password="password123",
    )
    unpaid = create_project(unpaid_user.profile, host="unpaid.example")
    completed_inventory(unpaid, completed_at=anchor, candidates=())
    unpaid_user.profile.stripe_subscription_status = "churned"
    unpaid_user.profile.save(update_fields=["stripe_subscription_status", "updated_at"])

    result = schedule_due_sitemap_reconciliations(
        now=anchor + timedelta(hours=25),
    )

    assert result["created_syncs"] == 0
    assert not ProjectSyncRequest.objects.filter(kind=ProjectSyncKinds.DAILY).exists()


@pytest.mark.django_db
def test_due_scheduler_enforces_batch_limit(profile, monkeypatch, settings):
    settings.RECONCILE_INTERVAL_HOURS = 24
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    projects = [
        create_project(profile, host="one.example"),
        create_project(profile, host="two.example"),
    ]
    for project in projects:
        completed_inventory(project, completed_at=anchor, candidates=())
    monkeypatch.setattr(
        "apps.core.crawl_jobs.enqueue_sitemap_sync_safely",
        lambda sync_uuid: "task",
    )

    result = schedule_due_sitemap_reconciliations(
        now=anchor + timedelta(hours=25),
        limit=1,
    )

    assert result["created_syncs"] == 1
    assert ProjectSyncRequest.objects.filter(kind=ProjectSyncKinds.DAILY).count() == 1


@pytest.mark.django_db(transaction=True)
def test_due_scheduler_runs_daily_task_through_django_q_sync_boundary(
    profile, monkeypatch, settings
):
    settings.RECONCILE_INTERVAL_HOURS = 24
    settings.CRAWL_MAX_ATTEMPTS = 3
    monkeypatch.setattr("django_q.tasks.Conf.SYNC", True)
    project = create_project(profile)
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    completed_inventory(project, completed_at=anchor, candidates=())
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result(),
    )

    result = schedule_due_sitemap_reconciliations(
        now=anchor + timedelta(hours=25),
    )

    assert result == {"due_projects": 1, "created_syncs": 1, "enqueued_syncs": 1}
    sync = ProjectSyncRequest.objects.get(project=project, kind=ProjectSyncKinds.DAILY)
    assert sync.state == ProjectSyncStates.SUCCEEDED
    assert sync.completed_at is not None


@pytest.mark.django_db
def test_manual_retry_creates_one_request_and_republishes_existing_work(profile, monkeypatch):
    project = create_project(profile)
    completed_inventory(
        project,
        completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        candidates=(),
    )
    project.last_error_code = "fetch_failed"
    project.save(update_fields=["last_error_code", "updated_at"])
    enqueued = []
    monkeypatch.setattr(
        "apps.core.crawl_jobs.enqueue_sitemap_sync_safely",
        lambda sync_uuid: enqueued.append(sync_uuid) or "task",
    )

    first = retry_project_sync(owner=profile, project_uuid=project.uuid)
    second = retry_project_sync(owner=profile, project_uuid=project.uuid)

    assert first.pk == second.pk
    assert first.kind == ProjectSyncKinds.MANUAL
    assert first.state == ProjectSyncStates.QUEUED
    assert enqueued == [first.uuid, first.uuid]
    project.refresh_from_db()
    assert project.current_sync_uuid == first.uuid
    assert project.last_error_code == ""


@pytest.mark.django_db
def test_manual_retry_cannot_cross_owner_boundary(profile, django_user_model):
    project = create_project(profile)
    completed_inventory(
        project,
        completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        candidates=(),
    )
    other_user = django_user_model.objects.create_user(
        username="other-owner",
        email="other-owner@example.com",
        password="password123",
    )

    with pytest.raises(Project.DoesNotExist):
        retry_project_sync(owner=other_user.profile, project_uuid=project.uuid)


@pytest.mark.django_db
def test_terminal_daily_sitemap_failure_remains_visible_on_project(
    profile, monkeypatch, settings
):
    settings.CRAWL_MAX_ATTEMPTS = 1
    project = create_project(profile)
    completed_inventory(
        project,
        completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        candidates=(),
    )
    sync = daily_sync(project)
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: (_ for _ in ()).throw(
            SitemapParseError(SitemapParseErrorCode.FETCH_FAILED)
        ),
    )

    assert run_sitemap_sync(str(sync.uuid)) == ProjectSyncStates.FAILED

    project.refresh_from_db()
    assert project.last_error_code == SitemapParseErrorCode.FETCH_FAILED.value
    assert project.current_sync_uuid is None
    assert project.current_sync_started_at is None


@pytest.mark.django_db
def test_daily_sync_only_crawls_new_and_lastmod_changed_candidates(
    profile, monkeypatch, settings
):
    settings.CRAWL_MAX_ATTEMPTS = 3
    project = create_project(profile)
    completed_inventory(
        project,
        completed_at=datetime(2026, 8, 1, tzinfo=UTC),
        candidates=(
            ("https://example.com/same", "2026-08-01"),
            ("https://example.com/changed", "2026-08-01"),
        ),
    )
    create_article_source(
        project,
        url="https://example.com/same",
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    create_article_source(
        project,
        url="https://example.com/changed",
        fetched_at=datetime(2026, 8, 1, tzinfo=UTC),
    )
    sync = daily_sync(project)
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result(
            ("https://example.com/same", "2026-08-01"),
            ("https://example.com/changed", "2026-08-02"),
            ("https://example.com/new", ""),
        ),
    )
    monkeypatch.setattr("apps.core.crawl_jobs.dispatch_page_work", lambda sync_uuid: 2)

    assert run_sitemap_sync(str(sync.uuid)) == ProjectSyncStates.RUNNING

    assert set(
        PageCrawlWork.objects.filter(sync_request=sync).values_list(
            "candidate__normalized_url", flat=True
        )
    ) == {"https://example.com/changed", "https://example.com/new"}


@pytest.mark.django_db
def test_unchanged_daily_sync_skips_page_fetch_and_updates_sitemap_observation(
    profile, monkeypatch, settings
):
    settings.CRAWL_MAX_ATTEMPTS = 3
    project = create_project(profile)
    anchor = datetime(2026, 8, 1, tzinfo=UTC)
    completed_inventory(
        project,
        completed_at=anchor,
        candidates=(("https://example.com/same", "2026-08-01"),),
    )
    create_article_source(
        project,
        url="https://example.com/same",
        fetched_at=anchor,
    )
    sync = daily_sync(project)
    now = anchor + timedelta(days=1)
    monkeypatch.setattr("apps.core.crawl_jobs.timezone.now", lambda: now)
    monkeypatch.setattr(
        "apps.core.article_ingestion.timezone.now",
        lambda: now,
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result(("https://example.com/same", "2026-08-01")),
    )

    assert run_sitemap_sync(str(sync.uuid)) == ProjectSyncStates.SUCCEEDED

    assert not PageCrawlWork.objects.filter(sync_request=sync).exists()
    source = ArticleSourceURL.objects.get(project=project)
    assert source.last_seen_at == now
    assert source.last_seen_sync == sync


@pytest.mark.django_db
def test_daily_sync_rechecks_unchanged_candidate_when_article_is_stale(
    profile, monkeypatch, settings
):
    settings.CRAWL_MAX_ATTEMPTS = 3
    settings.RECONCILE_INTERVAL_HOURS = 24
    project = create_project(profile)
    anchor = datetime(2026, 7, 20, tzinfo=UTC)
    completed_inventory(
        project,
        completed_at=anchor,
        candidates=(("https://example.com/stale", ""),),
    )
    create_article_source(
        project,
        url="https://example.com/stale",
        fetched_at=anchor,
    )
    sync = daily_sync(project)
    monkeypatch.setattr(
        "apps.core.crawl_jobs.timezone.now",
        lambda: anchor + timedelta(days=8),
    )
    monkeypatch.setattr(
        "apps.core.crawl_jobs.SitemapParser.parse",
        lambda self, url: parse_result(("https://example.com/stale", "")),
    )
    monkeypatch.setattr("apps.core.crawl_jobs.dispatch_page_work", lambda sync_uuid: 1)

    assert run_sitemap_sync(str(sync.uuid)) == ProjectSyncStates.RUNNING
    assert PageCrawlWork.objects.filter(sync_request=sync).count() == 1


@pytest.mark.django_db
def test_reconciliation_schedule_is_named_and_idempotent(monkeypatch):
    monkeypatch.setattr(
        "apps.core.management.commands.ensure_crawl_schedules.recover_crawl_jobs",
        lambda: {},
    )

    call_command("ensure_crawl_schedules")
    call_command("ensure_crawl_schedules")

    schedule = Schedule.objects.get(name="citeguild-daily-reconciliation")
    assert schedule.func == RECONCILIATION_TASK
    assert schedule.schedule_type == Schedule.MINUTES
    assert schedule.minutes == 15
    assert Schedule.objects.filter(name="citeguild-daily-reconciliation").count() == 1
