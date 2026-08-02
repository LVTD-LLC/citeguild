"""Deterministic, bounded extraction for hostile fetched HTML."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from enum import StrEnum
from urllib.parse import urljoin

import trafilatura
from charset_normalizer import from_bytes
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from lxml import etree, html
from trafilatura.settings import Extractor, use_config

from apps.core.choices import ExtractionStates
from apps.core.models import PageCrawlWork, PageExtractionResult
from apps.core.projects import normalize_outbound_url, normalize_sitemap_url
from apps.core.safe_fetch import SafeFetchResult


class HtmlExtractionErrorCode(StrEnum):
    UNSUPPORTED_CONTENT = "unsupported_content"
    INVALID_ENCODING = "invalid_encoding"
    INVALID_HTML = "invalid_html"
    TEXT_TOO_LARGE = "text_too_large"


class HtmlExtractionError(Exception):
    def __init__(self, code: HtmlExtractionErrorCode):
        self.code = code
        self.retryable = False
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class HtmlExtraction:
    state: str
    final_url: str
    canonical_url: str
    http_status: int
    title: str
    description: str
    language: str
    text: str
    noindex: bool
    source_bytes: int
    text_chars: int
    diagnostics: dict[str, bool]
    outbound_links: tuple[dict[str, str], ...] = ()

    def persistence_defaults(self) -> dict:
        return asdict(self)


_SPACE = re.compile(r"[\t\f\v ]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_LANGUAGE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")
_BOILERPLATE_HINT = re.compile(r"(?:^|[-_ ])(?:cookie|footer|menu|nav|sidebar)(?:$|[-_ ])", re.I)
_MAX_OUTBOUND_LINKS = 1000


def _bounded_text(value: str | None, limit: int) -> str:
    normalized = _SPACE.sub(" ", unicodedata.normalize("NFC", value or "")).strip()
    return normalized[:limit]


def _normalize_article_text(value: str | None) -> str:
    lines = [_SPACE.sub(" ", line).strip() for line in (value or "").splitlines()]
    normalized = "\n".join(line for line in lines if line)
    return _BLANK_LINES.sub("\n\n", unicodedata.normalize("NFC", normalized)).strip()


def _decode_html(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        match = from_bytes(body).best()
        if match is None or match.percent_chaos > 30:
            raise HtmlExtractionError(HtmlExtractionErrorCode.INVALID_ENCODING) from None
        return str(match)


def _parse_dom(document: str):
    parser = html.HTMLParser(recover=True, no_network=True, huge_tree=False)
    try:
        return html.fromstring(document, parser=parser)
    except (etree.ParserError, ValueError) as error:
        raise HtmlExtractionError(HtmlExtractionErrorCode.INVALID_HTML) from error


def _meta_content(root, name: str) -> str:
    values = root.xpath(
        "//meta[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz')=$name]/@content",
        name=name,
    )
    return str(values[0]).strip() if values else ""


def _robots_noindex(root, headers) -> bool:
    directives = [headers.get("x-robots-tag", "")]
    directives.extend(_meta_content(root, name) for name in ("robots", "googlebot", "bingbot"))
    tokens = {
        token.strip().lower() for directive in directives for token in re.split(r"[,;:]", directive)
    }
    return "noindex" in tokens or "none" in tokens


def _normalized_language(*values: str | None) -> str:
    for value in values:
        candidate = (value or "").split(",", 1)[0].strip().lower().replace("_", "-")
        if len(candidate) <= 35 and _LANGUAGE.fullmatch(candidate):
            return candidate
    return ""


def _canonical_url(value: str | None, final_url: str, allowed_host: str) -> tuple[str, bool]:
    candidate = urljoin(final_url, value) if value else final_url
    try:
        normalized, host = normalize_sitemap_url(candidate)
    except (ValidationError, ValueError):
        normalized, _host = normalize_sitemap_url(final_url)
        return normalized, bool(value)
    if host != allowed_host:
        normalized, _host = normalize_sitemap_url(final_url)
        return normalized, True
    return normalized, False


def _validated_final_url(value: str, allowed_host: str) -> str:
    try:
        normalized, host = normalize_sitemap_url(value)
    except (ValidationError, ValueError) as error:
        raise HtmlExtractionError(HtmlExtractionErrorCode.INVALID_HTML) from error
    if host != allowed_host:
        raise HtmlExtractionError(HtmlExtractionErrorCode.INVALID_HTML)
    return normalized


def _content_containers(root):
    containers = root.xpath("//article")
    if not containers:
        containers = root.xpath("//main | //*[@role='main']")
    return containers or [root]


def _is_boilerplate_anchor(anchor) -> bool:
    excluded_ancestors = "ancestor::nav | ancestor::header | ancestor::footer | ancestor::aside"
    if anchor.xpath(excluded_ancestors):
        return True
    ancestry_hints = " ".join(
        str(value) for value in anchor.xpath("ancestor-or-self::*/@class | ancestor-or-self::*/@id")
    )
    return bool(_BOILERPLATE_HINT.search(ancestry_hints))


def _normalized_link(anchor, final_url: str) -> str:
    try:
        normalized, _host = normalize_outbound_url(urljoin(final_url, str(anchor.get("href", ""))))
    except (ValidationError, ValueError):
        return ""
    return "" if normalized == final_url else normalized


def _outbound_links(root, final_url: str) -> tuple[dict[str, str], ...]:
    links: dict[str, str] = {}
    for container in _content_containers(root):
        for anchor in container.xpath(".//a[@href]"):
            if _is_boilerplate_anchor(anchor):
                continue
            normalized = _normalized_link(anchor, final_url)
            if not normalized:
                continue
            anchor_text = _bounded_text(" ".join(anchor.itertext()), 300)
            if normalized not in links or (not links[normalized] and anchor_text):
                links[normalized] = anchor_text
            if len(links) >= _MAX_OUTBOUND_LINKS:
                break
        if len(links) >= _MAX_OUTBOUND_LINKS:
            break
    return tuple({"url": url, "anchor_text": links[url]} for url in sorted(links))


def _extractor() -> Extractor:
    config = use_config()
    config["DEFAULT"]["MAX_TREE_SIZE"] = str(settings.EXTRACTION_MAX_TREE_SIZE)
    config["DEFAULT"]["MAX_FILE_SIZE"] = str(settings.CRAWL_MAX_PAGE_BYTES)
    config["DEFAULT"]["MIN_EXTRACTED_SIZE"] = str(settings.EXTRACTION_MIN_TEXT_CHARS)
    return Extractor(
        config=config,
        output_format="python",
        precision=True,
        comments=False,
        formatting=False,
        links=False,
        images=False,
        tables=True,
        # Trafilatura's deduplication cache spans calls, which can make an
        # identical document extract differently after another page is seen.
        dedup=False,
        with_metadata=True,
    )


def extract_article(response: SafeFetchResult, *, allowed_host: str) -> HtmlExtraction:
    if response.content_type not in {"text/html", "application/xhtml+xml"}:
        raise HtmlExtractionError(HtmlExtractionErrorCode.UNSUPPORTED_CONTENT)
    final_url = _validated_final_url(response.final_url, allowed_host)
    document = _decode_html(response.body).replace("\x00", "")
    if not document.strip():
        return HtmlExtraction(
            state=ExtractionStates.EMPTY,
            final_url=final_url,
            canonical_url=final_url,
            http_status=response.status,
            title="",
            description="",
            language=_normalized_language(response.headers.get("content-language", "")),
            text="",
            noindex=False,
            source_bytes=len(response.body),
            text_chars=0,
            diagnostics={"canonical_rejected": False},
            outbound_links=(),
        )
    root = _parse_dom(document)
    noindex = _robots_noindex(root, response.headers)
    try:
        extracted = trafilatura.bare_extraction(document, options=_extractor())
    except (ValueError, etree.LxmlError) as error:
        raise HtmlExtractionError(HtmlExtractionErrorCode.INVALID_HTML) from error

    values = root.xpath(
        "//link[contains(concat(' ', normalize-space(translate(@rel, "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')), ' '), "
        "' canonical ')]/@href"
    )
    canonical_hint = str(values[0]).strip() if values else None
    if not canonical_hint and extracted:
        canonical_hint = getattr(extracted, "url", None)
    canonical_url, canonical_rejected = _canonical_url(
        canonical_hint,
        final_url,
        allowed_host,
    )
    extracted_title = getattr(extracted, "title", None) if extracted else None
    title = _bounded_text(extracted_title or root.findtext(".//title"), 300)
    extracted_description = getattr(extracted, "description", None) if extracted else None
    description = _bounded_text(
        extracted_description or _meta_content(root, "description"),
        1000,
    )
    language = _normalized_language(
        getattr(extracted, "language", None) if extracted else None,
        root.get("lang"),
        _meta_content(root, "content-language"),
        response.headers.get("content-language", ""),
    )
    text = _normalize_article_text(getattr(extracted, "text", None) if extracted else "")
    outbound_links = _outbound_links(root, final_url)
    if len(text) > settings.EXTRACTION_MAX_TEXT_CHARS:
        raise HtmlExtractionError(HtmlExtractionErrorCode.TEXT_TOO_LARGE)
    if noindex:
        state = ExtractionStates.NOINDEX
        text = ""
    elif len(text) < settings.EXTRACTION_MIN_TEXT_CHARS:
        state = ExtractionStates.EMPTY
        text = ""
    else:
        state = ExtractionStates.READY

    return HtmlExtraction(
        state=state,
        final_url=final_url,
        canonical_url=canonical_url,
        http_status=response.status,
        title=title,
        description=description,
        language=language,
        text=text,
        noindex=noindex,
        source_bytes=len(response.body),
        text_chars=len(text),
        diagnostics={"canonical_rejected": canonical_rejected},
        outbound_links=outbound_links,
    )


class PageExtractionService:
    @staticmethod
    @transaction.atomic
    def persist(*, work: PageCrawlWork, extraction: HtmlExtraction) -> PageExtractionResult:
        work = PageCrawlWork.objects.select_for_update().get(pk=work.pk)
        result, _created = PageExtractionResult.objects.get_or_create(
            work=work,
            defaults=extraction.persistence_defaults(),
        )
        return result
