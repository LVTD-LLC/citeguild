"""Bounded sitemap discovery and atomic candidate inventory promotion."""

from __future__ import annotations

import io
import zlib
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from urllib.parse import urlsplit

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import (
    Project,
    ProjectSyncRequest,
    SitemapCandidate,
    SitemapInventory,
)
from apps.core.projects import normalize_sitemap_url
from apps.core.safe_fetch import SafeFetchClient, SafeFetchError, SafeFetchResult

SITEMAP_CONTENT_TYPES = frozenset(
    {"application/xml", "text/xml", "application/gzip", "application/x-gzip"}
)


class SitemapParseErrorCode(StrEnum):
    FETCH_FAILED = "fetch_failed"
    INVALID_XML = "invalid_xml"
    INVALID_COMPRESSION = "invalid_compression"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    ENTRY_LIMIT = "entry_limit"
    TOO_LARGE = "too_large"
    SITEMAP_LIMIT = "sitemap_limit"
    DEPTH_LIMIT = "depth_limit"
    INVALID_CHILD_SITEMAP = "invalid_child_sitemap"
    DISALLOWED_CHILD_HOST = "disallowed_child_host"
    REDIRECTED_OFF_HOST = "redirected_off_host"


class SitemapParseError(Exception):
    """A sanitized parser failure suitable for persisted worker diagnostics."""

    def __init__(self, code: SitemapParseErrorCode, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class ParsedCandidate:
    url: str
    normalized_url: str
    lastmod_hint: str = ""


@dataclass(frozen=True, slots=True)
class SitemapDiagnostics:
    sitemap_count: int
    raw_entry_count: int
    candidate_count: int
    duplicate_count: int
    invalid_url_count: int
    disallowed_host_count: int
    invalid_lastmod_count: int

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SitemapParseResult:
    candidates: tuple[ParsedCandidate, ...]
    diagnostics: SitemapDiagnostics


@dataclass(frozen=True, slots=True)
class SitemapParserLimits:
    max_bytes: int
    max_entries: int
    max_depth: int
    max_sitemap_files: int

    @classmethod
    def from_django_settings(cls) -> SitemapParserLimits:
        return cls(
            max_bytes=settings.CRAWL_MAX_SITEMAP_BYTES,
            max_entries=settings.CRAWL_MAX_SITEMAP_ENTRIES,
            max_depth=settings.CRAWL_MAX_SITEMAP_DEPTH,
            max_sitemap_files=settings.CRAWL_MAX_SITEMAP_FILES,
        )


@dataclass(frozen=True, slots=True)
class _DocumentEntry:
    location: str
    lastmod: str = ""


@dataclass(slots=True)
class _ParseState:
    pending: deque[tuple[str, int]]
    visited: set[str]
    candidates: dict[str, ParsedCandidate]
    raw_entry_count: int = 0
    duplicate_count: int = 0
    invalid_url_count: int = 0
    disallowed_host_count: int = 0
    invalid_lastmod_count: int = 0


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _entry_from_element(element) -> _DocumentEntry:
    values = {
        _local_name(child.tag): (child.text or "").strip()
        for child in element
        if _local_name(child.tag) in {"loc", "lastmod"}
    }
    return _DocumentEntry(values.get("loc", ""), values.get("lastmod", ""))


def _validated_root_kind(element) -> str:
    root_kind = _local_name(element.tag)
    if root_kind not in {"urlset", "sitemapindex"}:
        raise SitemapParseError(SitemapParseErrorCode.UNSUPPORTED_DOCUMENT)
    return root_kind


def _bounded_gzip_decode(body: bytes, max_bytes: int) -> bytes:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        decoded = decoder.decompress(body, max_bytes + 1)
        if len(decoded) > max_bytes or decoder.unconsumed_tail:
            raise SitemapParseError(SitemapParseErrorCode.TOO_LARGE)
        decoded += decoder.flush(max_bytes + 1 - len(decoded))
    except zlib.error as error:
        raise SitemapParseError(SitemapParseErrorCode.INVALID_COMPRESSION) from error
    if len(decoded) > max_bytes or not decoder.eof:
        raise SitemapParseError(SitemapParseErrorCode.INVALID_COMPRESSION)
    return decoded


def sitemap_document_body(response: SafeFetchResult, max_bytes: int) -> bytes:
    is_gzip = response.content_type in {"application/gzip", "application/x-gzip"}
    if response.body.startswith(b"\x1f\x8b"):
        is_gzip = True
    if is_gzip:
        return _bounded_gzip_decode(response.body, max_bytes)
    return response.body


def parse_sitemap_document(
    body: bytes,
    *,
    max_entries: int,
) -> tuple[str, tuple[_DocumentEntry, ...]]:
    root = None
    root_kind = ""
    entries: list[_DocumentEntry] = []
    try:
        for event, element in ElementTree.iterparse(io.BytesIO(body), events=("start", "end")):
            name = _local_name(element.tag)
            if root is None and event == "start":
                root = element
                root_kind = _validated_root_kind(element)
                continue
            expected_entry = "url" if root_kind == "urlset" else "sitemap"
            if event != "end" or name != expected_entry:
                continue
            entries.append(_entry_from_element(element))
            if len(entries) > max_entries:
                raise SitemapParseError(SitemapParseErrorCode.ENTRY_LIMIT)
            element.clear()
            if root is not None:
                try:
                    root.remove(element)
                except ValueError:
                    pass
    except SitemapParseError:
        raise
    except (ElementTree.ParseError, DefusedXmlException) as error:
        raise SitemapParseError(SitemapParseErrorCode.INVALID_XML) from error
    if root is None:
        raise SitemapParseError(SitemapParseErrorCode.INVALID_XML)
    return root_kind, tuple(entries)


def _normalized_lastmod(value: str) -> str:
    if not value or len(value) > 40:
        return ""
    try:
        if "T" not in value:
            return date.fromisoformat(value).isoformat()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat()


def _normalize_allowed_url(value: str, allowed_host: str) -> tuple[str, str] | None:
    try:
        normalized, host = normalize_sitemap_url(value)
        parsed = urlsplit(normalized)
    except (ValidationError, ValueError):
        return None
    expected_port = 443 if parsed.scheme == "https" else 80
    if parsed.port not in {None, expected_port}:
        return None
    if host != allowed_host:
        return (normalized, "")
    return normalized, host


class SitemapParser:
    def __init__(
        self,
        *,
        allowed_host: str,
        client: SafeFetchClient | None = None,
        limits: SitemapParserLimits | None = None,
    ):
        self.allowed_host = allowed_host
        self.client = client or SafeFetchClient.from_django_settings()
        self.limits = limits or SitemapParserLimits.from_django_settings()

    def parse(self, root_url: str) -> SitemapParseResult:
        state = _ParseState(deque([(root_url, 0)]), set(), {})
        while state.pending:
            requested_url, depth = state.pending.popleft()
            self._parse_one(state, requested_url, depth)

        ordered = tuple(state.candidates[url] for url in sorted(state.candidates))
        diagnostics = SitemapDiagnostics(
            sitemap_count=len(state.visited),
            raw_entry_count=state.raw_entry_count,
            candidate_count=len(ordered),
            duplicate_count=state.duplicate_count,
            invalid_url_count=state.invalid_url_count,
            disallowed_host_count=state.disallowed_host_count,
            invalid_lastmod_count=state.invalid_lastmod_count,
        )
        return SitemapParseResult(ordered, diagnostics)

    def _parse_one(self, state: _ParseState, requested_url: str, depth: int) -> None:
        normalized_url = self._normalize_child_sitemap(requested_url)
        if normalized_url in state.visited:
            return
        if len(state.visited) >= self.limits.max_sitemap_files:
            raise SitemapParseError(SitemapParseErrorCode.SITEMAP_LIMIT)
        state.visited.add(normalized_url)
        response = self._fetch(normalized_url)
        final_url = _normalize_allowed_url(response.final_url, self.allowed_host)
        if final_url is None or not final_url[1]:
            raise SitemapParseError(SitemapParseErrorCode.REDIRECTED_OFF_HOST)
        kind, entries = parse_sitemap_document(
            sitemap_document_body(response, self.limits.max_bytes),
            max_entries=self.limits.max_entries - state.raw_entry_count,
        )
        state.raw_entry_count += len(entries)
        if kind == "sitemapindex":
            self._queue_children(state, entries, depth)
        else:
            self._add_candidates(state, entries)

    def _normalize_child_sitemap(self, value: str) -> str:
        normalized = _normalize_allowed_url(value, self.allowed_host)
        if normalized is None:
            raise SitemapParseError(SitemapParseErrorCode.INVALID_CHILD_SITEMAP)
        url, host = normalized
        if not host:
            raise SitemapParseError(SitemapParseErrorCode.DISALLOWED_CHILD_HOST)
        return url

    def _fetch(self, normalized_url: str) -> SafeFetchResult:
        try:
            return self.client.fetch(
                normalized_url,
                max_bytes=self.limits.max_bytes,
                allowed_content_types=SITEMAP_CONTENT_TYPES,
            )
        except SafeFetchError as error:
            raise SitemapParseError(
                SitemapParseErrorCode.FETCH_FAILED,
                retryable=error.retryable,
            ) from error

    def _queue_children(
        self,
        state: _ParseState,
        entries: tuple[_DocumentEntry, ...],
        depth: int,
    ) -> None:
        if entries and depth >= self.limits.max_depth:
            raise SitemapParseError(SitemapParseErrorCode.DEPTH_LIMIT)
        state.pending.extend((entry.location, depth + 1) for entry in entries)

    def _add_candidates(
        self,
        state: _ParseState,
        entries: tuple[_DocumentEntry, ...],
    ) -> None:
        for entry in entries:
            normalized_entry = _normalize_allowed_url(entry.location, self.allowed_host)
            if normalized_entry is None:
                state.invalid_url_count += 1
                continue
            normalized, host = normalized_entry
            if not host:
                state.disallowed_host_count += 1
                continue
            lastmod = _normalized_lastmod(entry.lastmod)
            if entry.lastmod and not lastmod:
                state.invalid_lastmod_count += 1
            candidate = ParsedCandidate(normalized, normalized, lastmod)
            previous = state.candidates.get(normalized)
            if previous is not None:
                state.duplicate_count += 1
                if previous.lastmod_hint >= candidate.lastmod_hint:
                    continue
            state.candidates[normalized] = candidate


class SitemapInventoryService:
    @staticmethod
    @transaction.atomic
    def promote(
        *,
        project: Project,
        sync_request: ProjectSyncRequest,
        result: SitemapParseResult,
    ) -> SitemapInventory:
        project = Project.objects.select_for_update().get(pk=project.pk)
        sync_request = ProjectSyncRequest.objects.select_for_update().get(pk=sync_request.pk)
        if sync_request.project_id != project.pk:
            raise ValueError("The sync request does not belong to this project.")

        existing = SitemapInventory.objects.filter(sync_request=sync_request).first()
        if existing is not None:
            if project.active_sitemap_inventory_id != existing.pk:
                project.active_sitemap_inventory = existing
                project.save(update_fields=["active_sitemap_inventory", "updated_at"])
            return existing

        inventory = SitemapInventory.objects.create(
            project=project,
            sync_request=sync_request,
            candidate_count=len(result.candidates),
            sitemap_count=result.diagnostics.sitemap_count,
            diagnostics=result.diagnostics.as_dict(),
        )
        SitemapCandidate.objects.bulk_create(
            [
                SitemapCandidate(
                    inventory=inventory,
                    url=candidate.url,
                    normalized_url=candidate.normalized_url,
                    lastmod_hint=candidate.lastmod_hint,
                )
                for candidate in result.candidates
            ],
            batch_size=1000,
        )
        project.active_sitemap_inventory = inventory
        project.save(update_fields=["active_sitemap_inventory", "updated_at"])
        return inventory
