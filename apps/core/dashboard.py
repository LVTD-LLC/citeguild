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
from apps.core.models import Profile, Project, ProjectSyncRequest


@dataclass(frozen=True, slots=True)
class DashboardData:
    site_count: int
    projects: Page


class DashboardService:
    SITE_PAGE_SIZE = 10

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
                distinct=True,
            ),
            missing_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason="sitemap_removed"),
                distinct=True,
            ),
            unavailable_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason__in=("http_404", "http_410")),
                distinct=True,
            ),
            excluded_article_count=Count(
                "articles",
                filter=Q(articles__inactivity_reason__in=("empty", "noindex")),
                distinct=True,
            ),
            pending_article_count=Count(
                "articles",
                filter=Q(articles__state=ArticleStates.DISCOVERED),
                distinct=True,
            ),
            detected_links_given_count=Count(
                "articles__detected_links_given",
                filter=Q(articles__detected_links_given__is_active=True),
                distinct=True,
            ),
            detected_links_received_count=Count(
                "detected_links_received",
                filter=Q(detected_links_received__is_active=True),
                distinct=True,
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
    ) -> DashboardData:
        projects = cls._page(
            cls.projects_for_owner(owner),
            site_page,
            page_size=cls.SITE_PAGE_SIZE,
        )
        return DashboardData(
            site_count=projects.paginator.count,
            projects=projects,
        )
