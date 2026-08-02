"""Durable, idempotent Django Q2 crawl orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import DateTimeField, F, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone
from django_q.tasks import async_task
from qdrant_client.http.exceptions import ApiException

from apps.core.article_embeddings import EmbeddingError, EmbeddingService
from apps.core.article_ingestion import (
    ArticleIngestionService,
    ArticleLifecycleService,
    ArticlePersistenceError,
    CrawlAttemptService,
)
from apps.core.choices import (
    ExtractionStates,
    PageCrawlStates,
    ProjectStates,
    ProjectSyncKinds,
    ProjectSyncStates,
)
from apps.core.html_extraction import (
    HtmlExtraction,
    HtmlExtractionError,
    PageExtractionService,
    extract_article,
)
from apps.core.models import (
    Article,
    ArticleSourceURL,
    PageCrawlWork,
    PageExtractionResult,
    Profile,
    Project,
    ProjectSyncRequest,
    SitemapCandidate,
)
from apps.core.projects import normalize_sitemap_url
from apps.core.safe_fetch import SafeFetchClient, SafeFetchError
from apps.core.sitemap_parser import (
    SitemapInventoryService,
    SitemapParseError,
    SitemapParser,
)
from apps.search.qdrant import QdrantContractError, upsert_article

logger = logging.getLogger(__name__)

RUN_SYNC_TASK = "apps.core.crawl_jobs.run_sitemap_sync"
RUN_PAGE_TASK = "apps.core.crawl_jobs.run_page_crawl"
DISPATCH_TASK = "apps.core.crawl_jobs.dispatch_page_work"
RECOVERY_TASK = "apps.core.crawl_jobs.recover_crawl_jobs"
RECONCILIATION_TASK = "apps.core.crawl_jobs.schedule_due_sitemap_reconciliations"

_SYNC_TERMINAL = {
    ProjectSyncStates.SUCCEEDED,
    ProjectSyncStates.PARTIAL,
    ProjectSyncStates.FAILED,
    ProjectSyncStates.CANCELLED,
}
_PAGE_TERMINAL = {
    PageCrawlStates.SUCCEEDED,
    PageCrawlStates.FAILED,
    PageCrawlStates.CANCELLED,
}


def _task_id(value) -> str:
    return str(value or "")


def enqueue_sitemap_sync(sync_uuid) -> str:
    """Publish one logical sync task; duplicate callers reuse its durable marker."""
    with transaction.atomic():
        sync_request = ProjectSyncRequest.objects.select_for_update().get(uuid=sync_uuid)
        if sync_request.state in _SYNC_TERMINAL or sync_request.broker_task_id:
            return sync_request.broker_task_id
        if sync_request.next_attempt_at and sync_request.next_attempt_at > timezone.now():
            return ""
        sync_request.broker_task_id = "dispatching"
        sync_request.save(update_fields=["broker_task_id", "updated_at"])
        project_uuid = sync_request.project.uuid

    try:
        broker_task_id = async_task(
            RUN_SYNC_TASK,
            str(sync_uuid),
            q_options={"group": f"crawl:{project_uuid}"},
        )
    except Exception:
        ProjectSyncRequest.objects.filter(uuid=sync_uuid, broker_task_id="dispatching").update(
            broker_task_id=""
        )
        raise
    ProjectSyncRequest.objects.filter(uuid=sync_uuid, broker_task_id="dispatching").update(
        broker_task_id=_task_id(broker_task_id)
    )
    return _task_id(broker_task_id)


def enqueue_sitemap_sync_safely(sync_uuid) -> str:
    """Keep committed intent recoverable when the broker is temporarily unavailable."""
    try:
        return enqueue_sitemap_sync(sync_uuid)
    except Exception as error:
        logger.error(
            "crawl.sync.enqueue_failed",
            extra={"sync_uuid": str(sync_uuid), "error.type": type(error).__name__},
        )
        return ""


def _cancel_sync(sync_request: ProjectSyncRequest) -> str:
    now = timezone.now()
    sync_request.state = ProjectSyncStates.CANCELLED
    sync_request.error_code = "project_ineligible"
    sync_request.completed_at = now
    sync_request.broker_task_id = ""
    sync_request.save(
        update_fields=[
            "state",
            "error_code",
            "completed_at",
            "broker_task_id",
            "updated_at",
        ]
    )
    PageCrawlWork.objects.filter(sync_request=sync_request).exclude(
        state__in=_PAGE_TERMINAL
    ).update(
        state=PageCrawlStates.CANCELLED,
        completed_at=now,
        broker_task_id="",
        error_code="project_ineligible",
    )
    Project.objects.filter(
        pk=sync_request.project_id,
        current_sync_uuid=sync_request.uuid,
    ).update(
        current_sync_uuid=None,
        current_sync_started_at=None,
        last_error_code="project_ineligible",
    )
    logger.info(
        "crawl.sync.cancelled",
        extra={
            "event.name": "crawl.sync.cancelled",
            "sync_uuid": str(sync_request.uuid),
            "project_uuid": str(sync_request.project.uuid),
            "error.type": "project_ineligible",
            "operation.status": "cancelled",
            "outcome": "failure",
        },
    )
    return sync_request.state


def _claim_sync(sync_uuid) -> ProjectSyncRequest | None:
    with transaction.atomic():
        sync_request = (
            ProjectSyncRequest.objects.select_for_update()
            .select_related("project__owner__user")
            .get(uuid=sync_uuid)
        )
        if sync_request.state in _SYNC_TERMINAL:
            return None
        if not sync_request.project.is_sync_eligible:
            _cancel_sync(sync_request)
            return None
        if sync_request.state == ProjectSyncStates.RUNNING:
            return None
        now = timezone.now()
        if sync_request.next_attempt_at and sync_request.next_attempt_at > now:
            sync_request.broker_task_id = ""
            sync_request.save(update_fields=["broker_task_id", "updated_at"])
            return None
        sync_request.state = ProjectSyncStates.RUNNING
        sync_request.attempt_count += 1
        sync_request.max_attempts = settings.CRAWL_MAX_ATTEMPTS
        sync_request.started_at = now
        sync_request.completed_at = None
        sync_request.next_attempt_at = None
        sync_request.error_code = ""
        sync_request.broker_task_id = ""
        sync_request.save()
        Project.objects.filter(pk=sync_request.project_id).update(
            current_sync_uuid=sync_request.uuid,
            current_sync_started_at=now,
            last_error_code="",
        )
        return sync_request


def _retry_delay(identifier, attempt_count: int) -> timedelta:
    base_seconds = min(30 * (2 ** max(attempt_count - 1, 0)), 1800)
    jitter_seconds = identifier.int % max(base_seconds // 4, 1)
    return timedelta(seconds=base_seconds + jitter_seconds)


def reconciliation_due_at(project_uuid, anchor: datetime) -> datetime:
    """Return a stable per-site due time after the configured interval."""
    interval = timedelta(hours=settings.RECONCILE_INTERVAL_HOURS)
    jitter_window_seconds = max(min(int(interval.total_seconds() // 24), 3600), 1)
    jitter_seconds = project_uuid.int % jitter_window_seconds
    return anchor + interval + timedelta(seconds=jitter_seconds)


def _reconciliation_anchor(project: Project):
    latest_daily_created_at = (
        ProjectSyncRequest.objects.filter(
            project=project,
            kind=ProjectSyncKinds.DAILY,
        )
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    if latest_daily_created_at and latest_daily_created_at > project.last_sync_at:
        return latest_daily_created_at
    return project.last_sync_at


def _claim_due_reconciliation(project_id: int, *, now: datetime) -> tuple[bool, UUID | None]:
    try:
        with transaction.atomic():
            project = (
                Project.objects.select_for_update(
                    of=("self",),
                    skip_locked=connection.features.has_select_for_update_skip_locked,
                )
                .select_related(
                    "owner__user",
                    "active_sitemap_inventory__sync_request",
                )
                .filter(pk=project_id)
                .first()
            )
            if project is None or (
                project.state != ProjectStates.ACTIVE or not project.owner.has_active_subscription
            ):
                return False, None
            due_at = reconciliation_due_at(project.uuid, _reconciliation_anchor(project))
            if due_at > now:
                return False, None
            if ProjectSyncRequest.objects.filter(
                project=project,
                state__in=(ProjectSyncStates.QUEUED, ProjectSyncStates.RUNNING),
            ).exists():
                return True, None
            sync_request, created = ProjectSyncRequest.objects.get_or_create(
                idempotency_key=f"daily:{project.uuid}:{int(due_at.timestamp())}",
                defaults={
                    "project": project,
                    "kind": ProjectSyncKinds.DAILY,
                    "sitemap_kind": project.active_sitemap_inventory.sync_request.sitemap_kind,
                },
            )
            if not created:
                return True, None
            project.current_sync_uuid = sync_request.uuid
            project.current_sync_started_at = None
            project.last_error_code = ""
            project.save(
                update_fields=[
                    "current_sync_uuid",
                    "current_sync_started_at",
                    "last_error_code",
                    "updated_at",
                ]
            )
            return True, sync_request.uuid
    except IntegrityError:
        # Database constraints are the final guard when scheduler claims race.
        return False, None


def schedule_due_sitemap_reconciliations(*, now=None, limit: int = 100) -> dict[str, int]:
    """Claim and enqueue a bounded batch of due paid, active sites."""
    now = now or timezone.now()
    limit = max(1, min(int(limit), 100))
    interval = timedelta(hours=settings.RECONCILE_INTERVAL_HOURS)
    eligible_owner = Q(owner__stripe_subscription_status__in=("active", "past_due"))
    if settings.ENVIRONMENT == "prod":
        eligible_owner |= Q(owner__user__is_superuser=True)
    latest_daily_created_at = Subquery(
        ProjectSyncRequest.objects.filter(
            project_id=OuterRef("pk"),
            kind=ProjectSyncKinds.DAILY,
        )
        .order_by("-created_at")
        .values("created_at")[:1],
        output_field=DateTimeField(),
    )
    candidate_ids = list(
        Project.objects.annotate(
            latest_daily_created_at=latest_daily_created_at,
            reconciliation_anchor=Greatest(
                F("last_sync_at"),
                Coalesce(latest_daily_created_at, F("last_sync_at")),
            ),
        )
        .filter(
            eligible_owner,
            state=ProjectStates.ACTIVE,
            last_sync_at__isnull=False,
            reconciliation_anchor__lte=now - interval,
            active_sitemap_inventory__isnull=False,
        )
        .order_by("reconciliation_anchor", "id")
        .values_list("id", flat=True)[: limit * 5]
    )
    due_projects = 0
    created_syncs = 0
    enqueued_syncs = 0

    for project_id in candidate_ids:
        if created_syncs >= limit:
            break
        is_due, sync_uuid = _claim_due_reconciliation(project_id, now=now)
        due_projects += int(is_due)
        if sync_uuid is None:
            continue
        created_syncs += 1
        if enqueue_sitemap_sync_safely(sync_uuid):
            enqueued_syncs += 1

    logger.info(
        "crawl.reconciliation.scheduled",
        extra={
            "event.name": "crawl.reconciliation.scheduled",
            "due_projects": due_projects,
            "created_syncs": created_syncs,
            "enqueued_syncs": enqueued_syncs,
            "operation.status": "completed",
            "outcome": "success",
        },
    )
    return {
        "due_projects": due_projects,
        "created_syncs": created_syncs,
        "enqueued_syncs": enqueued_syncs,
    }


def retry_project_sync(*, owner: Profile, project_uuid) -> ProjectSyncRequest:
    """Create or republish one owner-scoped manual sync request."""
    with transaction.atomic():
        project = (
            Project.objects.select_for_update(of=("self",))
            .select_related("owner__user", "active_sitemap_inventory__sync_request")
            .get(owner=owner, uuid=project_uuid)
        )
        if project.state != ProjectStates.ACTIVE or not project.owner.has_active_subscription:
            raise PermissionDenied("This site is not eligible for synchronization.")
        sync_request = (
            ProjectSyncRequest.objects.filter(
                project=project,
                state__in=(ProjectSyncStates.QUEUED, ProjectSyncStates.RUNNING),
            )
            .order_by("created_at")
            .first()
        )
        if sync_request is None:
            latest = project.sync_requests.order_by("-created_at").first()
            sitemap_kind = (
                project.active_sitemap_inventory.sync_request.sitemap_kind
                if project.active_sitemap_inventory_id
                else latest.sitemap_kind
                if latest
                else ""
            )
            if not sitemap_kind:
                raise ValidationError("This site has no sitemap sync history to retry.")
            now = timezone.now()
            sync_request = ProjectSyncRequest.objects.create(
                project=project,
                kind=ProjectSyncKinds.MANUAL,
                sitemap_kind=sitemap_kind,
                idempotency_key=f"manual:{project.uuid}:{now.isoformat()}",
            )
            project.current_sync_uuid = sync_request.uuid
            project.current_sync_started_at = None
            project.last_error_code = ""
            project.save(
                update_fields=[
                    "current_sync_uuid",
                    "current_sync_started_at",
                    "last_error_code",
                    "updated_at",
                ]
            )
        sync_uuid = sync_request.uuid
    enqueue_sitemap_sync_safely(sync_uuid)
    return sync_request


def _record_sync_failure(sync_uuid, error: SitemapParseError) -> str:
    with transaction.atomic():
        sync_request = ProjectSyncRequest.objects.select_for_update().get(uuid=sync_uuid)
        project = Project.objects.select_for_update().get(pk=sync_request.project_id)
        sync_request.error_code = error.code.value
        sync_request.broker_task_id = ""
        if error.retryable and sync_request.attempt_count < sync_request.max_attempts:
            sync_request.state = ProjectSyncStates.QUEUED
            sync_request.next_attempt_at = timezone.now() + _retry_delay(
                sync_request.uuid, sync_request.attempt_count
            )
            sync_request.completed_at = None
        else:
            sync_request.state = ProjectSyncStates.FAILED
            sync_request.next_attempt_at = None
            sync_request.completed_at = timezone.now()
        sync_request.save()
        project.last_error_code = error.code.value
        if sync_request.state == ProjectSyncStates.FAILED:
            project.current_sync_uuid = None
            project.current_sync_started_at = None
        project.save()
        return sync_request.state


def _candidate_ids_for_sync(
    *,
    sync_request: ProjectSyncRequest,
    previous_inventory_id: int | None,
    now: datetime,
) -> list[int]:
    candidates = list(
        sync_request.sitemap_inventory.candidates.values(
            "id",
            "normalized_url",
            "lastmod_hint",
        )
    )
    if sync_request.kind != ProjectSyncKinds.DAILY or previous_inventory_id is None:
        return [candidate["id"] for candidate in candidates]

    previous_by_url = dict(
        SitemapCandidate.objects.filter(inventory_id=previous_inventory_id).values_list(
            "normalized_url",
            "lastmod_hint",
        )
    )
    selected_ids = []
    unchanged_by_url = {}
    for candidate in candidates:
        normalized_url = candidate["normalized_url"]
        previous_lastmod = previous_by_url.get(normalized_url)
        current_lastmod = candidate["lastmod_hint"]
        if previous_lastmod is None or (current_lastmod and current_lastmod != previous_lastmod):
            selected_ids.append(candidate["id"])
        else:
            unchanged_by_url[normalized_url] = candidate["id"]

    if not unchanged_by_url:
        return selected_ids

    sources = ArticleSourceURL.objects.filter(
        project_id=sync_request.project_id,
        normalized_url__in=unchanged_by_url,
        is_active=True,
    )
    known_urls = set(sources.values_list("normalized_url", flat=True))
    selected_ids.extend(
        candidate_id
        for normalized_url, candidate_id in unchanged_by_url.items()
        if normalized_url not in known_urls
    )
    stale_cutoff = now - timedelta(hours=settings.RECONCILE_INTERVAL_HOURS * 7)
    stale_urls = set(
        sources.filter(article__last_fetched_at__lte=stale_cutoff).values_list(
            "normalized_url", flat=True
        )
    )
    selected_ids.extend(unchanged_by_url[url] for url in stale_urls)
    return selected_ids


def run_sitemap_sync(sync_uuid: str) -> str:
    sync_request = _claim_sync(sync_uuid)
    if sync_request is None:
        return "noop"
    previous_inventory_id = sync_request.project.active_sitemap_inventory_id
    try:
        result = SitemapParser(allowed_host=sync_request.project.normalized_host).parse(
            sync_request.project.normalized_sitemap_url
        )
        inventory = SitemapInventoryService.promote(
            project=sync_request.project,
            sync_request=sync_request,
            result=result,
        )
    except SitemapParseError as error:
        state = _record_sync_failure(sync_uuid, error)
        logger.warning(
            "crawl.sync.failed",
            extra={
                "sync_uuid": str(sync_uuid),
                "error_code": error.code.value,
                "retryable": error.retryable,
                "sync_state": state,
            },
        )
        return state

    candidate_ids = _candidate_ids_for_sync(
        sync_request=sync_request,
        previous_inventory_id=previous_inventory_id,
        now=timezone.now(),
    )
    candidates = list(inventory.candidates.filter(id__in=candidate_ids).only("id"))
    PageCrawlWork.objects.bulk_create(
        [
            PageCrawlWork(
                sync_request=sync_request,
                candidate=candidate,
                max_attempts=settings.CRAWL_MAX_ATTEMPTS,
            )
            for candidate in candidates
        ],
        ignore_conflicts=True,
        batch_size=1000,
    )
    _refresh_sync_counts(sync_request.uuid)
    if not candidates:
        _finalize_sync(sync_request.uuid)
        return ProjectSyncStates.SUCCEEDED
    dispatch_page_work(str(sync_request.uuid))
    return ProjectSyncStates.RUNNING


def dispatch_page_work(sync_uuid: str) -> int:
    now = timezone.now()
    with transaction.atomic():
        sync_request = (
            ProjectSyncRequest.objects.select_for_update()
            .select_related("project__owner__user")
            .get(uuid=sync_uuid)
        )
        if sync_request.state != ProjectSyncStates.RUNNING:
            return 0
        if not sync_request.project.is_sync_eligible:
            _cancel_sync(sync_request)
            return 0
        work_items = list(
            PageCrawlWork.objects.select_for_update(skip_locked=True)
            .filter(sync_request=sync_request, state=PageCrawlStates.QUEUED, broker_task_id="")
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .order_by("id")[: settings.CRAWL_DISPATCH_BATCH_SIZE]
        )
        for work in work_items:
            work.broker_task_id = "dispatching"
        PageCrawlWork.objects.bulk_update(work_items, ["broker_task_id", "updated_at"])

    for work in work_items:
        try:
            broker_task_id = async_task(
                RUN_PAGE_TASK,
                str(work.uuid),
                q_options={"group": f"crawl:{sync_request.project.uuid}"},
            )
        except Exception as error:
            PageCrawlWork.objects.filter(uuid=work.uuid, broker_task_id="dispatching").update(
                broker_task_id=""
            )
            logger.error(
                "crawl.page.enqueue_failed",
                extra={"work_uuid": str(work.uuid), "error.type": type(error).__name__},
            )
            continue
        PageCrawlWork.objects.filter(uuid=work.uuid, broker_task_id="dispatching").update(
            broker_task_id=_task_id(broker_task_id)
        )

    remaining = PageCrawlWork.objects.filter(
        sync_request__uuid=sync_uuid,
        state=PageCrawlStates.QUEUED,
        broker_task_id="",
    ).exists()
    if remaining and work_items:
        async_task(
            DISPATCH_TASK,
            str(sync_uuid),
            q_options={"group": f"crawl:{sync_request.project.uuid}"},
        )
    return len(work_items)


def _claim_page_work(work_uuid) -> PageCrawlWork | None:
    with transaction.atomic():
        work = (
            PageCrawlWork.objects.select_for_update()
            .select_related("sync_request__project__owner__user", "candidate")
            .get(uuid=work_uuid)
        )
        if work.state in _PAGE_TERMINAL:
            return None
        project = Project.objects.select_for_update().get(pk=work.sync_request.project_id)
        if not project.is_sync_eligible:
            _cancel_sync(work.sync_request)
            return None
        if work.state == PageCrawlStates.RUNNING:
            return None
        running_count = PageCrawlWork.objects.filter(
            sync_request__project=project,
            state=PageCrawlStates.RUNNING,
        ).count()
        if running_count >= settings.CRAWL_PER_SITE_CONCURRENCY:
            work.broker_task_id = ""
            work.save(update_fields=["broker_task_id", "updated_at"])
            return None
        now = timezone.now()
        if work.next_attempt_at and work.next_attempt_at > now:
            work.broker_task_id = ""
            work.save(update_fields=["broker_task_id", "updated_at"])
            return None
        work.state = PageCrawlStates.RUNNING
        work.attempt_count += 1
        work.started_at = now
        work.next_attempt_at = None
        work.error_code = ""
        work.broker_task_id = ""
        work.save()
        return work


def _fetch_page(work: PageCrawlWork) -> HtmlExtraction:
    result = SafeFetchClient.from_django_settings().fetch(
        work.candidate.normalized_url,
        max_bytes=settings.CRAWL_MAX_PAGE_BYTES,
        allowed_content_types={"text/html", "application/xhtml+xml"},
    )
    try:
        _normalized, host = normalize_sitemap_url(result.final_url)
    except (ValidationError, ValueError) as error:
        raise SafeFetchErrorCodeWrapper("invalid_final_url") from error
    if host != work.sync_request.project.normalized_host:
        raise SafeFetchErrorCodeWrapper("redirected_off_host")
    return extract_article(
        result,
        allowed_host=work.sync_request.project.normalized_host,
    )


class SafeFetchErrorCodeWrapper(Exception):
    def __init__(self, code: str):
        self.code = code
        self.retryable = False
        super().__init__(code)


class ArticleIndexingError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class ProjectBecameIneligibleError(Exception):
    pass


def _cancel_if_project_ineligible(sync_uuid) -> bool:
    with transaction.atomic():
        sync_request = (
            ProjectSyncRequest.objects.select_for_update()
            .select_related("project__owner__user")
            .get(uuid=sync_uuid)
        )
        if sync_request.state == ProjectSyncStates.CANCELLED:
            return True
        if sync_request.project.is_sync_eligible:
            return False
        _cancel_sync(sync_request)
        return True


def _index_ready_article(article: Article) -> None:
    """Complete embedding and durable vector upsert inside one observable page job."""
    EmbeddingService().embed_article(article_uuid=article.uuid)
    owner_id = Project.objects.values_list("owner_id", flat=True).get(pk=article.project_id)
    # Lock in Article -> Profile -> Project order. Deactivation locks Article before
    # updating Project, while subscription and project transitions lock Profile
    # before Project. Holding all three makes the eligibility decision linearizable
    # with the bounded Qdrant publication and avoids cross-path deadlocks.
    with transaction.atomic():
        article = Article.objects.select_for_update().get(pk=article.pk)
        owner = Profile.objects.select_for_update().select_related("user").get(pk=owner_id)
        project = Project.objects.select_for_update().get(pk=article.project_id)
        if project.owner_id != owner.pk:
            # Ownership is immutable through the product service, but verify the
            # prefetched lock target so a direct concurrent reassignment cannot
            # publish under the previous owner's eligibility.
            raise ArticleIndexingError("project_owner_changed", retryable=True)
        if project.state != ProjectStates.ACTIVE or not owner.has_active_subscription:
            raise ProjectBecameIneligibleError
        try:
            upsert_article(article=article)
        except ApiException as error:
            raise ArticleIndexingError("qdrant_unavailable", retryable=True) from error


def _process_page_work(work: PageCrawlWork) -> None:
    if not PageExtractionResult.objects.filter(work=work).exists():
        extraction = _fetch_page(work)
        PageExtractionService.persist(work=work, extraction=extraction)
    article = ArticleIngestionService.ingest(work=work, queue_embedding=False)
    if work.extraction.state != ExtractionStates.READY or not settings.CITEGUILD_INDEXING_ENABLED:
        return
    if _cancel_if_project_ineligible(work.sync_request.uuid):
        raise ProjectBecameIneligibleError
    _index_ready_article(article)


def _record_page_outcome(work_uuid, *, error=None) -> str:
    with transaction.atomic():
        work = (
            PageCrawlWork.objects.select_for_update()
            .select_related("sync_request")
            .get(uuid=work_uuid)
        )
        if work.sync_request.state == ProjectSyncStates.CANCELLED:
            if work.state != PageCrawlStates.CANCELLED:
                work.state = PageCrawlStates.CANCELLED
                work.completed_at = timezone.now()
                work.broker_task_id = ""
                work.error_code = "project_ineligible"
                work.save()
            return work.state
        now = timezone.now()
        work.broker_task_id = ""
        if error is None:
            work.state = PageCrawlStates.SUCCEEDED
            work.completed_at = now
            work.error_code = ""
        else:
            CrawlAttemptService.record_failure(
                work=work,
                error_code=str(error.code),
            )
            work.error_code = str(error.code)
            if error.retryable and work.attempt_count < work.max_attempts:
                work.state = PageCrawlStates.QUEUED
                work.next_attempt_at = now + _retry_delay(work.uuid, work.attempt_count)
                work.completed_at = None
            else:
                work.state = PageCrawlStates.FAILED
                work.next_attempt_at = None
                work.completed_at = now
        work.save()
        sync_uuid = work.sync_request.uuid
    _refresh_sync_counts(sync_uuid)
    sync_state = _finalize_sync(sync_uuid)
    log = logger.warning if error is not None else logger.info
    log(
        "crawl.page.completed",
        extra={
            "event.name": "crawl.page.completed",
            "sync_uuid": str(sync_uuid),
            "work_uuid": str(work.uuid),
            "page_state": work.state,
            "sync_state": sync_state,
            "attempt_count": work.attempt_count,
            "error.type": work.error_code,
            "operation.status": work.state,
            "outcome": "success" if error is None else "failure",
            "retryable": bool(error and error.retryable),
        },
    )
    return work.state


def run_page_crawl(work_uuid: str) -> str:
    work = _claim_page_work(work_uuid)
    if work is None:
        return "noop"
    try:
        _process_page_work(work)
    except SafeFetchError as error:
        return _record_page_outcome(work_uuid, error=error)
    except (SafeFetchErrorCodeWrapper, HtmlExtractionError, ArticlePersistenceError) as error:
        return _record_page_outcome(work_uuid, error=error)
    except EmbeddingError as error:
        return _record_page_outcome(work_uuid, error=error)
    except ArticleIndexingError as error:
        return _record_page_outcome(work_uuid, error=error)
    except ProjectBecameIneligibleError:
        if _cancel_if_project_ineligible(work.sync_request.uuid):
            return PageCrawlStates.CANCELLED
        return _record_page_outcome(
            work_uuid,
            error=ArticleIndexingError("project_eligibility_changed", retryable=True),
        )
    except QdrantContractError as error:
        return _record_page_outcome(
            work_uuid,
            error=ArticleIndexingError(error.code),
        )
    return _record_page_outcome(work_uuid)


def _refresh_sync_counts(sync_uuid) -> None:
    states = PageCrawlWork.objects.filter(sync_request__uuid=sync_uuid)
    ProjectSyncRequest.objects.filter(uuid=sync_uuid).update(
        total_count=states.count(),
        queued_count=states.filter(state=PageCrawlStates.QUEUED).count(),
        succeeded_count=states.filter(state=PageCrawlStates.SUCCEEDED).count(),
        failed_count=states.filter(state=PageCrawlStates.FAILED).count(),
    )


def _finalize_sync(sync_uuid) -> str:
    with transaction.atomic():
        sync_request = ProjectSyncRequest.objects.select_for_update().get(uuid=sync_uuid)
        if sync_request.state == ProjectSyncStates.CANCELLED:
            return sync_request.state
        if not hasattr(sync_request, "sitemap_inventory"):
            return sync_request.state
        unfinished = sync_request.page_work.exclude(state__in=_PAGE_TERMINAL).exists()
        if unfinished:
            return sync_request.state
        _refresh_sync_counts(sync_uuid)
        sync_request.refresh_from_db()
        if sync_request.failed_count and sync_request.succeeded_count:
            sync_request.state = ProjectSyncStates.PARTIAL
        elif sync_request.failed_count:
            sync_request.state = ProjectSyncStates.FAILED
        else:
            sync_request.state = ProjectSyncStates.SUCCEEDED
        sync_request.completed_at = timezone.now()
        sync_request.broker_task_id = ""
        sync_request.save(update_fields=["state", "completed_at", "broker_task_id", "updated_at"])
        project = Project.objects.select_for_update().get(pk=sync_request.project_id)
        ArticleLifecycleService.reconcile_sitemap(sync_request=sync_request)
        project.last_sync_uuid = sync_request.uuid
        project.last_sync_at = sync_request.completed_at
        project.current_sync_uuid = None
        project.current_sync_started_at = None
        project.last_error_code = (
            "" if sync_request.state == ProjectSyncStates.SUCCEEDED else "page_failures"
        )
        project.save()
        return sync_request.state


def recover_crawl_jobs() -> dict[str, int]:
    """Requeue due/stale durable work after broker loss or worker restarts."""
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.CRAWL_STALE_AFTER_SECONDS)
    stale_syncs = ProjectSyncRequest.objects.filter(
        state=ProjectSyncStates.RUNNING,
        started_at__lt=cutoff,
    ).update(
        state=ProjectSyncStates.QUEUED,
        broker_task_id="",
        next_attempt_at=now,
        error_code="worker_lost",
    )
    stale_pages = PageCrawlWork.objects.filter(
        state=PageCrawlStates.RUNNING,
        started_at__lt=cutoff,
    ).update(
        state=PageCrawlStates.QUEUED,
        broker_task_id="",
        next_attempt_at=now,
        error_code="worker_lost",
    )
    ProjectSyncRequest.objects.filter(
        state=ProjectSyncStates.QUEUED,
        broker_task_id="dispatching",
        updated_at__lt=cutoff,
    ).update(broker_task_id="")
    PageCrawlWork.objects.filter(
        state=PageCrawlStates.QUEUED,
        broker_task_id="dispatching",
        updated_at__lt=cutoff,
    ).update(broker_task_id="")

    syncs = list(
        ProjectSyncRequest.objects.filter(state=ProjectSyncStates.QUEUED, broker_task_id="")
        .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
        .values_list("uuid", flat=True)[:100]
    )
    for sync_uuid in syncs:
        enqueue_sitemap_sync(sync_uuid)
    running_syncs = list(
        ProjectSyncRequest.objects.filter(state=ProjectSyncStates.RUNNING).values_list(
            "uuid", flat=True
        )[:100]
    )
    for sync_uuid in running_syncs:
        dispatch_page_work(str(sync_uuid))
        _finalize_sync(sync_uuid)
    return {
        "stale_syncs": stale_syncs,
        "stale_pages": stale_pages,
        "enqueued_syncs": len(syncs),
        "dispatched_syncs": len(running_syncs),
    }
