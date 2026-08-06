# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
with release sections grouped by ISO 8601 date headings (`## YYYY-MM-DD`).

## 2026-08-06

### Changed

- Refocused the SEO competitor roadmap on backlink-exchange workflows, moved
  direct exchange products into validation, and removed Tavily and Exa from
  planned comparison pages because CiteGuild is not a general programmatic
  web-search product.

## 2026-08-05

### Added

- Added a source-verified guide to seven current HARO alternatives, including a
  decision framework for journalist requests versus persistent agent retrieval,
  enriched blog schema, and contextual homepage and pricing links.
- Added an owner-scoped sitemap details page with indexing and sync status,
  paginated cross-site links given and received, editable site metadata, safe
  confirmed deletion, and dashboard navigation.
- Added reusable product, organization, FAQ, breadcrumb, and article JSON-LD
  builders, homepage product schema, and stable feature anchors for future SEO
  page families.
- Added the measured CiteGuild SEO sprint roadmap, persistent brand and internal-link
  context, connected-tool evidence, and private Rowset research locators for phased
  organic-search execution.
- Added privacy-safe Sentry browser error capture, page-load and navigation
  tracing, Web Vitals, and same-origin trace propagation to the existing Django
  errors, logs, traces, and profiling integration.

### Fixed

- Dashboard site pagination now counts the owner-scoped project list directly
  and hydrates only the visible page with bounded aggregate queries, avoiding
  the repeated multi-join count that dominated production page loads. Per-site
  link totals also exclude preserved legacy same-site edges.
- OpenRouter agent and embedding requests now share explicit CiteGuild app
  attribution instead of leaving deferred embedding requests unattributed.
- Sentry releases now fall back to the immutable image commit when no explicit
  Sentry or service release is configured.
- Production deploys now pin the CapRover CLI to the last known-good release,
  avoiding the conflicting deploy flags introduced in CapRover CLI 2.4.0.

### Changed

- Marked the generic technology-stack page `noindex` and removed it from the
  public sitemap while retaining it as a transparency page.
- Adopted a plainspoken source-discovery and backlink-outcome direction across
  shared public navigation, landing copy, and footer; retained the Guilded mark
  and paid-only $10 monthly membership.
- Carried the same sparse direction into the authenticated dashboard, settings,
  and admin surfaces; removed Docs from app navigation and hid shortcut keycaps.
- Reworked the unsubscribed dashboard into a compact onboarding empty state
  without the previous double-divider gap.
- Refocused the paid dashboard on a small site collection: one modal Add Site
  action, hostname-derived names with later renaming, and indexing plus
  detected-link data grouped by site instead of global KPI/activity sections.

## Types of changes

**Added** for new features.
**Changed** for changes in existing functionality.
**Deprecated** for soon-to-be removed features.
**Removed** for now removed features.
**Fixed** for any bug fixes.
**Security** in case of vulnerabilities.

## 2026-08-04

### Added

- Added an installable, dependency-free Go CLI for agent and shell search with
  secret-safe configuration and authentication checks, readable and stable v1
  JSON output, bounded HTTP behavior, deterministic exit codes, native CI, and
  checksum-backed Linux amd64 and macOS arm64 release automation.

## 2026-08-03

### Fixed

- Detected links given/received and citation aggregates now count only
  cross-site links inside the CiteGuild member network, excluding external and
  same-site links while retaining the underlying crawl observations.

## 2026-08-02

### Fixed

- Stripe webhooks now ignore unrelated products in the shared LVTD account and
  mutate CiteGuild billing state only for the configured monthly Price.
- Stripe Checkout now validates live Stripe SDK Price objects without treating
  them as plain dictionaries, while preserving the fail-closed $10 plan check.
- Crawl recovery now clears every stale queued broker reservation, including
  task IDs left behind after a worker replacement, so phantom in-flight work
  cannot consume a site's concurrency slots indefinitely.
- Sitemap page dispatch now reserves only the available per-site worker slots
  and refills each slot after a page finishes, so large crawls cannot stall
  after their first concurrent batch.
- Hosted MCP now uses stateless Streamable HTTP so authenticated multi-call
  clients remain reliable across the three production Gunicorn workers.

### Changed

- The browser favicon, public and authenticated navigation, and publisher
  metadata now use the CiteGuild guild mark.
