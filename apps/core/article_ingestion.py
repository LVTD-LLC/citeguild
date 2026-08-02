"""Tenant-safe article lifecycle persistence from immutable crawl extraction results."""

from __future__ import annotations

import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.core.choices import ArticleStates, CrawlAttemptStates, ExtractionStates
from apps.core.models import (
    Article,
    ArticleCrawlAttempt,
    ArticleSourceURL,
    OutboundLinkObservation,
    PageCrawlWork,
    Project,
    ProjectSyncRequest,
)
from apps.core.projects import normalize_sitemap_url


class ArticlePersistenceError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.retryable = False
        super().__init__(code)


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _refresh_project_counts(project: Project) -> None:
    articles = Article.objects.filter(project=project)
    Project.objects.filter(pk=project.pk).update(
        article_count=articles.count(),
        active_article_count=articles.filter(is_active=True).count(),
    )


def _update_project_counts(
    project: Project,
    *,
    article_delta: int,
    active_delta: int,
) -> None:
    Project.objects.filter(pk=project.pk).update(
        article_count=F("article_count") + article_delta,
        active_article_count=F("active_article_count") + active_delta,
    )


class ArticleRepository:
    @staticmethod
    def for_owner(owner):
        return Article.objects.filter(project__owner=owner)


class CrawlAttemptService:
    @staticmethod
    def _article_for_work(work: PageCrawlWork) -> Article | None:
        source = (
            ArticleSourceURL.objects.filter(
                project=work.sync_request.project,
                normalized_url=work.candidate.normalized_url,
            )
            .select_related("article")
            .first()
        )
        return source.article if source else None

    @classmethod
    @transaction.atomic
    def record_failure(cls, *, work: PageCrawlWork, error_code: str) -> ArticleCrawlAttempt:
        work = (
            PageCrawlWork.objects.select_related("sync_request__project", "candidate")
            .select_for_update()
            .get(pk=work.pk)
        )
        attempt, _created = ArticleCrawlAttempt.objects.get_or_create(
            work=work,
            attempt_number=work.attempt_count,
            defaults={
                "project": work.sync_request.project,
                "sync_request": work.sync_request,
                "article": cls._article_for_work(work),
                "state": CrawlAttemptStates.FAILED,
                "requested_url": work.candidate.normalized_url,
                "error_code": str(error_code)[:64],
                "fetched_at": timezone.now(),
            },
        )
        return attempt


