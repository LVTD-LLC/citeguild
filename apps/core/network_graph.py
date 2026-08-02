"""Resolve crawl observations into an account-scoped detected-link graph."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.core.choices import ProjectStates
from apps.core.funnel_analytics import (
    CITATION_DETECTED,
    CITATION_REMOVED,
    track_funnel_event,
)
from apps.core.models import (
    Article,
    ArticleSourceURL,
    DetectedNetworkLink,
    OutboundLinkObservation,
    Profile,
    Project,
)
from apps.core.projects import normalize_sitemap_url


class DetectedNetworkLinkService:
    @staticmethod
    def _track_transition(edge: DetectedNetworkLink, event_name: str, *, occurred_at) -> None:
        source_project = Project.objects.only("uuid", "owner_id").get(
            pk=edge.source_article.project_id
        )
        target_project = Project.objects.only("uuid", "owner_id").get(pk=edge.target_project_id)
        for owner_id, site_id, direction in (
            (source_project.owner_id, source_project.uuid, "given"),
            (target_project.owner_id, target_project.uuid, "received"),
        ):
            track_funnel_event(
                Profile.objects.get(pk=owner_id),
                event_name,
                {
                    "direction": direction,
                    "site_id": str(site_id),
                    "matched_page": edge.target_article_id is not None,
                    "active": edge.is_active,
                },
                idempotency_key=(
                    f"citation:{edge.uuid}:{event_name}:{direction}:{occurred_at.isoformat()}"
                ),
                source_function="DetectedNetworkLinkService.reconcile_observation",
            )

    @staticmethod
    def resolve_destination(url: str) -> tuple[Project, Article | None] | None:
        """Resolve a member host and, when unambiguous, its exact article."""
        try:
            _normalized, host = normalize_sitemap_url(url)
        except (ValidationError, ValueError):
            return None
        project = Project.objects.filter(normalized_host=host).first()
        if project is None:
            return None
        candidates = list(
            Article.objects.filter(
                Q(normalized_canonical_url=url) | Q(source_urls__normalized_url=url),
                project=project,
            )
            .distinct()
            .order_by("id")[:2]
        )
        return project, (candidates[0] if len(candidates) == 1 else None)

    @classmethod
    def target_for_url(cls, url: str) -> Article | None:
        resolved = cls.resolve_destination(url)
        return resolved[1] if resolved else None

    @staticmethod
    def _is_active(
        observation: OutboundLinkObservation,
        target_project: Project,
        target_article: Article | None,
    ) -> bool:
        return bool(
            observation.is_active
            and observation.source_article.is_active
            and observation.source_article.project.state == ProjectStates.ACTIVE
            and target_project.state == ProjectStates.ACTIVE
            and (target_article is None or target_article.is_active)
        )

    @classmethod
    @transaction.atomic
    def reconcile_observation(
        cls,
        observation: OutboundLinkObservation,
        *,
        now=None,
    ) -> DetectedNetworkLink | None:
        now = now or timezone.now()
        observation = (
            OutboundLinkObservation.objects.select_for_update()
            .select_related("source_article__project")
            .get(pk=observation.pk)
        )
        resolved = cls.resolve_destination(observation.normalized_destination_url)
        existing = (
            DetectedNetworkLink.objects.select_for_update().filter(observation=observation).first()
        )
        if resolved is None:
            if existing is not None:
                was_active = existing.is_active
                existing.target_article = None
                existing.is_active = False
                existing.inactive_at = existing.inactive_at or now
                existing.save(
                    update_fields=[
                        "target_article",
                        "is_active",
                        "inactive_at",
                        "updated_at",
                    ]
                )
                if was_active:
                    cls._track_transition(existing, CITATION_REMOVED, occurred_at=now)
            return existing

        target_project, target_article = resolved
        target_project = Project.objects.get(pk=target_project.pk)
        if target_article is not None:
            target_article = Article.objects.get(pk=target_article.pk)
        active = cls._is_active(observation, target_project, target_article)
        was_active = existing.is_active if existing is not None else False
        edge, created = DetectedNetworkLink.objects.get_or_create(
            observation=observation,
            defaults={
                "source_article": observation.source_article,
                "target_project": target_project,
                "target_article": target_article,
                "normalized_destination_url": observation.normalized_destination_url,
                "anchor_text": observation.anchor_text,
                "first_detected_at": observation.first_seen_at,
                "last_detected_at": observation.last_seen_at,
                "is_active": active,
                "inactive_at": None if active else now,
            },
        )
        if not created:
            edge.source_article = observation.source_article
            edge.target_project = target_project
            edge.target_article = target_article
            edge.normalized_destination_url = observation.normalized_destination_url
            edge.anchor_text = observation.anchor_text
            edge.last_detected_at = observation.last_seen_at
            edge.is_active = active
            edge.inactive_at = None if active else (edge.inactive_at or now)
            edge.save()
        if created or active and not was_active:
            cls._track_transition(edge, CITATION_DETECTED, occurred_at=now)
        elif was_active and not active:
            cls._track_transition(edge, CITATION_REMOVED, occurred_at=now)
        return edge

    @classmethod
    def reconcile_article(cls, article: Article, *, now=None) -> None:
        destination_urls = set(
            ArticleSourceURL.objects.filter(article=article).values_list(
                "normalized_url", flat=True
            )
        )
        destination_urls.add(article.normalized_canonical_url)
        observations = OutboundLinkObservation.objects.filter(
            Q(source_article=article)
            | Q(normalized_destination_url__in=destination_urls)
            | Q(detected_network_link__target_article=article)
        ).distinct()
        for observation in observations.iterator():
            cls.reconcile_observation(observation, now=now)

    @classmethod
    def reconcile_project(cls, project: Project, *, now=None) -> None:
        observation_ids = set(
            OutboundLinkObservation.objects.filter(
                Q(source_article__project=project)
                | Q(detected_network_link__target_project=project)
            ).values_list("id", flat=True)
        )
        destinations = OutboundLinkObservation.objects.only("id", "normalized_destination_url")
        for observation in destinations.iterator():
            try:
                _normalized, host = normalize_sitemap_url(observation.normalized_destination_url)
            except (ValidationError, ValueError):
                continue
            if host == project.normalized_host:
                observation_ids.add(observation.pk)
        for observation in OutboundLinkObservation.objects.filter(
            pk__in=observation_ids
        ).iterator():
            cls.reconcile_observation(observation, now=now)


class DetectedNetworkLinkQueries:
    @staticmethod
    def links_given(owner: Profile, *, active_only: bool = True):
        links = DetectedNetworkLink.objects.filter(source_article__project__owner=owner)
        if active_only:
            links = links.filter(is_active=True)
        return links.select_related("source_article__project", "target_project", "target_article")

    @staticmethod
    def links_received(owner: Profile, *, active_only: bool = True):
        links = DetectedNetworkLink.objects.filter(target_project__owner=owner)
        if active_only:
            links = links.filter(is_active=True)
        return links.select_related("source_article__project", "target_project", "target_article")

    @staticmethod
    def most_cited_pages(owner: Profile, *, active_only: bool = True):
        link_filter = Q(detected_links_received__isnull=False)
        if active_only:
            link_filter &= Q(detected_links_received__is_active=True)
        return (
            Article.objects.filter(project__owner=owner)
            .annotate(
                detected_link_count=Count(
                    "detected_links_received",
                    filter=link_filter,
                    distinct=True,
                )
            )
            .filter(detected_link_count__gt=0)
            .order_by("-detected_link_count", "uuid")
        )

    @staticmethod
    def most_cited_sites(owner: Profile, *, active_only: bool = True):
        link_filter = Q(detected_links_received__isnull=False)
        if active_only:
            link_filter &= Q(detected_links_received__is_active=True)
        return (
            Project.objects.filter(owner=owner)
            .annotate(
                detected_link_count=Count(
                    "detected_links_received",
                    filter=link_filter,
                    distinct=True,
                )
            )
            .filter(detected_link_count__gt=0)
            .order_by("-detected_link_count", "uuid")
        )
