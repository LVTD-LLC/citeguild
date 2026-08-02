from __future__ import annotations

import pytest

from apps.core.choices import ExtractionStates, ProjectSyncStates
from apps.core.html_extraction import (
    HtmlExtractionError,
    HtmlExtractionErrorCode,
    PageExtractionService,
    extract_article,
)
from apps.core.models import PageCrawlWork, ProjectSyncRequest
from apps.core.projects import ProjectService
from apps.core.safe_fetch import SafeFetchResult
from apps.core.sitemap_parser import (
    ParsedCandidate,
    SitemapDiagnostics,
    SitemapInventoryService,
    SitemapParseResult,
)

ARTICLE_PARAGRAPHS = """
<p>Semantic search helps independent publishers make their archives useful to
research agents. The crawler first discovers public article URLs from a sitemap.</p>
<p>Each fetched page is reduced to its editorial content and stable metadata.
Navigation, advertisements, cookie prompts, and executable scripts are excluded.</p>
<p>The resulting text is deterministic so later embedding jobs can be idempotent.
Publishers keep control through canonical URLs and standard robots directives.</p>
"""


def response(body: str | bytes, **overrides) -> SafeFetchResult:
    values = {
        "body": body.encode() if isinstance(body, str) else body,
        "content_type": "text/html",
        "final_url": "https://example.com/posts/hello",
        "status": 200,
        "redirect_count": 0,
        "headers": {},
    }
    values.update(overrides)
    return SafeFetchResult(**values)


def article_html(*, head: str = "", body: str = ARTICLE_PARAGRAPHS) -> str:
    return f"""
    <!doctype html>
    <html lang="EN_us">
      <head>
        <title>  A useful article  </title>
        <meta name="description" content="A concise description.">
        {head}
      </head>
      <body>
        <nav>Home Pricing Login Newsletter Archive</nav>
        <aside>Sponsored links and unrelated recommendations</aside>
        <main><article><h1>A useful article</h1>{body}</article></main>
        <div class="cookie-banner">Accept all cookies to continue</div>
        <footer>Copyright and privacy policy</footer>
        <script>window.evil = 'SCRIPT-MUST-NOT-EXECUTE-OR-STORE';</script>
      </body>
    </html>
    """


def test_extracts_readable_text_and_metadata_without_boilerplate(settings):
    settings.EXTRACTION_MIN_TEXT_CHARS = 100
    subject = response(article_html(head='<link rel="canonical" href="../guides/hello#section">'))

    result = extract_article(subject, allowed_host="example.com")

    assert result.state == ExtractionStates.READY
    assert result.final_url == "https://example.com/posts/hello"
    assert result.canonical_url == "https://example.com/guides/hello"
    assert result.http_status == 200
    assert result.title == "A useful article"
    assert result.description == "A concise description."
    assert result.language == "en-us"
    assert "Semantic search helps independent publishers" in result.text
    assert "Navigation, advertisements" in result.text
    assert "Accept all cookies" not in result.text
    assert "Sponsored links" not in result.text
    assert "SCRIPT-MUST-NOT-EXECUTE-OR-STORE" not in result.text
    assert result.text_chars == len(result.text)
    assert result.source_bytes == len(subject.body)


def test_extraction_is_deterministic(settings):
    settings.EXTRACTION_MIN_TEXT_CHARS = 100
    subject = response(article_html())

    assert extract_article(subject, allowed_host="example.com") == extract_article(
        subject,
        allowed_host="example.com",
    )


@pytest.mark.parametrize(
    ("container", "phrase"),
    [
        (
            '<div class="post-content"><h1>Field notes</h1>'
            "<p>Independent field notes explain how editorial citations create "
            "useful discovery paths between trustworthy member archives.</p></div>",
            "Independent field notes",
        ),
        (
            '<div id="story-body"><h1>Daily report</h1>'
            "<p>This newsroom report describes deterministic content processing "
            "for agents that need concise and attributable search results.</p></div>",
            "This newsroom report",
        ),
        (
            '<section itemprop="articleBody"><h1>Technical guide</h1>'
            "<p>The technical guide walks publishers through safe sitemap ingestion "
            "without executing scripts or retaining hostile source documents.</p></section>",
            "The technical guide",
        ),
    ],
)
def test_common_article_layouts_are_readable_without_navigation(
    settings,
    container,
    phrase,
):
    settings.EXTRACTION_MIN_TEXT_CHARS = 40
    document = (
        "<html><head><title>Layout</title></head><body>"
        "<nav>Account Pricing Login Cookie settings</nav>"
        f"{container}"
        "<footer>Terms Privacy Careers</footer>"
        "</body></html>"
    )

    result = extract_article(response(document), allowed_host="example.com")

    assert result.state == ExtractionStates.READY
    assert phrase in result.text
    assert "Account Pricing Login" not in result.text
    assert "Terms Privacy Careers" not in result.text


