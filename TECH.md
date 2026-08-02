# CiteGuild Technical Contract

This file records the target MVP architecture and the constraints that should
survive individual tasks. `PRODUCT.md` owns product decisions; `STRUCTURE.md`
owns file placement; `docs/quality.md` owns the full command matrix.

The detailed model, lifecycle, idempotency, job, and shared search decision is
[ADR 0001: Define the MVP domain and service
boundaries](docs/architecture/0001-mvp-domain-and-service-boundaries.md).

## Current Baseline vs Target

The repository currently contains the generated Django SaaS foundation: auth,
Stripe primitives, Django Ninja API, FastMCP with `get_user_info`, Django Q2,
PostgreSQL/Redis integration, PostHog/Sentry, server-rendered frontend, and
CapRover app/worker deployment. Do not mistake generated example behavior for
completed CiteGuild domain features.

The target MVP adds subscription-gated sites, secure sitemap ingestion, article
extraction, whole-article embeddings in Qdrant, shared semantic search, daily
reconciliation, CLI access, and detected citation tracking. Implement these in
dependency order from the live Rowset taskboard.

## Stack

- Python 3.14.5, Django 6.0.5, uv, PostgreSQL 18.
- Redis 8.6.3 and Django Q2 for background work and scheduling.
- Django Ninja for HTTP API; FastMCP mounted at `/mcp/` for agent access.
- Django templates, Tailwind CSS 4, HTMX, and Alpine.js; no SPA framework.
- Stripe for the single subscription, PostHog for consented product analytics,
  and Sentry for content-safe operational telemetry.
- Self-hosted Qdrant for semantic retrieval. PostgreSQL is authoritative.
- One shared production image with `APP_PROCESS_TYPE=server|worker`, deployed to
  CapRover alongside PostgreSQL, Redis, and Qdrant.

Pinned versions and dependencies live in `pyproject.toml`, `uv.lock`,
`package.json`, and `package-lock.json`; do not duplicate them here.

## Domain and Data Contracts

- **Account/profile:** user identity and subscription state. Stripe webhooks are
  the server truth and must remain idempotent.
- **Site/project:** tenant owner, name, submitted sitemap URL, derived base
  domain, lifecycle/indexing state, and last successful sync.
- **Article:** site, original/canonical URL, metadata, extracted content or
  durable reference, normalized content hash, HTTP/lifecycle state, timestamps,
  and stable Qdrant point identifier.
- **Detected citation:** source article, target article/site, normalized
  destination, anchor text when safe, first/last seen, and active state.
- **Sync state:** attempts, bounded failure details, checkpoints/counts, and the
  information required for safe retries.

Every tenant-owned management or ingestion query must derive ownership from
authenticated context. IDs from a request, MCP argument, job payload, or Qdrant
result are never sufficient authorization. Semantic search is deliberately
cross-tenant over eligible active member articles, but must expose only the
public-safe retrieval contract and must not grant management/content access.

## Ingestion and Reconciliation

1. Validate the submitted HTTP(S) sitemap URL and resolve it safely.
2. Fetch with time, byte, redirect, content-type, concurrency, and rate limits;
   repeat network-policy checks after every DNS resolution and redirect.
3. Parse bounded sitemap XML and sitemap indexes; canonicalize and deduplicate
   page URLs before enqueueing.
4. Fetch each page under the same network policy, extract main article content
   and outbound links, and compute a normalized content hash.
5. Persist canonical state in PostgreSQL. Regenerate an embedding only when the
   normalized content changes or index repair requires it.
6. Upsert one whole-article vector with a stable point ID and the minimum
   metadata required for filtering and result display.
7. Reconcile approximately daily. New pages are indexed; removed or confirmed
   unavailable pages become inactive in PostgreSQL and Qdrant search without
   erasing history; returning pages can reactivate.

Retries must be idempotent. Partial failure must not publish a vector detached
from authorized, active PostgreSQL state.

## Retrieval Contract

MCP, CLI, and API must call one shared search service. It embeds the query,
searches only active authorized corpus entries in Qdrant, ranks primarily by
similarity, supports own-domain exclusion, rehydrates authoritative metadata
from PostgreSQL when needed, and returns bounded fields such as title,
canonical URL, site/domain, short excerpt or summary, relevance score, and
last-seen time.

Never log or send raw queries, drafts, article bodies, embeddings, or result
content to analytics/observability. Never auto-edit or publish customer content.

## Security Launch Blockers

- SSRF defense must reject loopback, private, link-local, multicast,
  unspecified/reserved networks, cloud metadata targets, credential-bearing
  URLs, and non-HTTP(S) schemes across initial requests and redirects. Account
  for DNS rebinding and mixed public/private answers.
- Bound XML depth/entries/bytes, decompression, HTML size, redirects, request
  time, worker concurrency, retries, and per-tenant/global crawl rates.
- Treat XML, HTML, metadata, canonical tags, links, filenames, model text, and
  error bodies as untrusted input. Do not execute page scripts.
- Enforce subscription and tenant isolation for management, ingestion,
  background jobs, and private dashboard/API state. Shared MCP/CLI/API search
  may cross tenants only over eligible active public articles; keep private
  fields out of Qdrant payloads and retrieval results.
- Store secrets only in environment-backed configuration. Keep credentials,
  raw user content, connection strings, and private dataset data out of logs,
  analytics, errors, fixtures, screenshots, and committed files.
- Preserve idempotency for Stripe, sync jobs, vector upserts, and citation
  observations. Use transactions/outbox-style coordination where cross-system
  state can diverge.

## Deployment Contract

MVP production is not complete until these CapRover components are healthy:

- `citeguild` app process
- `citeguild-workers` worker process
- PostgreSQL
- Redis
- Qdrant with durable storage and non-public access

The current `.github/workflows/deploy.yml` builds one image and deploys app and
workers. Production Qdrant is provisioned as the private
`citeguild-qdrant` CapRover service on port 6333, pinned to Qdrant 1.18.3 with
the persistent `citeguild-qdrant-data` volume and API-key authentication.
Server startup and `/api/healthcheck` validate the authenticated article
collection contract. `rebuild_qdrant_articles` reconstructs active points from
PostgreSQL and removes stale points; infrastructure backup and restore policy
remains a separate deployment concern.

The typed environment matrix, fail-fast production rules, and secret-safe
web/worker fingerprint contract live in
[`docs/configuration.md`](docs/configuration.md).

## Commands

First-time host setup with Compose-backed services:

```bash
cp .env.agent.example .env
make agent-services
make terminal-setup
make terminal-migrate
make terminal-manage check
```

Focused documentation/steering verification:

```bash
git diff --check
make python-quality
```

Targeted and full checks:

```bash
make terminal-test apps/core/tests/test_api_keys.py -q
make frontend-check
make migrations-check
make django-check
make ci-local
```

CI runs `make python-quality`, `make type-check`, `make frontend-check`,
`make migrations-check`, `make django-check`, and high-risk coverage. See
`docs/quality.md` for prerequisites and touched-area choices.

## Ship Contract

Pull current `main`, branch, implement, test, update `CHANGELOG.md`, push, and
open a PR. Never commit directly to `main`. Required CI and current-head
ReviewGate/configured review feedback must pass and material comments must be
resolved unless the owner explicitly waives a gate for that PR. Record the PR,
review outcome, merge SHA, and validation evidence on the live Rowset task.
