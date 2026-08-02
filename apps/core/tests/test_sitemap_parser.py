import gzip

import pytest

from apps.core.models import ProjectSyncRequest, SitemapCandidate, SitemapInventory
from apps.core.projects import ProjectService
from apps.core.safe_fetch import SafeFetchError, SafeFetchErrorCode, SafeFetchResult
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseError,
    SitemapParseErrorCode,
    SitemapParser,
    SitemapParseResult,
    SitemapParserLimits,
)


class MappingFetchClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch(self, url, *, max_bytes, allowed_content_types):
        self.calls.append((url, max_bytes, allowed_content_types))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def response(url, body, content_type="application/xml"):
    return SafeFetchResult(
        body=body,
        content_type=content_type,
        final_url=url,
        status=200,
        redirect_count=0,
    )


def parser(responses, **limits):
    defaults = {
        "max_bytes": 10_000,
        "max_entries": 100,
        "max_depth": 3,
        "max_sitemap_files": 10,
    }
    defaults.update(limits)
    return SitemapParser(
        allowed_host="example.com",
        client=MappingFetchClient(responses),
        limits=SitemapParserLimits(**defaults),
    )


def test_namespaced_urlset_is_deduplicated_sorted_and_diagnosed():
    url = "https://example.com/sitemap.xml"
    body = b"""<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://example.com/z</loc><lastmod>2026-01-01</lastmod></url>
      <url><loc>https://EXAMPLE.com/a#fragment</loc><lastmod>bad</lastmod></url>
      <url><loc>https://example.com/z</loc><lastmod>2026-02-01</lastmod></url>
      <url><loc>https://other.example/page</loc></url>
      <url><loc>javascript:alert(1)</loc></url>
    </urlset>"""

    result = parser({url: response(url, body)}).parse(url)

    assert result.candidates == (
        ParsedCandidate("https://example.com/a", "https://example.com/a"),
        ParsedCandidate(
            "https://example.com/z",
            "https://example.com/z",
            "2026-02-01",
        ),
    )
    assert result.diagnostics == SitemapDiagnostics(
        sitemap_count=1,
        raw_entry_count=5,
        candidate_count=2,
        duplicate_count=1,
        invalid_url_count=1,
        disallowed_host_count=1,
        invalid_lastmod_count=1,
    )


def test_sitemap_index_recurses_and_accepts_bounded_gzip():
    root = "https://example.com/sitemap.xml"
    child = "https://example.com/posts.xml.gz"
    index = f"<sitemapindex><sitemap><loc>{child}</loc></sitemap></sitemapindex>".encode()
    child_body = gzip.compress(b"<urlset><url><loc>https://example.com/post</loc></url></urlset>")
    subject = parser(
        {
            root: response(root, index),
            child: response(child, child_body, "application/gzip"),
        }
    )

    result = subject.parse(root)

    assert [candidate.normalized_url for candidate in result.candidates] == [
        "https://example.com/post"
    ]
    assert result.diagnostics.sitemap_count == 2
    assert [call[0] for call in subject.client.calls] == [root, child]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"\x1f\x8bnot-gzip", SitemapParseErrorCode.INVALID_COMPRESSION),
        (
            gzip.compress(b"<urlset>" + b" " * 500 + b"</urlset>"),
            SitemapParseErrorCode.TOO_LARGE,
        ),
    ],
)
def test_gzip_is_validated_and_decompressed_within_the_byte_limit(body, code):
    root = "https://example.com/sitemap.xml.gz"

    with pytest.raises(SitemapParseError) as error:
        parser(
            {root: response(root, body, "application/gzip")},
            max_bytes=100,
        ).parse(root)

    assert error.value.code == code


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"<urlset>", SitemapParseErrorCode.INVALID_XML),
        (b"<html />", SitemapParseErrorCode.UNSUPPORTED_DOCUMENT),
        (
            b"<!DOCTYPE urlset [<!ENTITY x 'boom'>]><urlset>&x;</urlset>",
            SitemapParseErrorCode.INVALID_XML,
        ),
    ],
)
def test_malformed_unsafe_and_unsupported_xml_fail_closed(body, code):
    url = "https://example.com/sitemap.xml"

    with pytest.raises(SitemapParseError) as error:
        parser({url: response(url, body)}).parse(url)

    assert error.value.code == code


def test_child_sitemap_must_remain_on_project_host():
    root = "https://example.com/sitemap.xml"
    body = b"<sitemapindex><sitemap><loc>https://other.example/a.xml</loc></sitemap></sitemapindex>"

    with pytest.raises(SitemapParseError) as error:
        parser({root: response(root, body)}).parse(root)

    assert error.value.code == SitemapParseErrorCode.DISALLOWED_CHILD_HOST