- Replaced generic policy copy with CiteGuild-specific crawler, semantic search,
  public indexing, data processing, billing, abuse, and no-guaranteed-backlink
  terms that match the deployed MVP.

### Added

- Added the evidence-linked launch checklist, named operator ownership,
  component and abuse incident paths, metric cadence, production failure
  exercise, and explicit launch/no-launch risks.
- Added private encrypted daily PostgreSQL backups with bucket-scoped storage,
  daily/weekly/monthly retention, integrity checks, failure alerts, and an
  isolated PostgreSQL restore plus Qdrant rebuild recovery runbook.
- Production deploys now validate required configuration up front, pin the
  CapRover action, and gate worker rollout on the exact expected release plus
  the public aggregate health contract for PostgreSQL, Redis, and Qdrant.
- Codified the five-service CapRover topology, private networking, persistent
  volumes, dependency health, immutable image identity, scheduler ownership,
  deployment order, and rollback boundary with tested Compose/workflow parity,
  including portable Qdrant readiness and explicit HTTP 200 web health probes.
- Added a dedicated real-service MVP acceptance lane covering paid site
  submission, article indexing, semantic search, detected links, Redis, pinned
  dependency audits, documented risk coverage, and explicit smoke budgets.
- Added a documented, allowlisted paid-to-citation PostHog contract with
  server-truth conversions, deterministic retry deduplication, safe reliability
  and unit-cost inputs, and privacy tests that exclude content, URLs, and PII.
- The dashboard now presents bounded owner-scoped site pagination, current sync
  progress and safe errors, account indexing totals, and paginated detected
  links given/received with accessible empty and historical states.
- Normalized outbound observations now resolve into durable detected network
  links with historical URL matching, lifecycle reconciliation, owner-scoped
  detail queries, and page/site citation aggregates without attribution claims.
- Outbound article links now strip an explicit allowlist of campaign tracking
  identifiers while preserving query semantics and atomic observation history.
- Confirmed article lifecycle reconciliation now handles repeated sitemap
  omissions, terminal 404/410 responses, redirects, reappearance, and Qdrant
  deactivation while preserving article and crawl history.
- Active paid sites now receive jittered daily sitemap reconciliation through a
  named, idempotent Django Q2 schedule with PostgreSQL claims, selective
  new/changed/stale page work, visible failures, and an owner-scoped manual retry.
- The dashboard now reveals a credential-safe Copy Prompt after the first site
  submission, with provider-neutral MCP/API onboarding, current public URLs,
  explicit source-evaluation guardrails, and linked key rotation guidance.
- Added the authenticated `search_member_articles` Streamable HTTP MCP tool on
  the shared v1 semantic-search contract, with bounded inputs, safe errors,
  bearer/OAuth integration coverage, and Codex/Claude Code setup guidance.
- Authenticated `/api/v1` endpoints now expose shared semantic search, account
  state, bounded owner-scoped project listing/detail/creation, stable errors and
  request IDs, and atomic per-key rate limits through generated OpenAPI docs.
- A versioned shared semantic-search service now embeds bounded queries, searches
  the active paid-member corpus, applies language and exact-domain exclusions,
  reauthorizes every Qdrant hit through PostgreSQL, and returns deterministic
  public-safe results with content-free latency and failure telemetry.
- Initial sitemap syncs now orchestrate fetch, extraction, PostgreSQL article
  persistence, whole-article embedding, and Qdrant upsert as one retryable page
  workflow. Progress reaches success only after durable search publication;
  repeated runs reuse the article, embedding, and vector, while partial failures
  remain visible and resumable.
- Qdrant now has an idempotent cosine collection contract, authenticated
  startup and health checks, stable article upsert/deactivation, tenant-scoped
  bounded search, and a PostgreSQL-authoritative rebuild command. Local Compose
  persists an API-key-protected Qdrant service.
- Active extracted articles can now produce one durable, content-addressed
  whole-article embedding with bounded deterministic input, explicit model and
  dimension metadata, safe retry classification, and privacy-safe usage and
  latency metrics.
- PostgreSQL now retains tenant-owned article identities, normalized content
  hashes, source URL aliases, append-only crawl attempts, lifecycle timestamps,
  and reconciled outbound-link observations without storing raw HTML.
