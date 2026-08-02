# Article lifecycle persistence

CG-015 makes PostgreSQL the durable truth for accepted extraction results and
crawl history. `Article` is tenant-owned through `Project` and has a stable UUID
and equal Qdrant point UUID. Its identity constraint is the project plus exact,
normalized canonical URL. `ArticleSourceURL` maps every sitemap URL that resolved
to that identity, so canonical duplicates converge on one article while sitemap
reconciliation can retain all aliases and determine when none remain active.

The ingestion transaction locks the project before article rows. It consumes one
immutable `PageExtractionResult`, hashes normalized extracted text with SHA-256,
upserts the canonical article and source alias, appends one idempotent crawl
attempt per worker attempt, and reconciles the complete bounded outbound-link
set. Replaying a completed extraction is a no-op for identity and history.
Unchanged content advances seen/fetched timestamps without moving
`last_changed_at`; changed content moves the article back to `discovered` for a
replacement embedding. Empty or noindex results retain prior good text but make
the article inactive. Transport/extraction failures append failure evidence and
never update the last good Article row.

Successful sitemap finalization marks absent source aliases inactive. An article
becomes inactive only when it has no active source alias, and its text, hash,
attempts, links, UUID, and first-seen history remain available. A later successful
fetch reactivates the same UUID through `discovered`. The active/searchable flag
remains false until CG-016 records a matching ready whole-article embedding.

Outbound observations are derived only from bounded content-area anchors, never
navigation, footer, cookie, mailto, or executable content. Each source article
and normalized destination pair is stable; disappearance marks the observation
inactive and reappearance reuses it. Target resolution is an internal corpus
operation. Caller-facing repositories always derive article scope from the
authenticated profile through `Project.owner`; caller-supplied tenant IDs are
not accepted.
