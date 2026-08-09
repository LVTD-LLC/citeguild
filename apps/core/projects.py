from urllib.parse import unquote_plus, urlsplit, urlunsplit

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.choices import ProjectStates
from apps.core.models import Profile, Project, ProjectStateTransition


class ProjectHostConflict(ValidationError):
    pass


OUTBOUND_TRACKING_QUERY_PARAMETERS = frozenset(
    {
        "dclid",
        "fbclid",
        "gclid",
        "gbraid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "utm_campaign",
        "utm_content",
        "utm_creative_format",
        "utm_id",
        "utm_marketing_tactic",
        "utm_medium",
        "utm_source",
        "utm_source_platform",
        "utm_term",
        "wbraid",
    }
)


def normalize_sitemap_url(value: str) -> tuple[str, str]:
    """Return a canonical sitemap URL and its IDNA-normalized host."""
    raw = value.strip()
    if len(raw) > 2048:
        raise ValidationError("Sitemap URL must be 2048 characters or fewer.")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValidationError("Sitemap URL must use HTTP or HTTPS and include a host.")
    if parsed.username or parsed.password:
        raise ValidationError("Sitemap URL must not contain credentials.")

    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise ValidationError("Sitemap URL contains an invalid host or port.") from error
    if not host:
        raise ValidationError("Sitemap URL must include a valid host.")

    scheme = parsed.scheme.lower()
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    path = parsed.path or "/"
    normalized = urlunsplit((scheme, netloc, path, parsed.query, ""))
    return normalized, host


def normalize_outbound_url(value: str) -> tuple[str, str]:
    """Normalize one observed link and remove only known tracking keys."""
    normalized, host = normalize_sitemap_url(value)
    parsed = urlsplit(normalized)
    query_parts = []
    for part in parsed.query.split("&"):
        raw_key, _separator, _value = part.partition("=")
        if unquote_plus(raw_key).casefold() in OUTBOUND_TRACKING_QUERY_PARAMETERS:
            continue
        query_parts.append(part)
    query = "&".join(query_parts) if parsed.query else ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, "")), host


class ProjectService:
    @staticmethod
    def _locked_active_owner(owner: Profile):
        owner = Profile.objects.select_for_update().get(pk=owner.pk)
        if not owner.has_active_subscription:
            raise PermissionDenied("An active subscription is required to manage sites.")
        return owner

    @staticmethod
    def for_owner(owner: Profile):
        return Project.objects.filter(owner=owner)

    @classmethod
    def get_for_owner(cls, owner: Profile, project_uuid):
        return cls.for_owner(owner).get(uuid=project_uuid)

    @staticmethod
    @transaction.atomic
    def create(*, owner: Profile, name: str, sitemap_url: str) -> Project:
        owner = ProjectService._locked_active_owner(owner)
        name = name.strip()
        if not name:
            raise ValidationError("Site name is required.")
        if len(name) > 120:
            raise ValidationError("Site name must be 120 characters or fewer.")
        normalized_url, host = normalize_sitemap_url(sitemap_url)
        try:
            project = Project.objects.create(
                owner=owner,
                name=name,
                sitemap_url=sitemap_url.strip(),
                normalized_sitemap_url=normalized_url,
                normalized_host=host,
            )
        except IntegrityError as error:
            raise ProjectHostConflict(
                "This site host already belongs to a CiteGuild project; "
                "operator resolution is required."
            ) from error
        from apps.core.network_graph import DetectedNetworkLinkService

        DetectedNetworkLinkService.reconcile_project(project)
        from apps.core.domain_ratings import queue_project_domain_rating_refresh

        transaction.on_commit(
            lambda: queue_project_domain_rating_refresh(project.pk),
            robust=True,
        )
        return project

    @classmethod
    @transaction.atomic
    def update(cls, *, owner: Profile, project_uuid, name: str, sitemap_url: str) -> Project:
        owner = cls._locked_active_owner(owner)
        project = cls.get_for_owner(owner, project_uuid)
        name = name.strip()
        if not name:
            raise ValidationError("Site name is required.")
        if len(name) > 120:
            raise ValidationError("Site name must be 120 characters or fewer.")
        normalized_url, host = normalize_sitemap_url(sitemap_url)
        previous_host = project.normalized_host
        project.name = name
        project.sitemap_url = sitemap_url.strip()
        project.normalized_sitemap_url = normalized_url
        project.normalized_host = host
        if host != previous_host:
            project.ahrefs_domain_rating = None
            project.ahrefs_domain_rating_updated_at = None
        try:
            project.save()
        except IntegrityError as error:
            raise ProjectHostConflict(
                "This site host already belongs to a CiteGuild project; "
                "operator resolution is required."
            ) from error
        from apps.core.network_graph import DetectedNetworkLinkService

        DetectedNetworkLinkService.reconcile_project(project)
        if host != previous_host:
            from apps.core.domain_ratings import queue_project_domain_rating_refresh

            transaction.on_commit(
                lambda: queue_project_domain_rating_refresh(project.pk),
                robust=True,
            )
        return project

    @classmethod
    def delete(cls, *, owner: Profile, project_uuid) -> None:
        """Delete one owned site and queue cleanup of its external search points."""
        with transaction.atomic():
            owner = cls._locked_active_owner(owner)
            project = cls.for_owner(owner).select_for_update().get(uuid=project_uuid)
            deleted_uuid = project.uuid
            project.delete()

            from apps.search.qdrant import queue_project_deletion

            transaction.on_commit(lambda: queue_project_deletion(deleted_uuid))

    @classmethod
    def suspend(cls, *, owner: Profile, project_uuid, reason: str) -> Project:
        return cls._transition(
            owner=owner,
            project_uuid=project_uuid,
            to_state=ProjectStates.SUSPENDED,
            reason=reason,
        )

    @classmethod
    def reactivate(cls, *, owner: Profile, project_uuid) -> Project:
        return cls._transition(
            owner=owner,
            project_uuid=project_uuid,
            to_state=ProjectStates.ACTIVE,
            reason="",
        )

    @classmethod
    @transaction.atomic
    def _transition(cls, *, owner, project_uuid, to_state, reason):
        owner = cls._locked_active_owner(owner)
        project = cls.for_owner(owner).select_for_update().get(uuid=project_uuid)
        if project.state == to_state:
            return project
        previous = project.state
        project.state = to_state
        project.suspension_reason = reason if to_state == ProjectStates.SUSPENDED else ""
        project.suspended_at = timezone.now() if to_state == ProjectStates.SUSPENDED else None
        project.save()
        ProjectStateTransition.objects.create(
            project=project,
            actor=owner,
            from_state=previous,
            to_state=to_state,
            reason=reason,
        )
        from apps.core.network_graph import DetectedNetworkLinkService

        DetectedNetworkLinkService.reconcile_project(project)
        return project
