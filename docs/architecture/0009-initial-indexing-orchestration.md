# Initial indexing orchestration

CG-018 closes the initial sitemap-to-search loop inside the existing durable
`PageCrawlWork` boundary. A page job safely fetches and extracts the candidate,
persists its canonical article and crawl evidence in PostgreSQL, produces the
current whole-article embedding, and synchronously upserts the stable Qdrant
point. The page and parent sync become successful only after the Qdrant write
has completed and PostgreSQL has marked the article active.

The crawl task suppresses the ingestion service's standalone embedding enqueue
because it owns those stages itself. Other callers retain the original
post-commit embedding queue behavior. Embedding reuse and Qdrant's stable article
UUID point make repeated identical syncs cheap and idempotent.

Known provider and Qdrant transport failures use the existing bounded page retry
state. Non-retryable extraction, embedding, or Qdrant contract failures remain
on the page work and reconcile the parent sync to failed or partial. A retry
reuses durable extraction and article state rather than refetching successful
work. Project eligibility is checked before embedding and again while holding
the article, profile, and project row locks across the bounded vector publication.
Subscription and project transitions use the same lock order, so suspension or
lost subscription is linearized against publication and cancels outstanding work.
Project ownership is immutable through the service; the publication path still
verifies that the prefetched profile lock matches the locked project and retries
instead of publishing if a direct concurrent reassignment occurred.

When `CITEGUILD_INDEXING_ENABLED` is false, the pipeline intentionally stops
after PostgreSQL ingestion and retains the pre-existing non-searchable behavior.
Production must enable the gate only after both the embedding provider and the
private authenticated Qdrant collection pass their startup checks.