def test_off_host_canonical_is_rejected(settings):
    settings.EXTRACTION_MIN_TEXT_CHARS = 100
    subject = response(
        article_html(head='<link rel="canonical" href="https://attacker.example/stolen">')
    )

    result = extract_article(subject, allowed_host="example.com")

    assert result.canonical_url == subject.final_url
    assert result.diagnostics == {"canonical_rejected": True}


@pytest.mark.parametrize(
    ("head", "headers"),
    [
        ('<meta name="robots" content="max-image-preview:large, noindex">', {}),
        ("", {"x-robots-tag": "googlebot: noindex"}),
    ],
)
def test_noindex_content_is_never_retained(settings, head, headers):
    settings.EXTRACTION_MIN_TEXT_CHARS = 100

    result = extract_article(
        response(article_html(head=head), headers=headers),
        allowed_host="example.com",
    )

    assert result.state == ExtractionStates.NOINDEX
    assert result.noindex is True
    assert result.text == ""
    assert result.text_chars == 0


def test_empty_or_short_content_is_not_retained(settings):
    settings.EXTRACTION_MIN_TEXT_CHARS = 200

    result = extract_article(
        response(article_html(body="<p>Short announcement.</p>")),
        allowed_host="example.com",
    )

    assert result.state == ExtractionStates.EMPTY
    assert result.text == ""
    assert result.text_chars == 0


def test_empty_response_has_explicit_empty_state():
    result = extract_article(
        response(b"\x00 \n", headers={"content-language": "fr"}),
        allowed_host="example.com",
    )

    assert result.state == ExtractionStates.EMPTY
    assert result.text == ""
    assert result.language == "fr"
    assert result.canonical_url == "https://example.com/posts/hello"


def test_non_html_content_is_rejected():
    with pytest.raises(HtmlExtractionError) as raised:
        extract_article(
            response("plain text", content_type="text/plain"),
            allowed_host="example.com",
        )

    assert raised.value.code == HtmlExtractionErrorCode.UNSUPPORTED_CONTENT
    assert raised.value.retryable is False


def test_invalid_encoding_is_rejected(monkeypatch):
    class NoMatch:
        @staticmethod
        def best():
            return None

    monkeypatch.setattr("apps.core.html_extraction.from_bytes", lambda body: NoMatch())

    with pytest.raises(HtmlExtractionError) as raised:
        extract_article(response(b"\xff\xfe\x00"), allowed_host="example.com")

    assert raised.value.code == HtmlExtractionErrorCode.INVALID_ENCODING


def test_extracted_text_limit_is_enforced(settings, monkeypatch):
    class OversizedExtraction:
        text = "x" * 51
        title = "Article"
        description = ""
        language = "en"
        url = None

    settings.EXTRACTION_MIN_TEXT_CHARS = 1
    settings.EXTRACTION_MAX_TEXT_CHARS = 50
    monkeypatch.setattr(
        "apps.core.html_extraction.trafilatura.bare_extraction",
        lambda *args, **kwargs: OversizedExtraction(),
    )

    with pytest.raises(HtmlExtractionError) as raised:
        extract_article(response(article_html()), allowed_host="example.com")

    assert raised.value.code == HtmlExtractionErrorCode.TEXT_TOO_LARGE


def test_metadata_is_normalized_and_bounded(settings, monkeypatch):
    class MetadataExtraction:
        text = "A sufficiently useful article body for extraction."
        title = "  " + "T" * 350
        description = "  " + "D" * 1200
        language = "EN_us"
        url = None

    settings.EXTRACTION_MIN_TEXT_CHARS = 1
    monkeypatch.setattr(
        "apps.core.html_extraction.trafilatura.bare_extraction",
        lambda *args, **kwargs: MetadataExtraction(),
    )

    result = extract_article(response(article_html()), allowed_host="example.com")

    assert len(result.title) == 300
    assert len(result.description) == 1000
    assert result.language == "en-us"


@pytest.mark.django_db
def test_persistence_is_immutable_and_idempotent(profile, settings):
    settings.EXTRACTION_MIN_TEXT_CHARS = 100
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
        idempotency_key=f"test:{project.uuid}",
        state=ProjectSyncStates.RUNNING,
    )
    parsed = SitemapParseResult(
        (
            ParsedCandidate(
                "https://example.com/posts/hello",
                "https://example.com/posts/hello",
            ),
        ),
        SitemapDiagnostics(1, 1, 1, 0, 0, 0, 0),
    )
    inventory = SitemapInventoryService.promote(
        project=project,
        sync_request=sync,
        result=parsed,
    )
    work = PageCrawlWork.objects.create(
        sync_request=sync,
        candidate=inventory.candidates.get(),
    )
    extraction = extract_article(response(article_html()), allowed_host="example.com")

    first = PageExtractionService.persist(work=work, extraction=extraction)
    second = PageExtractionService.persist(work=work, extraction=extraction)

    assert first.pk == second.pk
    assert first.text == extraction.text
    assert work.extraction.pk == first.pk
