# CiteGuild Structure and Placement

This file tells coding agents where work belongs. It describes current paths
and target domain boundaries; it does not imply that every target module has
already been implemented.

## Existing Repository Map

- `apps/core/`: shared account/profile behavior, auth-adjacent flows, Stripe
  webhooks, shared tasks/utilities, analytics, and common tests.
- `apps/api/`: Django Ninja authentication, schemas, routers, services, and API
  contract tests.
- `apps/mcp_server/`: FastMCP server, OAuth/API-key authentication, protocol
  analytics, tools, and tests.
- `apps/pages/`: server-rendered marketing/app pages, repository-backed blog and
  documentation content, views, services, and tests.
- `citeguild/`: project settings, root URLs, ASGI/WSGI entry points, storage,
  logging, Sentry, and cross-app configuration.
- `frontend/templates/`: Django templates. Put reusable fragments under
  `components/`; product screens under `pages/` unless an app-owned template
  directory is more appropriate.
- `frontend/src/js/`: small browser modules; no product business rules.
- `frontend/src/styles/`: Tailwind/global styles governed by `DESIGN.md`.
- `deployment/`, `docker-compose-*.yml`, `.github/workflows/`: image, runtime,
  service, CI, review, and deployment configuration.
- `docs/architecture/`: accepted and proposed architecture decisions that
  coordinate multiple product domains or external systems.
- `docs/quality.md`: verification command contract.
- `.agents/skills/`: reusable project workflows, not one-task instructions.

## Product Domain Placement

As CiteGuild domains are introduced, prefer cohesive Django apps over adding
unrelated models and services to `apps/core/`:

- `apps/projects/`: subscribed sites/projects, sitemap URLs, ownership,
  lifecycle, dashboard operations, and sync status. Do not create an
  `apps/sites/` app because `django.contrib.sites` already owns the `sites` app
  label.
- `apps/articles/`: article records, canonicalization, content extraction,
  hashes, lifecycle, and detected outbound links.
- `apps/search/`: embedding/Qdrant adapter, indexing/upsert logic, and the
  shared authenticated semantic-search service.
- `apps/citations/`: detected member-to-member relationship reconciliation and
  network queries if this grows beyond article-owned link observations.

The task implementing the first model in a domain should create the app and
register it in `citeguild/settings.py`; later tasks should follow that boundary.
If the live task or existing implementation establishes a different coherent
name, update this file in the same PR rather than creating parallel concepts.

## Cross-Surface Rules

- Keep product behavior in domain services. Django views, Ninja routes, MCP
  tools, CLI commands, and Q2 tasks should validate/translate input and call the
  same service rather than reimplementing rules.
- Keep API wire types in `apps/api/schemas.py` or a domain-scoped schema module;
  do not make transport schemas the domain model.
- Keep MCP authentication/protocol concerns in `apps/mcp_server/`; import the
  shared search service for retrieval behavior.
- Add the CLI as a thin client/package around the authenticated API or shared
  stable contract. Do not couple it to Django ORM internals if it must be
  distributed independently.
- Keep scheduled orchestration thin. Put retryable sitemap/article operations
  in domain services and call them from Django Q2 tasks.
- Put reusable external-service clients behind adapters with narrow interfaces;
  do not scatter raw Qdrant, HTTP crawler, Stripe, or analytics calls through
  views and models.

## Model and Migration Rules

- Tenant-owned models need explicit ownership paths and indexes supporting
  authorization-critical queries.
- Use stable unique constraints for canonical URLs, job idempotency, Qdrant
  point IDs, and active citation observations where appropriate.
- Prefer inactive/status timestamps over hard deletion for articles and
  detected citations.
- Create models first, generate migrations, inspect them, and never hand-edit
  historical migrations without an explicit migration-repair task.
- Place tests beside the owning app (`tests/` for a growing suite); include
  tenant isolation, retry/idempotency, hostile input, and state-transition
  cases for high-risk domains.

## Documentation Placement

- Product decisions and non-goals: `PRODUCT.md` and the linked Outline memo.
- Architecture/security/deployment invariants: `TECH.md`.
- Detailed cross-domain decisions: numbered ADRs under `docs/architecture/`,
  linked from `TECH.md`.
- UI system and product interaction language: `DESIGN.md`.
- Events, funnels, identity, and privacy: `ANALYTICS.md`.
- Repo-wide agent workflow: `AGENTS.md`.
- End-user docs: `apps/pages/content/docs/`, with navigation changes in
  `apps/pages/content/docs/navigation.yaml`.
- Temporary task detail and validation evidence: the live Rowset task, not a
  new permanent repo document.

Avoid vendor-specific steering files unless the repository deliberately adopts
that vendor. Shared instructions belong in `AGENTS.md` and the focused canonical
files above so Codex, Claude Code, Gemini, and other agents receive one contract.
