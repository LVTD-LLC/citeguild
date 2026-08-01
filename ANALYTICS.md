# CiteGuild Product Analytics Contract

CiteGuild uses PostHog for consented product analytics. This file is the
canonical measurement contract for humans and coding agents. Instrument only
events supported by implemented behavior; when a domain feature lands, add its
canonical event in the same PR.

## Measurement Goal

The decisive question is whether paid members supply legitimate articles and
writing agents repeatedly retrieve useful sources, producing a growing graph
of detected citations at sustainable crawl and embedding cost.

Primary funnel:

1. Account signs up.
2. Subscription becomes active on the single $10 monthly plan.
3. First sitemap-backed site is added.
4. First sitemap sync completes and at least one article becomes searchable.
5. Copy Prompt is copied or an MCP/CLI/API integration first searches.
6. Search becomes recurring for the account/agent.
7. A member-to-member citation is detected and retained.

Track conversion and elapsed time between these milestones. Do not substitute
pageviews or raw search volume for successful indexing, repeat retrieval, and
detected network activity.

## Canonical Metrics

- Active paid accounts and subscription retention.
- Sites added per active paid account.
- Sitemap sync success rate and time to first searchable article.
- Active/inactive article counts and content-change/index refresh rate.
- Search queries and querying days per account, agent, and interface.
- Searches with results, result selection/use when explicitly reported, and
  repeat search retention.
- Active detected citations, distinct giving/receiving sites, new citations,
  and citation retention.
- Crawl, extraction, embedding, Qdrant, and storage cost per account/site/page.

## Identity and Source of Truth

- Authenticated browser and server events use the profile ID as `distinct_id`;
  never use email. Add bounded `account_id`, `site_id`, `article_id`, or
  `sync_id` only when needed and authorized.
- Stripe webhook-confirmed state is subscription truth. Backend persistence is
  site/article/sync/citation truth. A successful shared search service call is
  retrieval truth; transport clicks or request starts are intent signals only.
- MCP, CLI, API, dashboard, and background-worker events use the same event
  names. Distinguish surfaces with `interface` (`dashboard`, `mcp`, `cli`,
  `api`, `worker`) rather than separate names.
- Server events include `event_version`, `environment`, `profile_id`, and
  `current_state` when those fields are applicable.
- Use deterministic idempotency keys for critical server conversions and job
  milestones so retries do not inflate metrics.

## Event Contract

Event names are lowercase snake case, start with `citeguild_`, and describe a
completed action or durable state transition. Keep properties bounded and
schema-controlled.

Generated lifecycle events already available:

- `citeguild_signup_completed`
- `citeguild_user_logged_in`
- `citeguild_checkout_started`
- `citeguild_account_deleted`
- `citeguild_marketing_cta_clicked`

Canonical events to add with their corresponding MVP features:

- `citeguild_subscription_activated`: `plan_key=monthly_10_usd`,
  `subscription_state`, `is_first_activation`.
- `citeguild_site_created`: `site_id`, `interface`.
- `citeguild_sitemap_sync_completed`: `site_id`, `sync_id`, `outcome`, bounded
  `failure_type`, and new/changed/reactivated/inactivated/failed counts.
- `citeguild_article_indexed`: `site_id`, `article_id`, `index_reason`
  (`new`, `content_changed`, `repair`, `reactivated`). Prefer a batch event with
  counts when per-article volume would be noisy or costly.
- `citeguild_copy_prompt_copied`: `site_id`, `integration` (`mcp`, `cli`,
  `api`, `generic`).
- `citeguild_search_completed`: `interface`, `result_count`, bounded
  `latency_bucket`, `excluded_own_domain`, and `outcome`.
- `citeguild_search_result_selected`: `interface`, `article_id`,
  `result_position`, and `selection_signal`; emit only when the caller reports a
  real selection/use signal.
- `citeguild_citation_detected`: `source_site_id`, `target_site_id`, bounded
  cross-account flag, and whether this is first observed/reactivated.
- `citeguild_subscription_ended`: bounded `reason` and prior tenure bucket.

Use `track_event()` only after the action succeeds or a durable transition is
committed. For events with an `outcome`, allow only `success` or `failure` and a
small enumerated `failure_type`; never attach exception text or response bodies.

## Privacy Contract

- Browser capture is opted out by default, DOM autocapture is disabled, and
  pageviews are emitted manually only for allowlisted routes in
  `apps/core/context_processors.py` after a visitor chooses **Allow analytics**.
- Never send passwords, form values, API keys, payment/customer identifiers,
  full URLs, query strings, sitemap URLs/bodies, article content, search query
  or draft text, embeddings, result excerpts, anchor text, raw domains from
  private sites, IP addresses, exception content, or arbitrary model/tool data.
- Browser events use normalized Django route templates. Referrers are reduced
  to origin/domain. Campaign fields are limited to `utm_source`, `utm_medium`,
  `utm_campaign`, `utm_content`, `utm_term`, and `campaign_id`; advertising
  click IDs are removed.
- Declining analytics removes stored attribution. Logout resets the PostHog
  browser identity.
- AI observability remains separately opt-in and content-free. MCP analytics
  record protocol/tool usage but replace argument values with names and coarse
  types, remove tool responses, and drop exception payloads.

## Attribution

The browser stores sanitized first-touch and latest-touch attribution for up to
180 days after consent. Person properties use `first_touch_*` and
`current_touch_*`. Untagged internal navigation does not erase the latest
campaign.

## Validation and Schema Evolution

- Send browser and server events to the same PostHog project. Exclude
  non-production and staff traffic from decision dashboards.
- Before launch, validate one consented UTM-to-signup-to-Stripe activation flow,
  one sitemap-to-search flow, and one detected-citation flow without exposing
  prohibited data.
- Maintain dashboards for funnel conversion, activation time, search retention,
  citation growth/retention, ingestion reliability, and unit economics.
- Event/property changes require an `event_version` bump when semantics change,
  a migration/overlap plan for dashboards, and an update to this file.
- Run a daily ingestion-health check for recent critical events, failed sends,
  unexpected schema drift, and zero-volume anomalies.

Set `POSTHOG_BROWSER_HOST` to a first-party reverse proxy in production when
possible. Keep `POSTHOG_HOST` on the regional ingestion endpoint for server
capture. MCP usage is enabled when `POSTHOG_API_KEY` is set, and the ASGI
lifespan drains pending MCP events during graceful shutdown.
