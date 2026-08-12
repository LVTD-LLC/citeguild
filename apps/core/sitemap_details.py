"""Bounded, owner-scoped read model for one sitemap-backed site."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Page, Paginator
from django.db.models import Count, F, Max, Q

from apps.core.choices import ArticleStates
from apps.core.models import Article, DetectedNetworkLink, Profile, Project
from apps.core.projects import ProjectService


@dataclass(frozen=True, slots=True)
class SitemapDetailsData:
    project: Project
    article_counts: dict[str, int]
    links_given: Page
    links_received: Page
    linked_domain_count: int
    linking_domain_count: int


@dataclass(frozen=True, slots=True)
class SitemapArticlesData:
    project: Project
    articles: Page


@dataclass(frozen=True, slots=True)
class SitemapLinksData:
    project: Project
    direction: str
    links: Page
    domain_count: int
    domain_summaries: tuple[dict, ...]


class SitemapDetailsService:
    LINK_PAGE_SIZE = 20
    ARTICLE_PAGE_SIZE = 25
    DOMAIN_SUMMARY_SIZE = 5

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
        links_given = cls._links_given(project)
        links_received = cls._links_received(project)
        return SitemapDetailsData(
            project=project,
            article_counts=cls._article_counts(project),
            links_given=Paginator(links_given, cls.LINK_PAGE_SIZE).get_page(given_page or 1),
            links_received=Paginator(links_received, cls.LINK_PAGE_SIZE).get_page(
                received_page or 1
            ),
            linked_domain_count=links_given.values("target_project_id").distinct().count(),
            linking_domain_count=links_received.values("source_article__project_id")
            .distinct()
            .count(),
        )

    @classmethod
    def articles_for_owner(
        cls,
        owner: Profile,
        project_uuid,
        *,
        page=1,
    ) -> SitemapArticlesData:
        project = ProjectService.get_for_owner(owner, project_uuid)
        articles = Article.objects.filter(project=project).order_by("-last_seen_at", "-id")
        return SitemapArticlesData(
            project=project,
            articles=Paginator(articles, cls.ARTICLE_PAGE_SIZE).get_page(page or 1),
        )

    @classmethod
    def links_for_owner(
        cls,
        owner: Profile,
        project_uuid,
        *,
        direction="in",
        page=1,
    ) -> SitemapLinksData:
        project = ProjectService.get_for_owner(owner, project_uuid)
        normalized_direction = "out" if direction == "out" else "in"
        links_given = cls._links_given(project)
        links_received = cls._links_received(project)
        selected_links = links_given if normalized_direction == "out" else links_received
        domain_field = (
            "target_project__normalized_host"
            if normalized_direction == "out"
            else "source_article__project__normalized_host"
        )
        domain_summaries = tuple(
            selected_links.values(domain=F(domain_field))
            .annotate(
                link_count=Count("id"),
                last_detected_at=Max("last_detected_at"),
            )
            .order_by("-link_count", "domain")[: cls.DOMAIN_SUMMARY_SIZE]
        )
        links_page = Paginator(selected_links, cls.LINK_PAGE_SIZE).get_page(page or 1)
        return SitemapLinksData(
            project=project,
            direction=normalized_direction,
            links=links_page,
            domain_count=selected_links.values(domain_field).distinct().count(),
            domain_summaries=domain_summaries,
        )
