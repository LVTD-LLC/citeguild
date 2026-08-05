"""Bounded, owner-scoped read model for one sitemap-backed site."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Page, Paginator
from django.db.models import Count, F, Q

from apps.core.choices import ArticleStates
from apps.core.models import Article, DetectedNetworkLink, Profile, Project
from apps.core.projects import ProjectService


@dataclass(frozen=True, slots=True)
class SitemapDetailsData:
    project: Project
    article_counts: dict[str, int]
    links_given: Page
    links_received: Page


class SitemapDetailsService:
    LINK_PAGE_SIZE = 20

    @staticmethod
    def _cross_site_links():
        return DetectedNetworkLink.objects.exclude(
            source_article__project_id=F("target_project_id")
        )

    @classmethod
    def _links_given(cls, project: Project):
        return (
            cls._cross_site_links()
            .filter(source_article__project=project)
            .select_related("source_article", "target_project", "target_article")
            .order_by("-last_detected_at", "-id")
        )

    @classmethod
    def _links_received(cls, project: Project):
        return (
            cls._cross_site_links()
            .filter(target_project=project)
            .select_related("source_article__project", "target_project", "target_article")
            .order_by("-last_detected_at", "-id")
        )

    @staticmethod
    def _article_counts(project: Project) -> dict[str, int]:
        return Article.objects.filter(project=project).aggregate(
            total=Count("id"),
            searchable=Count("id", filter=Q(is_active=True)),
            waiting=Count("id", filter=Q(state=ArticleStates.DISCOVERED)),
            inactive=Count("id", filter=Q(state=ArticleStates.INACTIVE)),
        )

    @classmethod
    def for_owner(
        cls,
        owner: Profile,
        project_uuid,
        *,
        given_page=1,
        received_page=1,
    ) -> SitemapDetailsData:
        project = ProjectService.get_for_owner(owner, project_uuid)
        project.latest_sync = project.sync_requests.order_by("-created_at", "-id").first()
        return SitemapDetailsData(
            project=project,
            article_counts=cls._article_counts(project),
            links_given=Paginator(cls._links_given(project), cls.LINK_PAGE_SIZE).get_page(
                given_page or 1
            ),
            links_received=Paginator(cls._links_received(project), cls.LINK_PAGE_SIZE).get_page(
                received_page or 1
            ),
        )
