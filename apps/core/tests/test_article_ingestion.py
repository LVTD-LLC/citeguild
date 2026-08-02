from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.core.article_ingestion import (
    ArticleIngestionService,
    ArticleLifecycleService,
    ArticleRepository,
    CrawlAttemptService,
)
from apps.core.choices import ArticleStates, ProjectSyncStates
from apps.core.models import (
    Article,
    ArticleCrawlAttempt,
    ArticleSourceURL,
    OutboundLinkObservation,
    PageCrawlWork,
    PageExtractionResult,
    ProjectSyncRequest,
)
from apps.core.projects import ProjectService
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseResult,
)


def create_project(profile, host="example.com"):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    return ProjectService.create(
        owner=profile,
        name=host,
        sitemap_url=f"https://{host}/sitemap.xml",
    )


def create_sync(project, key, *urls):
    sync = ProjectSyncRequest.objects.create(
        project=project,
        sitemap_kind="urlset",
        idempotency_key=key,
        state=ProjectSyncStates.RUNNING,
    )
    candidates = tuple(ParsedCandidate(url, url) for url in urls)
    inventory = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=SitemapParseResult(
            candidates,
            SitemapDiagnostics(1, len(urls), len(urls), 0, 0, 0, 0),
        ),
    )
    return sync, [
        PageCrawlWork.objects.create(sync_request=sync, candidate=candidate)
        for candidate in inventory.candidates.order_by("normalized_url")
    ]


def extraction_for(
    work,
    *,
    canonical_url=None,
    text="Stable useful article text.",
    state="ready",
    links=(),
):
    return PageExtractionResult.objects.create(
        work=work,
        state=state,
        final_url=work.candidate.normalized_url,
        canonical_url=canonical_url or work.candidate.normalized_url,
        http_status=200,
        title="Article title",
        description="Article description",
        language="en",
        text=text if state == "ready" else "",
        noindex=state == "noindex",
        source_bytes=500,
        text_chars=len(text) if state == "ready" else 0,
        outbound_links=list(links),
        diagnostics={"canonical_rejected": False},
    )


