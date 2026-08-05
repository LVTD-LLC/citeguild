"""Bounded, owner-scoped dashboard read model."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Page, Paginator
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber

from apps.core.choices import ArticleStates
from apps.core.models import (
    Article,
    DetectedNetworkLink,
    Profile,
    Project,
    ProjectSyncRequest,
)


@dataclass(frozen=True, slots=True)
class DashboardData:
    site_count: int
    projects: Page


class DashboardService:
    SITE_PAGE_SIZE = 10
    ARTICLE_COUNT_FIELDS = (
        "inactive_article_count",
        "missing_article_count",
        "unavailable_article_count",
        "excluded_article_count",
        "pending_article_count",
    )
    LATEST_SYNC_FIELDS = (
        "state",
        "error_code",
        "total_count",
        "succeeded_count",
        "failed_count",
        "started_at",
        "completed_at",
    )
    LATEST_SYNC_DEFAULTS = {
        "state": "",
        "error_code": "",
        "total_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "started_at": None,
        "completed_at": None,
    }

    @classmethod
    def projects_for_owner(cls, owner: Profile):
        # Keep pagination independent from dashboard aggregates. In production,
        # counting the previous multi-join annotation repeated nearly all of the
        # expensive project-list query before the page itself was fetched.
        return Project.objects.filter(owner=owner).order_by("name", "id")

    @classmethod
    def _article_counts(cls, project_ids: list[int]) -> dict[int, dict]:
        rows = (
            Article.objects.filter(project_id__in=project_ids)
            .values("project_id")
            .annotate(
                inactive_article_count=Count(
                    "id",
                    filter=Q(state=ArticleStates.INACTIVE),
                ),
                missing_article_count=Count(
                    "id",
                    filter=Q(inactivity_reason="sitemap_removed"),
                ),
                unavailable_article_count=Count(
                    "id",
                    filter=Q(inactivity_reason__in=("http_404", "http_410")),
                ),
                excluded_article_count=Count(
                    "id",
                    filter=Q(inactivity_reason__in=("empty", "noindex")),
                ),
                pending_article_count=Count(
                    "id",
                    filter=Q(state=ArticleStates.DISCOVERED),
                ),
            )
        )
        return {row["project_id"]: row for row in rows}

    @staticmethod
    def _link_counts(project_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
        cross_project = DetectedNetworkLink.objects.filter(is_active=True).exclude(
            source_article__project_id=F("target_project_id")
        )
        given = {
            row["source_article__project_id"]: row["count"]
            for row in cross_project.filter(source_article__project_id__in=project_ids)
            .values("source_article__project_id")
            .annotate(count=Count("id"))
        }
        received = {
            row["target_project_id"]: row["count"]
            for row in cross_project.filter(target_project_id__in=project_ids)
            .values("target_project_id")
            .annotate(count=Count("id"))
        }
        return given, received

    @classmethod
    def _latest_syncs(cls, project_ids: list[int]) -> dict[int, dict]:
        rows = (
            ProjectSyncRequest.objects.filter(project_id__in=project_ids)
            .annotate(
                dashboard_row_number=Window(
                    expression=RowNumber(),
                    partition_by=(F("project_id"),),
                    order_by=(F("created_at").desc(), F("id").desc()),
                )
            )
            .filter(dashboard_row_number=1)
            .order_by()
            .values("project_id", *cls.LATEST_SYNC_FIELDS)
        )
        return {row["project_id"]: row for row in rows}

    @classmethod
    def _hydrate_page(cls, page: Page) -> Page:
        projects = list(page.object_list)
        if not projects:
            page.object_list = projects
            return page

        project_ids = [project.pk for project in projects]
        article_counts = cls._article_counts(project_ids)
        links_given, links_received = cls._link_counts(project_ids)
        latest_syncs = cls._latest_syncs(project_ids)

        for project in projects:
            counts = article_counts.get(project.pk, {})
            for field in cls.ARTICLE_COUNT_FIELDS:
                setattr(project, field, counts.get(field, 0))

            project.detected_links_given_count = links_given.get(project.pk, 0)
            project.detected_links_received_count = links_received.get(project.pk, 0)

            latest_sync = latest_syncs.get(project.pk, {})
            for field in cls.LATEST_SYNC_FIELDS:
                default = cls.LATEST_SYNC_DEFAULTS[field]
                setattr(project, f"latest_sync_{field}", latest_sync.get(field, default))
            project.latest_sync_pending_count = max(
                project.latest_sync_total_count
                - project.latest_sync_succeeded_count
                - project.latest_sync_failed_count,
                0,
            )

        page.object_list = projects
        return page

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
        projects = cls._hydrate_page(
            cls._page(
                cls.projects_for_owner(owner),
                site_page,
                page_size=cls.SITE_PAGE_SIZE,
            )
        )
        return DashboardData(
            site_count=projects.paginator.count,
            projects=projects,
        )