def test_redirected_sitemap_must_remain_on_project_host():
    root = "https://example.com/sitemap.xml"
    redirected = response(root, b"<urlset />")
    redirected = SafeFetchResult(
        body=redirected.body,
        content_type=redirected.content_type,
        final_url="https://other.example/sitemap.xml",
        status=200,
        redirect_count=1,
    )

    with pytest.raises(SitemapParseError) as error:
        parser({root: redirected}).parse(root)

    assert error.value.code == SitemapParseErrorCode.REDIRECTED_OFF_HOST


@pytest.mark.parametrize(
    ("limits", "root_body", "responses", "code"),
    [
        (
            {"max_entries": 1},
            b"<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/b</loc></url></urlset>",
            {},
            SitemapParseErrorCode.ENTRY_LIMIT,
        ),
        (
            {"max_depth": 0},
            b"<sitemapindex><sitemap><loc>https://example.com/a.xml</loc></sitemap></sitemapindex>",
            {},
            SitemapParseErrorCode.DEPTH_LIMIT,
        ),
        (
            {"max_sitemap_files": 1},
            b"<sitemapindex><sitemap><loc>https://example.com/a.xml</loc></sitemap></sitemapindex>",
            {"https://example.com/a.xml": response("https://example.com/a.xml", b"<urlset />")},
            SitemapParseErrorCode.SITEMAP_LIMIT,
        ),
    ],
)
def test_global_entry_depth_and_sitemap_limits_are_enforced(limits, root_body, responses, code):
    root = "https://example.com/sitemap.xml"
    responses = {root: response(root, root_body), **responses}

    with pytest.raises(SitemapParseError) as error:
        parser(responses, **limits).parse(root)

    assert error.value.code == code


def test_fetch_failure_preserves_retryability_without_leaking_details():
    root = "https://example.com/private?token=secret"
    subject = parser({root: SafeFetchError(SafeFetchErrorCode.TIMEOUT, retryable=True)})

    with pytest.raises(SitemapParseError) as error:
        subject.parse(root)

    assert error.value.code == SitemapParseErrorCode.FETCH_FAILED
    assert error.value.retryable is True
    assert "secret" not in str(error.value)


@pytest.mark.django_db
def test_inventory_promotion_is_idempotent_and_sorted(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    project = ProjectService.create(
        owner=profile,
        name="Example",
        sitemap_url="https://example.com/sitemap.xml",
    )
    sync = ProjectSyncRequest.objects.create(
        project=project,
        sitemap_kind="urlset",
    )
    result = SitemapParseResult(
        candidates=(
            ParsedCandidate("https://example.com/b", "https://example.com/b"),
            ParsedCandidate("https://example.com/a", "https://example.com/a", "2026-01-01"),
        ),
        diagnostics=SitemapDiagnostics(1, 2, 2, 0, 0, 0, 0),
    )

    inventory = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=result,
    )
    duplicate = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=result,
    )

    assert duplicate.pk == inventory.pk
    assert list(inventory.candidates.values_list("normalized_url", flat=True)) == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    project.refresh_from_db()
    assert project.active_sitemap_inventory == inventory


@pytest.mark.django_db(transaction=True)
def test_failed_inventory_write_does_not_replace_previous_active_set(profile, monkeypatch):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    project = ProjectService.create(
        owner=profile,
        name="Example",
        sitemap_url="https://example.com/sitemap.xml",
    )
    previous_sync = ProjectSyncRequest.objects.create(
        project=project,
        kind="initial",
        state="succeeded",
        sitemap_kind="urlset",
    )
    previous = SitemapInventory.objects.create(
        project=project,
        sync_request=previous_sync,
        candidate_count=1,
        sitemap_count=1,
    )
    SitemapCandidate.objects.create(
        inventory=previous,
        url="https://example.com/old",
        normalized_url="https://example.com/old",
    )
    project.active_sitemap_inventory = previous
    project.save(update_fields=["active_sitemap_inventory", "updated_at"])
    next_sync = ProjectSyncRequest.objects.create(
        project=project,
        kind="daily",
        sitemap_kind="urlset",
    )
    result = SitemapParseResult(
        (ParsedCandidate("https://example.com/new", "https://example.com/new"),),
        SitemapDiagnostics(1, 1, 1, 0, 0, 0, 0),
    )
    monkeypatch.setattr(
        SitemapCandidate.objects,
        "bulk_create",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("write failed")),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        SitemapInventoryService.promote(
            project=project,
            sync_request=next_sync,
            result=result,
        )

    project.refresh_from_db()
    assert project.active_sitemap_inventory == previous
    assert not SitemapInventory.objects.filter(sync_request=next_sync).exists()