@pytest.mark.django_db
def test_ready_extraction_persists_article_source_attempt_and_links(profile):
    project = create_project(profile)
    sync, [work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(
        work,
        links=(
            {"url": "https://member.example/guide", "anchor_text": "Member guide"},
        ),
    )

    article = ArticleIngestionService.ingest(work=work)

    assert article.project == project
    assert article.state == ArticleStates.DISCOVERED
    assert article.content == "Stable useful article text."
    assert len(article.content_hash) == 64
    assert article.qdrant_point_id == article.uuid
    assert ArticleSourceURL.objects.get(article=article).normalized_url.endswith("/post")
    attempt = ArticleCrawlAttempt.objects.get(work=work, attempt_number=0)
    assert attempt.article == article
    assert attempt.content_hash == article.content_hash
    link = OutboundLinkObservation.objects.get(source_article=article)
    assert link.normalized_destination_url == "https://member.example/guide"
    assert link.anchor_text == "Member guide"
    assert link.is_active is True
    assert project.articles.count() == 1
    project.refresh_from_db()
    assert project.article_count == 1
    assert project.active_article_count == 0


@pytest.mark.django_db
def test_unchanged_content_does_not_move_last_changed(profile):
    project = create_project(profile)
    first_sync, [first_work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(first_work)
    article = ArticleIngestionService.ingest(work=first_work)
    first_changed = article.last_changed_at
    first_sync.state = ProjectSyncStates.SUCCEEDED
    first_sync.save(update_fields=["state", "updated_at"])

    _second_sync, [second_work] = create_sync(
        project,
        "second",
        "https://example.com/post",
    )
    extraction_for(second_work)
    refreshed = ArticleIngestionService.ingest(work=second_work)

    assert refreshed.pk == article.pk
    assert refreshed.last_changed_at == first_changed
    assert refreshed.last_fetched_at >= first_changed


@pytest.mark.django_db
def test_canonical_duplicates_resolve_to_one_article_with_two_sources(profile):
    project = create_project(profile)
    _sync, works = create_sync(
        project,
        "duplicates",
        "https://example.com/amp/post",
        "https://example.com/post",
    )
    for work in works:
        extraction_for(work, canonical_url="https://example.com/post")

    articles = [ArticleIngestionService.ingest(work=work) for work in works]

    assert articles[0].pk == articles[1].pk
    assert Article.objects.filter(project=project).count() == 1
    assert ArticleSourceURL.objects.filter(article=articles[0], is_active=True).count() == 2


@pytest.mark.django_db
def test_failed_fetch_records_history_without_erasing_last_good_content(profile):
    project = create_project(profile)
    first_sync, [first_work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(first_work)
    article = ArticleIngestionService.ingest(work=first_work)
    original_hash = article.content_hash
    first_sync.state = ProjectSyncStates.SUCCEEDED
    first_sync.save(update_fields=["state", "updated_at"])
    _second_sync, [failed_work] = create_sync(
        project,
        "failed",
        "https://example.com/post",
    )
    failed_work.attempt_count = 1
    failed_work.save(update_fields=["attempt_count", "updated_at"])

    CrawlAttemptService.record_failure(
        work=failed_work,
        error_code="timeout",
    )

    article.refresh_from_db()
    assert article.content_hash == original_hash
    assert article.content == "Stable useful article text."
    assert ArticleCrawlAttempt.objects.get(work=failed_work).error_code == "timeout"


@pytest.mark.django_db
def test_noindex_inactivates_without_erasing_last_good_content(profile):
    project = create_project(profile)
    first_sync, [first_work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(first_work)
    article = ArticleIngestionService.ingest(work=first_work)
    original_hash = article.content_hash
    first_sync.state = ProjectSyncStates.SUCCEEDED
    first_sync.save(update_fields=["state", "updated_at"])
    _second_sync, [noindex_work] = create_sync(
        project,
        "noindex",
        "https://example.com/post",
    )
    extraction_for(noindex_work, state="noindex")

    updated = ArticleIngestionService.ingest(work=noindex_work)

    assert updated.pk == article.pk
    assert updated.state == ArticleStates.INACTIVE
    assert updated.inactivity_reason == "noindex"
    assert updated.content_hash == original_hash
    assert updated.content == "Stable useful article text."


@pytest.mark.django_db
def test_successful_refresh_reconciles_outbound_link_history(profile):
    project = create_project(profile)
    first_sync, [first_work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(
        first_work,
        links=(
            {"url": "https://member.example/a", "anchor_text": "A"},
            {"url": "https://member.example/b", "anchor_text": "B"},
        ),
    )
    article = ArticleIngestionService.ingest(work=first_work)
    first_sync.state = ProjectSyncStates.SUCCEEDED
    first_sync.save(update_fields=["state", "updated_at"])
    _second_sync, [second_work] = create_sync(
        project,
        "second",
        "https://example.com/post",
    )
    extraction_for(
        second_work,
        links=({"url": "https://member.example/b", "anchor_text": "Updated B"},),
    )

    ArticleIngestionService.ingest(work=second_work)

    first_link = OutboundLinkObservation.objects.get(
        source_article=article,
        normalized_destination_url="https://member.example/a",
    )
    second_link = OutboundLinkObservation.objects.get(
        source_article=article,
        normalized_destination_url="https://member.example/b",
    )
    assert first_link.is_active is False
    assert first_link.inactive_at is not None
    assert second_link.is_active is True
    assert second_link.anchor_text == "Updated B"


@pytest.mark.django_db
def test_missing_article_is_retained_and_reactivated_with_stable_identity(profile):
    project = create_project(profile)
    first_sync, [first_work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(first_work)
    article = ArticleIngestionService.ingest(work=first_work)
    article_uuid = article.uuid
    first_sync.state = ProjectSyncStates.SUCCEEDED
    first_sync.save(update_fields=["state", "updated_at"])
    missing_sync, _works = create_sync(project, "missing")

    ArticleLifecycleService.reconcile_sitemap(sync_request=missing_sync)

    article.refresh_from_db()
    assert article.state == ArticleStates.INACTIVE
    assert article.inactive_at is not None
    assert article.content == "Stable useful article text."
    missing_sync.state = ProjectSyncStates.SUCCEEDED
    missing_sync.save(update_fields=["state", "updated_at"])
    _return_sync, [return_work] = create_sync(
        project,
        "return",
        "https://example.com/post",
    )
    extraction_for(return_work)

    reactivated = ArticleIngestionService.ingest(work=return_work)

    assert reactivated.uuid == article_uuid
    assert reactivated.state == ArticleStates.DISCOVERED
    assert reactivated.inactive_at is None
    assert reactivated.inactivity_reason == ""


@pytest.mark.django_db
def test_owner_repository_cannot_cross_tenant_boundaries(profile):
    project = create_project(profile)
    _sync, [work] = create_sync(project, "first", "https://example.com/post")
    extraction_for(work)
    article = ArticleIngestionService.ingest(work=work)
    other_user = get_user_model().objects.create_user(
        username="other",
        email="other@example.com",
        password="password123",
    )

    assert ArticleRepository.for_owner(profile).get(uuid=article.uuid) == article
    assert not ArticleRepository.for_owner(other_user.profile).filter(uuid=article.uuid).exists()
