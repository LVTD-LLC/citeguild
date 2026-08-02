# Paid-to-citation analytics contract

This contract is the operational source of truth for the CiteGuild MVP funnel.
Events are captured from backend state transitions, never inferred from a success
page. Every property is allowlisted in `apps/core/funnel_analytics.py` before it
can reach PostHog.

## Identity and deduplication

- `distinct_id` and `profile_id` are the internal numeric profile ID. Email and
  Stripe customer/subscription IDs are never analytics properties.
- `site_id` is the opaque project UUID. Sitemap, article, source, and destination
  URLs are excluded.
- Critical transitions carry a SHA-256 `$insert_id` derived from the profile,
  event name, and durable source key. The source key itself is not sent or logged.
  Retried Stripe events, sitemap submissions, sync finalizers, credential writes,
  and citation transitions therefore collapse at PostHog ingestion.
- Search and embedding attempts intentionally have no `$insert_id`: each actual
  provider attempt is a unit of activity/cost. Existing job and embedding
  idempotency prevents successful work from being repeated.

## Canonical events

| Event | Server truth | Properties |
| --- | --- | --- |
| `citeguild_subscription_activated` | First paid Stripe subscription state | `subscription_status`, `previous_status`, `cancel_at_period_end` |
| `citeguild_subscription_retained` | Later unique Stripe event while paid | Same as activation |
| `citeguild_subscription_ended` | Paid-to-terminal Stripe transition | Same as activation |
| `citeguild_site_submitted` | Validated sitemap and durable initial sync committed | `site_id`, `sitemap_kind` |
| `citeguild_initial_index_completed` | Initial sync finalized successfully | `site_id`, page outcome counts, `active_articles`, `duration_ms`, `status` |
| `citeguild_initial_index_failed` | Initial sync reached failed/partial terminal state | Completion properties plus `error_code`, `retryable` |
| `citeguild_agent_credential_created` | API credential hash committed | `credential_kind`, `rotation` |
| `citeguild_search_completed` | Shared search service returned or rejected a request | `transport`, `status`, query length only, result/limit/filter counts, `input_tokens`, `duration_ms`, optional safe error fields |
| `citeguild_embedding_completed` | One embedding provider attempt completed | `site_id`, `status`, `model`, input size/tokens, `duration_ms`, optional safe error fields |
| `citeguild_citation_detected` | Detected member edge first appears or becomes active | `direction`, own `site_id`, `matched_page`, `active` |
| `citeguild_citation_removed` | Active detected member edge becomes inactive | Same as detection |

Result selection is not emitted yet because CiteGuild has no redirect/click
boundary that can establish server truth. Add it only with such a boundary; do
not infer selection from returned search results.

## MVP questions and saved-query recipes

Use `environment = 'prod'` in every PostHog insight.

- Paid conversion: unique `distinct_id` on `citeguild_subscription_activated`.
- Activation: funnel activation → site submitted → initial index completed →
  agent credential created → search completed (`status = succeeded`) → citation
  detected (`direction = received`).
- Repeated search: weekly unique users and event count for successful searches,
  broken down by `transport`.
- Supply balance: sum `active_articles` on the latest initial-index event per
  `site_id`, compared with searches and received citations.
- Reliability: failed / total initial-index, search, and embedding events,
  grouped by safe `error_code`; p50/p95 `duration_ms` by event and transport.
- Crawl unit proxy: sum `total_pages`, `succeeded_pages`, and `failed_pages` per
  activated account.
- Embedding cost: sum `input_tokens` by `model`, multiply by the current provider
  input-token rate, then divide by activated accounts or successfully indexed
  pages. Pricing stays outside event data because provider rates change.
- Search cost: sum search `input_tokens` by transport and divide by searches or
  accounts. Add infrastructure cost separately from CapRover billing.

PostHog ingestion and privacy-filtered operational logs are separate. Logs may
carry safe error codes and durations for diagnosis, but analytics must never add
raw query text, article bodies/excerpts, URLs, email, credentials, provider
payloads, or Stripe identifiers.
