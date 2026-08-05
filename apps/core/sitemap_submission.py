"""Sitemap-only project submission and durable initial-sync staging."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.core.choices import ProjectSyncKinds
from apps.core.crawl_jobs import enqueue_sitemap_sync_safely
from apps.core.funnel_analytics import SITE_SUBMITTED, track_funnel_event
from apps.core.models import Profile, Project, ProjectSyncRequest
from apps.core.projects import ProjectService, normalize_sitemap_url
from apps.core.safe_fetch import SafeFetchClient, SafeFetchError, SafeFetchErrorCode
from apps.core.sitemap_parser import (
    SITEMAP_CONTENT_TYPES,
    SitemapParseError,
    SitemapParseErrorCode,
    parse_sitemap_document,
    sitemap_document_body,
)


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
            allowed_content_types=SITEMAP_CONTENT_TYPES,
        )
    except SafeFetchError as error:
        raise _map_fetch_error(error) from error

    try:
        root_name, _entries = parse_sitemap_document(
            sitemap_document_body(response, settings.CRAWL_MAX_SITEMAP_BYTES),
            max_entries=settings.CRAWL_MAX_SITEMAP_ENTRIES,
        )
    except SitemapParseError as error:
        if error.code == SitemapParseErrorCode.UNSUPPORTED_DOCUMENT:
            code = SitemapSubmissionErrorCode.UNSUPPORTED_DOCUMENT
        elif error.code == SitemapParseErrorCode.INVALID_COMPRESSION:
            code = SitemapSubmissionErrorCode.INVALID_ENCODING
        elif error.code in {SitemapParseErrorCode.ENTRY_LIMIT, SitemapParseErrorCode.TOO_LARGE}:
            code = SitemapSubmissionErrorCode.TOO_LARGE
        else:
            code = SitemapSubmissionErrorCode.INVALID_XML
        raise SitemapSubmissionError(code) from error

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
                idempotency_key=f"initial:{project.uuid}",
            ).first()
            if existing is not None:
                return existing
            raise ValueError("sitemap_kind is required for a new initial sync")

        sync_request, _created = ProjectSyncRequest.objects.get_or_create(
            idempotency_key=f"initial:{project.uuid}",
            defaults={
                "project": project,
                "kind": ProjectSyncKinds.INITIAL,
                "sitemap_kind": sitemap_kind.value,
            },
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
        sitemap_url: str,
        name: str | None = None,
        client: SafeFetchClient | None = None,
    ) -> SitemapSubmission:
        owner = Profile.objects.select_related("user").get(pk=owner.pk)
        if not owner.has_active_subscription:
            raise PermissionDenied("An active subscription is required to add a site.")

        normalized_url, host = normalize_sitemap_url(sitemap_url)
        normalized_name = name.strip() if name is not None else host.removeprefix("www.")[:120]
        if not normalized_name or len(normalized_name) > 120:
            raise ValidationError("Site name must contain 1 to 120 characters.")
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
            transaction.on_commit(
                lambda sync_uuid=sync_request.uuid: enqueue_sitemap_sync_safely(sync_uuid)
            )
            track_funnel_event(
                owner,
                SITE_SUBMITTED,
                {
                    "site_id": str(project.uuid),
                    "sitemap_kind": validation.kind.value,
                },
                idempotency_key=f"project:{project.uuid}",
                source_function="SitemapSubmissionService.submit",
            )
        return SitemapSubmission(project, sync_request, validation.kind)