- Page workers now deterministically extract bounded article text and canonical
  metadata with Trafilatura, persist immutable extraction results, honor
  noindex directives, and reject unsupported, empty, oversized, or off-host
  content without retaining raw HTML.

## 2026-08-01

### Changed

- Billing now offers one fixed $10 USD monthly subscription with Stripe-hosted
  Checkout and portal management, synchronous server-side access truth,
  durable webhook receipts, stale-event protection, and a reusable paywall.
- Replaced generic generated agent context with aligned CiteGuild product,
  architecture, structure, design, and analytics contracts covering the
  $10/month sitemap-to-search MVP, explicit non-goals, hostile-content and
  tenant-isolation boundaries, CapRover topology, real validation commands,
  and the Rowset/PR ship workflow.

### Added

- Durable Django Q2 sitemap/page jobs now provide idempotent enqueueing,
  bounded retries, per-site concurrency, progress, cancellation, and recovery.
- XML sitemap indexes now produce deterministic, host-scoped candidate
  inventories with bounded recursion, gzip handling, and atomic promotion.
- Sitemap-only dashboard and API submission now validate bounded XML through
  the shared SSRF-safe transport and create one durable, idempotent initial-sync
  request with retry-safe error responses.
- A shared SSRF-safe crawler fetch client now pins validated public DNS answers,
  revalidates redirects, and bounds response types, encodings, time, size,
  concurrency, and per-host request pace.
- Add the subscription-aware dashboard onboarding shell, owner-scoped site
  list, and accessible Add Site flow.
- Account-owned `Project` records now model submitted sites with global
  normalized-host uniqueness, unlimited paid-account membership, owner-scoped
  services, suspension/reactivation audit history, and sync eligibility gates.
- A shared typed runtime configuration contract now validates production
  database, Redis, Qdrant, Stripe feature-gate, embedding, crawler, scheduler,
  and process settings, with a secret-safe fingerprint reported by web and
  worker startup.
- ADR 0001 defines the CiteGuild MVP systems of record, domain entities,
  lifecycle states, stable identifiers, unique constraints, idempotent worker
  boundaries, shared API/MCP/CLI search contract, failure recovery, and
  CapRover deployment topology.
- CiteGuild can now construct a shared authenticated Qdrant client from
  environment configuration, without creating collections or writing vectors.
- Production now has a private, API-key-authenticated Qdrant 1.18.3 service
  with persistent storage and matching web/worker connection configuration.

### Fixed

- Stripe SDK Event objects are normalized to plain dictionaries after signature
  verification so production webhooks use the same safe contract as tests.
- The agent development preflight now runs a low-noise typed baseline inside
  the locked project environment, and GitHub CI executes the same check.
- Local MinIO startup now uses the current client command and credentials and
  bucket settings that match `.env.agent.example`.
- Host and Compose development servers now run the ASGI application so the
  documented local path exposes UI, API, OAuth discovery, and MCP together.

## 2026-07-31
### Changed
- PostHog analytics now use opt-in consent, manual privacy-safe pageviews,
  bounded first/latest-touch attribution, optional first-party browser proxying,
  and profile-ID-based lifecycle events without email or raw URL properties.
- AI-enabled projects can separately opt into content-free Pydantic AI model
  and embedding performance spans.
- Logging now uses canonical dotted event names, binary outcomes,
  OpenTelemetry-style request/job/resource fields, and privacy-aware scalar
  context across console, JSON, and Sentry output.
- PostHog now receives a strictly allowlisted, fail-open clone of application
  logs through batched OTLP export when `POSTHOG_LOGS_ENABLED=True`.
- PostHog now records privacy-filtered MCP protocol and tool usage without
  argument values, tool responses, or exception payloads.
- Changelog entries now use date-based headings instead of version-based
  release placeholders.
- CI now runs parallel Python quality, frontend, and pytest jobs. Pytest uses
  `citeguild.test_settings` for local cache/media/email
  and Django Q2 isolation, strict markers, and slow-test duration reporting.
- Frontend assets now use Tailwind CLI plus Django staticfiles instead of a JavaScript bundler.
- AI-assisted development guidance now uses tool-neutral `AGENTS.md` files
  instead of agent-vendor-specific instruction files.