class ArticleIngestionService:
    @staticmethod
    def _validate_canonical(project: Project, value: str) -> str:
        try:
            normalized, host = normalize_sitemap_url(value)
        except (ValidationError, ValueError) as error:
            raise ArticlePersistenceError("invalid_canonical_url") from error
        if host != project.normalized_host:
            raise ArticlePersistenceError("canonical_host_mismatch")
        return normalized

    @staticmethod
    def _upsert_source(*, article: Article, work: PageCrawlWork, now) -> ArticleSourceURL:
        source, created = ArticleSourceURL.objects.select_for_update().get_or_create(
            project=article.project,
            normalized_url=work.candidate.normalized_url,
            defaults={
                "article": article,
                "is_active": True,
                "first_seen_at": now,
                "last_seen_at": now,
                "last_seen_sync": work.sync_request,
            },
        )
        if not created:
            source.article = article
            source.is_active = True
            source.last_seen_at = now
            source.last_seen_sync = work.sync_request
            source.inactive_at = None
            source.save()
        return source

    @staticmethod
    def _resolve_target(url: str) -> Article | None:
        try:
            _normalized, host = normalize_sitemap_url(url)
        except (ValidationError, ValueError):
            return None
        return (
            Article.objects.filter(
                project__normalized_host=host,
                normalized_canonical_url=url,
            )
            .order_by("id")
            .first()
        )

    @classmethod
    def _reconcile_links(cls, *, article: Article, extraction, sync_request, now) -> None:
        observed: set[str] = set()
        for item in extraction.outbound_links[:1000]:
            if not isinstance(item, dict):
                continue
            try:
                url, _host = normalize_sitemap_url(str(item.get("url", "")))
            except (ValidationError, ValueError):
                continue
            observed.add(url)
            link, created = OutboundLinkObservation.objects.select_for_update().get_or_create(
                source_article=article,
                normalized_destination_url=url,
                defaults={
                    "target_article": cls._resolve_target(url),
                    "anchor_text": str(item.get("anchor_text", ""))[:300],
                    "is_active": True,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "last_seen_sync": sync_request,
                },
            )
            if not created:
                link.target_article = cls._resolve_target(url)
                link.anchor_text = str(item.get("anchor_text", ""))[:300]
                link.is_active = True
                link.last_seen_at = now
                link.last_seen_sync = sync_request
                link.inactive_at = None
                link.save()
        stale = OutboundLinkObservation.objects.filter(
            source_article=article,
            is_active=True,
        )
        if observed:
            stale = stale.exclude(normalized_destination_url__in=observed)
        stale.update(is_active=False, inactive_at=now)

    @classmethod
    @transaction.atomic
    def ingest(cls, *, work: PageCrawlWork) -> Article:
        project = Project.objects.select_for_update().get(pk=work.sync_request.project_id)
        work = (
            PageCrawlWork.objects.select_for_update(of=("self",))
            .select_related("sync_request", "candidate", "extraction")
            .get(pk=work.pk)
        )
        existing_attempt = (
            ArticleCrawlAttempt.objects.select_for_update()
            .select_related("article")
            .filter(work=work, state=CrawlAttemptStates.SUCCEEDED)
            .first()
        )
        if existing_attempt and existing_attempt.article:
            return existing_attempt.article
        extraction = work.extraction
        canonical = cls._validate_canonical(project, extraction.canonical_url)
        now = timezone.now()
        content_hash = (
            _content_hash(extraction.text) if extraction.state == ExtractionStates.READY else ""
        )
        article = (
            Article.objects.select_for_update()
            .filter(project=project, normalized_canonical_url=canonical)
            .first()
        )
        created = article is None
        was_active = article.is_active if article else False
        if created:
            ready = extraction.state == ExtractionStates.READY
            article = Article.objects.create(
                project=project,
                original_url=work.candidate.normalized_url,
                final_url=extraction.final_url,
                canonical_url=extraction.canonical_url,
                normalized_canonical_url=canonical,
                title=extraction.title,
                description=extraction.description,
                language=extraction.language,
                content=extraction.text,
                content_hash=content_hash,
                http_status=extraction.http_status,
                extraction_state=extraction.state,
                state=ArticleStates.DISCOVERED if ready else ArticleStates.INACTIVE,
                is_active=False,
                inactivity_reason="" if ready else extraction.state,
                first_seen_at=now,
                last_seen_at=now,
                last_fetched_at=now,
                last_changed_at=now,
                inactive_at=None if ready else now,
            )
        else:
            ready = extraction.state == ExtractionStates.READY
            changed = ready and content_hash != article.content_hash
            article.final_url = extraction.final_url
            article.canonical_url = extraction.canonical_url
            article.title = extraction.title
            article.description = extraction.description
            article.language = extraction.language
            article.http_status = extraction.http_status
            article.extraction_state = extraction.state
            article.last_seen_at = now
            article.last_fetched_at = now
            if changed:
                article.content = extraction.text
                article.content_hash = content_hash
                article.last_changed_at = now
                article.state = ArticleStates.DISCOVERED
                article.is_active = False
            elif ready and article.state == ArticleStates.INACTIVE:
                article.state = ArticleStates.DISCOVERED
                article.is_active = False
            if ready:
                article.inactivity_reason = ""
                article.inactive_at = None
            else:
                article.state = ArticleStates.INACTIVE
                article.is_active = False
                article.inactivity_reason = extraction.state
                article.inactive_at = article.inactive_at or now
            article.save()

        cls._upsert_source(article=article, work=work, now=now)
        ArticleCrawlAttempt.objects.get_or_create(
            work=work,
            attempt_number=work.attempt_count,
            defaults={
                "project": project,
                "sync_request": work.sync_request,
                "article": article,
                "state": CrawlAttemptStates.SUCCEEDED,
                "requested_url": work.candidate.normalized_url,
                "final_url": extraction.final_url,
                "canonical_url": canonical,
                "http_status": extraction.http_status,
                "extraction_state": extraction.state,
                "source_bytes": extraction.source_bytes,
                "content_hash": content_hash,
                "fetched_at": now,
            },
        )
        if extraction.state == ExtractionStates.READY:
            cls._reconcile_links(
                article=article,
                extraction=extraction,
                sync_request=work.sync_request,
                now=now,
            )
        _update_project_counts(
            project,
            article_delta=int(created),
            active_delta=int(article.is_active) - int(was_active),
        )
        return article


class ArticleLifecycleService:
    @classmethod
    @transaction.atomic
    def reconcile_sitemap(cls, *, sync_request: ProjectSyncRequest) -> None:
        sync_request = (
            ProjectSyncRequest.objects.select_related("project", "sitemap_inventory")
            .select_for_update(of=("self",))
            .get(pk=sync_request.pk)
        )
        project = Project.objects.select_for_update().get(pk=sync_request.project_id)
        desired = set(
            sync_request.sitemap_inventory.candidates.values_list("normalized_url", flat=True)
        )
        now = timezone.now()
        sources = ArticleSourceURL.objects.select_for_update().filter(project=project)
        if desired:
            sources.filter(normalized_url__in=desired).update(
                is_active=True,
                inactive_at=None,
            )
            missing = sources.exclude(normalized_url__in=desired)
        else:
            missing = sources
        missing.update(is_active=False, inactive_at=now)
        source_backed = Article.objects.filter(
            project=project,
            source_urls__is_active=True,
        ).values("pk")
        Article.objects.select_for_update().filter(project=project).exclude(
            pk__in=source_backed
        ).update(
            state=ArticleStates.INACTIVE,
            is_active=False,
            inactivity_reason="sitemap_removed",
            inactive_at=now,
        )
        _refresh_project_counts(project)
