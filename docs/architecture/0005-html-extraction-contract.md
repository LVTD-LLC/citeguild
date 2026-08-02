# HTML extraction contract

CG-014 attaches deterministic content extraction to the existing bounded page
fetch job. The safe fetch client remains the only network boundary and admits
only HTML/XHTML from the submitted site's exact normalized host. Workers never
render pages, execute scripts, resolve external entities, write response data to
disk, or place response bodies in queue metadata or logs.

Trafilatura provides the main-content baseline with precision mode and bounded
file/tree settings. CiteGuild owns the stable product policy around it: input is
decoded as UTF-8 when possible with a bounded charset fallback, text and metadata
are NFC/whitespace normalized, and output length is capped. The original body is
discarded after extraction. An immutable `PageExtractionResult` retains only the
final/canonical URL, HTTP status, bounded title/description/language, extraction
state, text, size counters, noindex decision, and non-sensitive diagnostics.

Canonical URLs are resolved relative to the final response URL, normalized by
the shared URL contract, stripped of fragments, and accepted only on the exact
project host. Invalid or off-host canonical hints fall back to the final URL.
`robots`, named crawler directives, and `X-Robots-Tag` can mark content noindex;
the metadata remains diagnosable but extracted text is discarded. Content below
the minimum is stored as `empty`, and unsupported/invalid/oversized inputs end
with stable non-retryable error codes so they cannot reach embedding.

Extraction persistence precedes the page-work success transition. If a worker
dies between those writes, recovery observes the existing immutable result and
finishes the page without fetching or duplicating it. CG-015 will consume these
results to maintain canonical Article identities, content hashes, crawl history,
and outbound-link observations without changing this extraction boundary.
