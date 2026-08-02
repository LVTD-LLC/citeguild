import gzip

import pytest
from django.core.exceptions import PermissionDenied

from apps.core.models import ProjectSyncRequest
from apps.core.safe_fetch import SafeFetchError, SafeFetchErrorCode, SafeFetchResult
from apps.core.sitemap_submission import (
    SitemapDocumentKind,
    SitemapSubmissionError,
    SitemapSubmissionErrorCode,
    SitemapSubmissionService,
    validate_sitemap,
)


class RecordingFetchClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def fetch(self, url, *, max_bytes, allowed_content_types):
        self.calls.append((url, max_bytes, allowed_content_types))
        if self.error:
            raise self.error
        return self.result


def fetch_result(body, content_type="application/xml"):
    return SafeFetchResult(
        body=body,
        content_type=content_type,
        final_url="https://example.com/sitemap.xml",
        status=200,
        redirect_count=0,
    )


@pytest.mark.parametrize(
    ("root", "kind"),
    [
        ("urlset", SitemapDocumentKind.URL_SET),
        ("sitemapindex", SitemapDocumentKind.SITEMAP_INDEX),
    ],
)
def test_validate_sitemap_accepts_supported_xml_roots(settings, root, kind):
    settings.CRAWL_MAX_SITEMAP_BYTES = 1234
    client = RecordingFetchClient(
        fetch_result(f'<{root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" />'.encode())
    )

    result = validate_sitemap("https://example.com/sitemap.xml", client=client)

    assert result.kind == kind
    assert client.calls == [
        (
            "https://example.com/sitemap.xml",
            1234,
            {"application/xml", "text/xml", "application/gzip", "application/x-gzip"},
        )
    ]


def test_validate_sitemap_accepts_gzip_document(settings):
    settings.CRAWL_MAX_SITEMAP_BYTES = 1234
    settings.CRAWL_MAX_SITEMAP_ENTRIES = 10
    client = RecordingFetchClient(
        fetch_result(gzip.compress(b"<urlset />"), content_type="application/gzip")
    )

    result = validate_sitemap("https://example.com/sitemap.xml.gz", client=client)

    assert result.kind == SitemapDocumentKind.URL_SET


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"<urlset>", SitemapSubmissionErrorCode.INVALID_XML),
        (b"<html />", SitemapSubmissionErrorCode.UNSUPPORTED_DOCUMENT),
        (
            b"<!DOCTYPE urlset [<!ENTITY x 'boom'>]><urlset>&x;</urlset>",
            SitemapSubmissionErrorCode.INVALID_XML,
        ),
    ],
)
def test_validate_sitemap_rejects_invalid_or_unsafe_xml(body, code):
    client = RecordingFetchClient(fetch_result(body))

    with pytest.raises(SitemapSubmissionError) as error:
        validate_sitemap("https://example.com/sitemap.xml", client=client)

    assert error.value.code == code
    assert error.value.retryable is False


@pytest.mark.parametrize(
    ("fetch_code", "submission_code", "retryable"),
    [
        (
            SafeFetchErrorCode.BLOCKED_ADDRESS,
            SitemapSubmissionErrorCode.BLOCKED_DESTINATION,
            False,
        ),
        (SafeFetchErrorCode.TIMEOUT, SitemapSubmissionErrorCode.TEMPORARY_FETCH, True),
        (SafeFetchErrorCode.DNS_FAILURE, SitemapSubmissionErrorCode.TEMPORARY_FETCH, True),
        (
            SafeFetchErrorCode.UNSUPPORTED_CONTENT_TYPE,
            SitemapSubmissionErrorCode.INVALID_CONTENT_TYPE,
            False,
        ),
        (SafeFetchErrorCode.BODY_TOO_LARGE, SitemapSubmissionErrorCode.TOO_LARGE, False),
        (
            SafeFetchErrorCode.INVALID_CONTENT_ENCODING,
            SitemapSubmissionErrorCode.INVALID_ENCODING,
            False,
        ),
        (SafeFetchErrorCode.HTTP_ERROR, SitemapSubmissionErrorCode.UNAVAILABLE, False),
    ],
)
def test_validate_sitemap_maps_safe_fetch_errors(fetch_code, submission_code, retryable):
    client = RecordingFetchClient(error=SafeFetchError(fetch_code, retryable=retryable))

    with pytest.raises(SitemapSubmissionError) as error:
        validate_sitemap("https://example.com/private?token=secret", client=client)

    assert error.value.code == submission_code
    assert error.value.retryable is retryable
    assert "secret" not in str(error.value)


@pytest.mark.django_db
def test_valid_submission_creates_project_and_one_idempotent_initial_sync(profile):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    client = RecordingFetchClient(fetch_result(b"<urlset />"))

    submission = SitemapSubmissionService.submit(
        owner=profile,
        name="Example",
        sitemap_url="https://EXAMPLE.com/sitemap.xml",
        client=client,
    )
    duplicate = SitemapSubmissionService.enqueue_initial_sync(submission.project)

    assert submission.project.owner == profile
    assert submission.project.normalized_host == "example.com"
    assert submission.sitemap_kind == SitemapDocumentKind.URL_SET
    assert duplicate.pk == submission.sync_request.pk
    assert ProjectSyncRequest.objects.filter(project=submission.project).count() == 1
    submission.project.refresh_from_db()
    assert submission.project.current_sync_uuid == submission.sync_request.uuid


@pytest.mark.django_db
def test_submission_enqueues_only_after_commit(
    profile,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    enqueued = []
    monkeypatch.setattr(
        "apps.core.sitemap_submission.enqueue_sitemap_sync_safely",
        lambda sync_uuid: enqueued.append(sync_uuid),
    )

    with django_capture_on_commit_callbacks(execute=True):
        submission = SitemapSubmissionService.submit(
            owner=profile,
            name="Queued",
            sitemap_url="https://queued.example/sitemap.xml",
            client=RecordingFetchClient(fetch_result(b"<urlset />")),
        )
        assert enqueued == []

    assert enqueued == [submission.sync_request.uuid]


@pytest.mark.django_db
def test_unsubscribed_submission_does_not_fetch_or_create_site(profile):
    client = RecordingFetchClient(fetch_result(b"<urlset />"))

    with pytest.raises(PermissionDenied):
        SitemapSubmissionService.submit(
            owner=profile,
            name="Blocked",
            sitemap_url="https://blocked.example/sitemap.xml",
            client=client,
        )

    assert client.calls == []
    assert not ProjectSyncRequest.objects.exists()


def test_submission_error_exposes_only_stable_safe_fields():
    error = SitemapSubmissionError(SitemapSubmissionErrorCode.TEMPORARY_FETCH, retryable=True)

    assert error.as_dict() == {
        "code": "temporary_fetch",
        "message": "The sitemap could not be reached right now. Try again.",
        "retryable": True,
    }
    assert not hasattr(error, "url")
