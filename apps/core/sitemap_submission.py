"""Sitemap-only project submission and durable initial-sync staging."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core.choices import ProjectSyncKinds
from apps.core.models import Profile, Project, ProjectSyncRequest
from apps.core.projects import ProjectService, normalize_sitemap_url
from apps.core.safe_fetch import SafeFetchClient, SafeFetchError, SafeFetchErrorCode


class SitemapDocumentKind(StrEnum):
    URL_SET = "urlset"
    SITEMAP_INDEX = "sitemap_index"


class SitemapSubmissionErrorCode(StrEnum):
    BLOCKED_DESTINATION = "blocked_destination"
    TEMPORARY_FETCH = "temporary_fetch"
    INVALID_CONTENT_TYPE = "invalid_content_type"
    INVALID_ENCODING = "invalid_encoding"
    TOO_LARGE = "too_large"
    UNAVAILABLE = "unavailable"
    INVALID_XML = "invalid_xml"
    UNSUPPORTED_DOCUMENT = "unsupported_document"


_ERROR_MESSAGES = {
    SitemapSubmissionErrorCode.BLOCKED_DESTINATION: (
        "The sitemap destination is not allowed. Use a public HTTP or HTTPS URL."
    ),
    SitemapSubmissionErrorCode.TEMPORARY_FETCH: (
        "The sitemap could not be reached right now. Try again."
    ),
    SitemapSubmissionErrorCode.INVALID_CONTENT_TYPE: ("The URL did not return an XML sitemap."),
    SitemapSubmissionErrorCode.INVALID_ENCODING: (
        "The sitemap uses an invalid or unsupported content encoding."
    ),
    SitemapSubmissionErrorCode.TOO_LARGE: "The sitemap exceeds the allowed validation size.",
    SitemapSubmissionErrorCode.UNAVAILABLE: "The sitemap URL is unavailable.",
    SitemapSubmissionErrorCode.INVALID_XML: "The sitemap contains invalid or unsafe XML.",
    SitemapSubmissionErrorCode.UNSUPPORTED_DOCUMENT: (
        "The XML document is not a sitemap or sitemap index."
    ),
}


class SitemapSubmissionError(Exception):
    def __init__(self, code: SitemapSubmissionErrorCode, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(_ERROR_MESSAGES[code])

    def as_dict(self) -> dict:
        return {"code": self.code.value, "message": str(self), "retryable": self.retryable}


@dataclass(frozen=True, slots=True)
class SitemapValidation:
    kind: SitemapDocumentKind


@dataclass(frozen=True, slots=True)
class SitemapSubmission:
    project: Project
    sync_request: ProjectSyncRequest
    sitemap_kind: SitemapDocumentKind


_FETCH_ERROR_MAP = {
    SafeFetchErrorCode.BLOCKED_ADDRESS: SitemapSubmissionErrorCode.BLOCKED_DESTINATION,
    SafeFetchErrorCode.BLOCKED_PORT: SitemapSubmissionErrorCode.BLOCKED_DESTINATION,
    SafeFetchErrorCode.INVALID_URL: SitemapSubmissionErrorCode.BLOCKED_DESTINATION,
    SafeFetchErrorCode.UNSUPPORTED_CONTENT_TYPE: (SitemapSubmissionErrorCode.INVALID_CONTENT_TYPE),
    SafeFetchErrorCode.UNSUPPORTED_CONTENT_ENCODING: (SitemapSubmissionErrorCode.INVALID_ENCODING),
    SafeFetchErrorCode.INVALID_CONTENT_ENCODING: SitemapSubmissionErrorCode.INVALID_ENCODING,
    SafeFetchErrorCode.BODY_TOO_LARGE: SitemapSubmissionErrorCode.TOO_LARGE,
    SafeFetchErrorCode.TOO_MANY_REDIRECTS: SitemapSubmissionErrorCode.UNAVAILABLE,
    SafeFetchErrorCode.TLS_ERROR: SitemapSubmissionErrorCode.UNAVAILABLE,
    SafeFetchErrorCode.HTTP_ERROR: SitemapSubmissionErrorCode.UNAVAILABLE,
}


def _map_fetch_error(error: SafeFetchError) -> SitemapSubmissionError:
    code = _FETCH_ERROR_MAP.get(error.code)
    if code is not None:
        return SitemapSubmissionError(code)
    if not error.retryable:
        return SitemapSubmissionError(SitemapSubmissionErrorCode.UNAVAILABLE)
    return SitemapSubmissionError(
        SitemapSubmissionErrorCode.TEMPORARY_FETCH,
        retryable=True,
    )


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_sitemap(
    sitemap_url: str,
    *,
    client: SafeFetchClient | None = None,
) -> SitemapValidation:
    client = client or SafeFetchClient.from_django_settings()
    try:
        response = client.fetch(
            sitemap_url,
            max_bytes=settings.CRAWL_MAX_SITEMAP_BYTES,
            allowed_content_types={"application/xml", "text/xml"},
        )
    except SafeFetchError as error:
        raise _map_fetch_error(error) from error

    try:
        root = ElementTree.fromstring(response.body)
    except (ElementTree.ParseError, DefusedXmlException) as error:
        raise SitemapSubmissionError(SitemapSubmissionErrorCode.INVALID_XML) from error

    root_name = _local_name(root.tag)
    if root_name == "urlset":
        return SitemapValidation(SitemapDocumentKind.URL_SET)
    if root_name == "sitemapindex":
        return SitemapValidation(SitemapDocumentKind.SITEMAP_INDEX)
    raise SitemapSubmissionError(SitemapSubmissionErrorCode.UNSUPPORTED_DOCUMENT)


class SitemapSubmissionService:
    @staticmethod
    @transaction.atomic
    def enqueue_initial_sync(
        project: Project,
        *,
        sitemap_kind: SitemapDocumentKind | None = None,
    ) -> ProjectSyncRequest:
        if sitemap_kind is None:
            existing = ProjectSyncRequest.objects.filter(
                project=project,
                kind=ProjectSyncKinds.INITIAL,
            ).first()
            if existing is not None:
                return existing
            raise ValueError("sitemap_kind is required for a new initial sync")

        sync_request, _created = ProjectSyncRequest.objects.get_or_create(
            project=project,
            kind=ProjectSyncKinds.INITIAL,
            defaults={"sitemap_kind": sitemap_kind.value},
        )
        if project.current_sync_uuid != sync_request.uuid:
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
        return sync_request

    @classmethod
    def submit(
        cls,
        *,
        owner: Profile,
        name: str,
        sitemap_url: str,
        client: SafeFetchClient | None = None,
    ) -> SitemapSubmission:
        owner = Profile.objects.select_related("user").get(pk=owner.pk)
        if not owner.has_active_subscription:
            raise PermissionDenied("An active subscription is required to add a site.")

        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 120:
            raise ValidationError("Site name must contain 1 to 120 characters.")
        normalized_url, _host = normalize_sitemap_url(sitemap_url)
        validation = validate_sitemap(normalized_url, client=client)

        with transaction.atomic():
            project = ProjectService.create(
                owner=owner,
                name=normalized_name,
                sitemap_url=normalized_url,
            )
            sync_request = cls.enqueue_initial_sync(
                project,
                sitemap_kind=validation.kind,
            )
        return SitemapSubmission(project, sync_request, validation.kind)
