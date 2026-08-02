"""Bounded, owner-scoped dashboard read model."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Page, Paginator
from django.db.models import (
    CharField,
    Count,
    DateTimeField,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce, Greatest

from apps.core.choices import ArticleStates
from apps.core.models import Article, Profile, Project, ProjectSyncRequest
from apps.core.network_graph import DetectedNetworkLinkQueries


@dataclass(frozen=True, slots=True)
class DashboardSummary:
    site_count: int
    indexed_article_count: int
    pending_article_count: int
    inactive_article_count: int
    detected_links_given: int
    detected_links_received: int


@dataclass(frozen=True, slots=True)
class DashboardData:
    summary: DashboardSummary
    projects: Page
    links_given: Page
    links_received: Page


class DashboardService:
    SITE_PAGE_SIZE = 10
    LINK_PAGE_SIZE = 10

    @staticmethod
    def _latest_sync_annotations():
        latest = ProjectSyncRequest.objects.filter(project=OuterRef("pk")).order_by(
            "-created_at", "-id"
        )
        return {
            "latest_sync_state": Coalesce(
                Subquery(latest.values("state")[:1], output_field=CharField()),
                Value(""),
            ),
            "latest_sync_error_code": Coalesce(
                Subquery(latest.values("error_code")[:1], output_field=CharField()),
                Value(""),
            ),
            "latest_sync_total_count": Coalesce(
                Subquery(latest.values("total_count")[:1], output_field=IntegerField()),
                Value(0),
            ),
            "latest_sync_succeeded_count": Coalesce(
                Subquery(latest.values("succeeded_count")[:1], output_field=IntegerField()),
                Value(0),
            ),
            "latest_sync_failed_count": Coalesce(
                Subquery(latest.values("failed_count")[:1], output_field=IntegerField()),
                Value(0),
            ),
            "latest_sync_started_at": Subquery(
                latest.values("started_at")[:1], output_field=DateTimeField()
            ),
            "latest_sync_completed_at": Subquery(
                latest.values("completed_at")[:1], output_field=DateTimeField()
            ),
        }

    @classmethod
    def projects_for_owner(cls, owner: Profile):
        projects = Project.objects.filter(owner=owner).annotate(
            inactive_article_count=Count(
                "articles",
                filter=Q(articles__state=ArticleStates.INACTIVE),
            ),
            missing_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason="sitemap_removed"),
            ),
            unavailable_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason__in=("http_404", "http_410")),
            ),
            excluded_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason__in=("empty", "noindex")),
            ),
            pending_article_count=Count(
                "articles",
                filter=Q(articles__state=ArticleStates.DISCOVERED),
            ),
            **cls._latest_sync_annotations(),
        )
        return projects.annotate(
            latest_sync_pending_count=Greatest(
                F("latest_sync_total_count")
                - F("latest_sync_succeeded_count")
                - F("latest_sync_failed_count"),
                Value(0),
                output_field=IntegerField(),
            )
        ).order_by("name", "id")

    @staticmethod
    def _page(queryset, number, *, page_size: int) -> Page:
        return Paginator(queryset, page_size).get_page(number or 1)

    @classmethod
    def for_owner(
        cls,
        owner: Profile,
        *,
        site_page=1,
        given_page=1,
        received_page=1,
    ) -> DashboardData:
        projects = cls._page(
            cls.projects_for_owner(owner),
            site_page,
            page_size=cls.SITE_PAGE_SIZE,
        )
        links_given = cls._page(
            DetectedNetworkLinkQueries.links_given(owner, active_only=False).order_by(
                "-last_detected_at", "-id"
            ),
            given_page,
            page_size=cls.LINK_PAGE_SIZE,
        )
        links_received = cls._page(
            DetectedNetworkLinkQueries.links_received(owner, active_only=False).order_by(
                "-last_detected_at", "-id"
            ),
            received_page,
            page_size=cls.LINK_PAGE_SIZE,
        )
        article_counts = Article.objects.filter(project__owner=owner).aggregate(
            indexed=Count("id", filter=Q(is_active=True)),
            pending=Count("id", filter=Q(state=ArticleStates.DISCOVERED)),
            inactive=Count("id", filter=Q(state=ArticleStates.INACTIVE)),
        )
        return DashboardData(
            summary=DashboardSummary(
                site_count=projects.paginator.count,
                indexed_article_count=article_counts["indexed"] or 0,
                pending_article_count=article_counts["pending"] or 0,
                inactive_article_count=article_counts["inactive"] or 0,
                detected_links_given=links_given.paginator.count,
                detected_links_received=links_received.paginator.count,
            ),
            projects=projects,
            links_given=links_given,
            links_received=links_received,
        )