- Deployments now use one shared Docker image, one CapRover deploy workflow, and explicit `APP_PROCESS_TYPE` guards to choose server vs. worker at runtime.
- Align template runtimes on Python 3.14.5, Django 6.0.5, Node.js 24.15.0 LTS, PostgreSQL 18, and Redis 8.6.3.
- Sentry setup now includes release metadata, configurable tracing/profiling/log settings, logging breadcrumbs/events, and the `before_send` hook by default.
- Logging now uses plain Python `logging` call sites with explicit `extra={...}` structured fields, console output in development, structured JSON in production, and request correlation fields.
- Product AI dependencies now use `pydantic-ai-slim[openai]` for the
  OpenRouter-backed starter code instead of the full Pydantic AI meta-package.
- Transactional email logs now record template context keys/count only, avoiding context values that may contain verification codes or reset tokens.
- Frontend documentation now shows HTMX partial responses with explicit partial
  templates rather than unsupported template-fragment suffixes.
- Blog posts now render from repo-tracked Markdown files in `apps/pages/posts`
  instead of a database-backed blog model or internal admin API.

### Added
- Bootstrapped the CiteGuild repository from Djass's current
  `django-saas-starter` baseline with all generator features enabled except
  DigitalOcean deployment, and recorded the reproducible inputs in
  `djass-manifest.json`.
- Opt-in mutmut mutation testing for service and utility behavior kernels, with
  Django import-path handling, Makefile commands, and a documented survivor
  workflow.
- Schemathesis-powered API property tests that exercise the Django Ninja
  OpenAPI contract with test-owned authentication, including `make api-fuzz`
  for focused local runs.
- Hypothesis property-based testing, including a generated API-key round-trip
  invariant, Django database-test guidance, and seed-based failure reproduction
  commands.
- Local quality command contract in `docs/quality.md`, with Makefile targets
  for local CI, touched-area checks, frontend checks, migration checks, Django
  checks, pytest, static analysis, and typing visibility.
- No-Docker local terminal development path with `.env.terminal.example`,
  `terminal-*` Makefile targets, generated docs, and
  `.agents/skills/local-terminal-development`.
- PGSandbox MCP testing guidance, including `.agents/skills/pgsandbox-testing`
  and `make test-local-postgres` for disposable local Postgres checks.
- Alpine.js skill in `.agents/skills/alpinejs-django` covering Django template patterns, safe data passing, accessibility, and HTMX coordination.
- Django Ninja skill in `.agents/skills/django-ninja` covering API endpoints,
  schemas, routers, authentication, OpenAPI docs, and API tests.
- Django Q2 skill in `.agents/skills/django-q2` covering background tasks,
  schedules, `qcluster` workers, Redis broker defaults, testing, and ORM broker
  fallback.
- Django/HTMX coding-agent skill in `.agents/skills/django-htmx` covering
  server-rendered partial updates, forms, swaps, events, response headers, and
  Alpine.js coordination.
- CapRover deployment skill in `.agents/skills/caprover-deployment` covering split server/worker setup, per-app deploy tokens, API/CLI-only provisioning, and verification.
- Cross-agent Pydantic AI skills in `.agents/skills/` when `use_ai` is enabled.
- Fly.io deployment support with `fly.toml`, web and worker process groups, migration release commands, and `DATABASE_URL` support.
- HTMX, django-htmx middleware, Alpine.js, and frontend rules for Django-native interactivity.
- `ALLOW_SIGNUPS` environment flag (default `True`) to pause new email/social registrations while keeping existing user logins available.
### Removed
- Stimulus, Webpack, `python-webpack-boilerplate`, manifest loading, and generated Webpack configuration.
- Structlog, django-structlog, and structlog-sentry dependencies.

### Fixed
- PostHog task tests now assert the configured runtime environment instead of
  assuming every test run uses the development environment.
- Test settings now allow the WSGI hosts used by Django and Schemathesis so the
  OpenAPI property suite can load the schema in CI.
- S3-compatible media storage now includes the direct `boto3` runtime dependency
  required by `django-storages`.
- Local Docker Compose now waits for the frontend watcher to finish its first asset build, and `npm run watch` now keeps browser modules in sync while editing JavaScript.
- SEO metadata now uses project-scoped social tags/schema data, keeps private auth/app pages out of indexing, and limits blog listing/sitemaps to published posts.
