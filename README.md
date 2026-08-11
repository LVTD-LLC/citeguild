# CiteGuild

AI-native editorial source network for relevant agent-discovered citations

Product definition: [CiteGuild — AI-Native Editorial Link Network](https://outline.gregagi.com/doc/citeguild-ai-native-editorial-link-network-ss3kILTcjB).

This is a Django SaaS application generated from `django-saas-starter`. It
ships with authentication, a Django-native frontend, a small API surface,
background workers, production deployment files, and clear agent/human
development guidance.

## Key Features

- Django 6.0 application with apps organized under `apps/`.
- Email/password auth, passkey sign in and signup, recovery codes, and optional
  social login through `django-allauth`.
- Django templates, Tailwind CSS, HTMX, and Alpine.js without a JavaScript SPA
  framework.
- Django Ninja API with a healthcheck endpoint and authenticated user endpoint.
- Django Q2 workers backed by Redis by default.
- PostgreSQL 18 local and CI configuration, including `pgvector` and
  `pg_stat_statements` migrations.
- Docker, Fly.io, Render, and CapRover deployment files.

- Tool-neutral `AGENTS.md` plus focused `PRODUCT.md`, `TECH.md`, `STRUCTURE.md`,
  `DESIGN.md`, and `ANALYTICS.md` contracts for humans and coding agents.

- ReviewGate AI reviews for same-repository pull requests.


- Stripe Checkout, Billing Portal links, and defensive webhook handling.


- Public blog pages rendered from repo-tracked Markdown posts.


- Authenticated product documentation pages with copyable code blocks.


- Hosted MCP server with OAuth discovery, Dynamic Client Registration, and a
  first `get_user_info` tool.


## Table of Contents

- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Golden Path](#golden-path)
- [Local Development](#local-development)
- [Architecture](#architecture)
- [Environment Variables](#environment-variables)
- [API](#api)

- [Hosted MCP Server](#hosted-mcp-server)

- [Frontend](#frontend)
- [AI-Assisted Development](#ai-assisted-development)

- [ReviewGate AI Reviews](#reviewgate-ai-reviews)

- [Available Commands](#available-commands)
- [Testing And Quality](#testing-and-quality)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Tech Stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.14.5 |
| Framework | Django 6.0.5 |
| Package manager | uv |
| Database | PostgreSQL 18 |
| Cache and queue broker | Redis 8.6.3 |
| Background jobs | Django Q2 |
| API | Django Ninja |
| Auth | django-allauth, allauth MFA, WebAuthn/passkeys |
| Frontend | Django templates, Tailwind CSS 4, HTMX, Alpine.js |
| Static files | Whitenoise plus Django staticfiles |
| Email | Anymail with Mailgun, console email fallback, Mailhog locally |
| Local services | Docker Compose |
| CI | GitHub Actions, pre-commit, ruff, djlint, pytest, ESLint, pyscn |
| Deployment | Shared Docker image, Fly.io, Render, CapRover |

| Observability | Sentry traces, profiling, logs, and error monitoring |


| Product AI | Pydantic AI through OpenRouter model presets |


| Agent protocol | FastMCP mounted into ASGI at `/mcp/` |


## Prerequisites

Install these before running the project locally:

- Python 3.14.5 or newer within the `pyproject.toml` range.
- [uv](https://docs.astral.sh/uv/) for Python dependency management.
- Node.js 24.15.0 or newer and npm.
- Docker Desktop or Docker Engine if using Compose-managed services.
- PostgreSQL and Redis if using the terminal-only no-Docker path.
- Git.

Optional accounts or CLIs, depending on what you plan to use:

- Mailgun account for production email.

- Stripe account and Stripe CLI for payment and webhook work.


- S3-compatible object storage for production media uploads.


- Chatwoot Website inbox for support chat.


- Apprise API server for admin/internal notifications.


- OpenRouter API key for product AI features.


- Sentry project DSN for traces, profiling, logs, and errors.


- Fly.io or CapRover credentials if deploying through those paths.

## Golden Path

Use this path for day-to-day local development. Django, tests, workers, and
frontend commands run on your host. Docker Compose only provides backing
services.

```bash
cp .env.agent.example .env
make agent-services
make terminal-setup
uv run python manage.py makemigrations
make terminal-migrate
make terminal-manage check
make terminal-web
```

Run `makemigrations` without app labels. This project contains multiple apps,
and unlabeled `makemigrations` lets Django detect model changes across all of
them before you start feature work.

Open separate terminals for the normal development process set:

```bash
make terminal-web
make terminal-worker
make terminal-assets
```

Default local URLs:

| Service | URL |
| --- | --- |
| Django app | `http://localhost:8000` |
| Django admin | `http://localhost:8000/admin/` |
| API docs | `http://localhost:8000/api/docs` |
| Healthcheck | `http://localhost:8000/api/healthcheck` |
| Mailhog | `http://localhost:8025` |

| Minio console | `http://localhost:9001` |


| MCP endpoint | `http://localhost:8000/mcp/` |
| Runtime agent instructions | `http://localhost:8000/AGENTS.md` |


## Local Development

### Agent local development with Compose-backed services

Use this when an AI coding agent, or any host-terminal workflow, should run app
commands directly while Compose manages Postgres, Redis, Mailhog, Minio, MJML.

```bash
cp .env.agent.example .env
make agent-services
make terminal-setup
uv run python manage.py makemigrations
make terminal-migrate
make terminal-manage check
make terminal-web
```

When multiple generated projects run on the same machine, give each one a
unique port set and keep `.env` values aligned:

```bash
LOCAL_WEB_PORT=8001 LOCAL_POSTGRES_PORT=55433 LOCAL_REDIS_PORT=56380 make agent-services
DJANGO_RUNSERVER_PORT=8001 SITE_URL=http://localhost:8001 POSTGRES_PORT=55433 REDIS_PORT=56380 make terminal-web
```

If two clones share the same generated slug, isolate Docker Compose and Redis
namespaces:

```bash
COMPOSE_PROJECT_NAME=citeguild-agent-a make agent-services
LOCAL_INSTANCE_ID=citeguild-agent-a CACHE_KEY_PREFIX=citeguild-agent-a Q_CLUSTER_NAME=citeguild-agent-a-q make terminal-worker
```

Stop only the backing services when you are done:

```bash
make agent-services-down
```

### Terminal local development (no Docker)

Use this path when Postgres and Redis already run on your machine through a
package manager, a local service manager, or a remote development database.

```bash
cp .env.terminal.example .env
make terminal-setup
uv run python manage.py makemigrations
make terminal-migrate
make terminal-manage check
make terminal-web
```

Create the local PostgreSQL role and database named in `.env`, or replace the
split `POSTGRES_*` values with a full `DATABASE_URL`. The terminal env file
defaults Redis to `redis://localhost:6379/0` and email to Django's console
backend so Mailhog is not required.

### Docker-backed local development

Use this when you want Compose to run everything: Postgres, Redis, Mailhog, the
Django web process, workers, and the frontend watcher.

```bash
cp .env.example .env
uv sync --locked
npm ci
npm run build
uv run python manage.py makemigrations
make serve
```

`make serve` builds local images, starts `docker-compose-local.yml`, applies
migrations in the backend container, waits for the first frontend asset build,
and follows backend logs.

### Disposable Postgres testing with PGSandbox MCP

PGSandbox MCP gives MCP-capable coding agents a safe way to create and clean up
real local PostgreSQL databases for tests. It is agent-side tooling, not an app
runtime dependency.

Project: [`lvtd-llc/pgsandbox-mcp`](https://github.com/lvtd-llc/pgsandbox-mcp)

Install with Homebrew:

```bash
brew install lvtd-llc/tap/pgsandbox-mcp
```

Or use the install script:

```bash
curl -fsSL https://raw.githubusercontent.com/lvtd-llc/pgsandbox-mcp/main/scripts/install.sh | sh
```

Configure your MCP client with an existing Postgres admin URL:

```bash
pgsandbox-mcp setup --client codex --admin-url "$PGSANDBOX_ADMIN_DATABASE_URL"
pgsandbox-mcp doctor
```

When an agent has the `pgsandbox` MCP server available, ask it to create a
disposable database, export the returned URL, run the checks, and delete the
database:

```bash
DATABASE_URL="<pgsandbox connection string>" make test-local-postgres
```

`make test-local-postgres` runs migration drift checks, applies migrations,
runs `manage.py check`, and runs pytest with pytest-django reusing the sandbox
database. It fakes the extension-only migration because normal PGSandbox roles
cannot create superuser-only Postgres extensions.

## Architecture

The target CiteGuild MVP domain model, PostgreSQL/Qdrant ownership, lifecycle
states, job boundaries, idempotency rules, shared search contract, and CapRover
topology are defined in [ADR 0001: Define the MVP domain and service
boundaries](docs/architecture/0001-mvp-domain-and-service-boundaries.md).

### Directory Structure

```text
.
|-- AGENTS.md                         # Tool-neutral coding-agent guidance
|-- PRODUCT.md                        # Product, pricing, MVP, and non-goals
|-- TECH.md                           # Architecture, security, and deployment contract
|-- STRUCTURE.md                      # Domain boundaries and placement rules
|-- ANALYTICS.md                      # Metrics, events, identity, and privacy contract
|-- DESIGN.md                         # Design-system source of truth
|-- Makefile                          # Local, Compose, test, and analysis commands
|-- apps/
|   |-- api/                          # Django Ninja API routers, auth, schemas, services

|   |-- blog/                         # Markdown-backed public blog app and posts

|   |-- core/                         # Profiles, auth helpers, forms, tasks, email, shared domain code

|   |-- docs/                         # Authenticated documentation app and Markdown content


|   |-- mcp_server/                   # FastMCP server, OAuth endpoints, token models

|   `-- pages/                        # Landing, home, settings, legal, pricing pages
|-- deployment/
|   |-- Dockerfile                    # Shared production image
|   `-- entrypoint.sh                 # server/worker process selector
|-- docker-compose-local.yml          # Local services and app containers
|-- docker-compose-prod.yml           # Production-style Compose runtime
|-- frontend/
|   |-- src/
|   |   |-- js/                       # Small browser modules copied without bundling
|   |   `-- styles/                   # Tailwind CSS entrypoint
|   |-- static/                       # Built CSS, JS, and vendor assets
|   `-- templates/                    # Django templates
|-- citeguild/
|   |-- settings.py                   # Env-driven Django settings
|   |-- test_settings.py              # Faster isolated pytest settings
|   |-- urls.py                       # Root URL routing
|   |-- asgi.py                       # ASGI app with `/mcp/` mount
|   `-- wsgi.py                       # WSGI app for non-MCP deployments only
|-- package.json                      # Frontend scripts and dependencies
|-- pyproject.toml                    # Python dependencies and tool config
|-- pytest.ini                        # pytest-django settings
`-- uv.lock                           # Locked Python dependency graph
```

### Request Lifecycle

1. The request reaches Django through Gunicorn WSGI, or ASGI when MCP is enabled.
2. Security, session, CSRF, HTMX, auth, logging, allauth, and message middleware run.
3. URL routing dispatches to `apps/pages`, `apps/core`, `apps/api`, or `apps/mcp_server`.
4. Views, forms, services, schemas, and models perform validation and domain work.
5. Django templates render HTML, Django Ninja returns JSON, or FastMCP returns MCP protocol responses.
6. Logs include request context and render as readable console output in development or JSON in production.

### Logging and Observability

Use Python's standard `logging` module and keep stable dotted `event.name`
values in both the message and `extra`, for example:

```python
logger.info(
    "dataset.index.completed",
    extra={
        "event.name": "dataset.index.completed",
        "dataset_id": dataset.id,
        "duration_ms": duration_ms,
        "outcome": "success",
    },
)
```

`outcome` is always `success` or `failure`; put richer lifecycle detail in a
separate field such as `operation.status`. Prefer scalar identifiers, counts,
durations, statuses, and `error.type`. Never log credentials, cookies, email
addresses, request/response bodies, arbitrary metadata, or user-owned content.

Every Django request emits one `http.request.completed` event with a bounded
`request.id`, `request.interface` (`web`, `htmx`, or `rest`), normalized
`http.route`, status, duration, and actor IDs when already available. Django Q2
workers emit `background_job.completed` without task arguments or results.
These fields stay queryable in JSON logs and Sentry. PostHog receives an asynchronous clone restricted to an explicit field allowlist; unknown fields and the original formatted message are dropped, and `posthogDistinctId` is derived inside the exporter from `profile_id`.

The server-truth product event catalog, deduplication rules, privacy boundary,
and MVP metric recipes live in [the paid-to-citation analytics contract](docs/analytics/funnel-events.md).

### Application Boundaries

| Area | Responsibility |
| --- | --- |
| `apps/core` | Profile lifecycle, API keys, account settings, email delivery, shared utilities, background tasks, Stripe webhooks. |
| `apps/pages` | Marketing pages, app home, settings, legal pages, pricing, public blog posts, and authenticated Markdown docs content. |
| `apps/api` | Django Ninja API auth, schemas, serializers, and routers. |

| `apps/mcp_server` | Hosted MCP server, OAuth metadata, Dynamic Client Registration, authorization code flow, token models, and MCP auth. |

| `frontend/templates` | Server-rendered UI. |
| `frontend/src/js` | Small browser modules copied to static files. |
| `frontend/src/styles` | Tailwind CSS source. |

### Data Model

Core generated models:

| Model | Purpose |
| --- | --- |
| `django.contrib.auth.models.User` | Login identity managed by Django and allauth. |
| `apps.core.Profile` | One-to-one user profile, API key prefix/hash, lifecycle state, Stripe customer/subscription IDs. |
| `apps.core.ProfileStateTransition` | Auditable state transition history for profiles. |
| `apps.core.EmailSent` | Record of transactional email delivery attempts. |

| `apps.mcp_server.McpOAuthClient` | OAuth clients registered by MCP clients through DCR. |
| `apps.mcp_server.McpOAuthAuthorizationCode` | Short-lived PKCE authorization codes. |
| `apps.mcp_server.McpOAuthAccessToken` | Bearer access tokens scoped to MCP resources. |
| `apps.mcp_server.McpOAuthRefreshToken` | Refresh tokens for MCP clients requesting `offline_access`. |


Generated migrations include PostgreSQL extension setup before app model
migrations. Do not edit historical migrations unless you intentionally need to
change the migration history.


Blog posts are not database records. Published posts live as Markdown files in
`apps/pages/posts`, and every `*.md` file in that directory is rendered on deploy.
Keep drafts outside that folder until they are ready to publish.


### Background Jobs

Django Q2 runs through `make terminal-worker`, the `workers` Compose service, or
the production worker process. Redis is the default broker. Test settings and
`make test-local-postgres` can switch to local-memory cache and the ORM broker
for isolated runs.

### Authentication

The project uses `django-allauth` for account flows:

- Email/password login.
- Passkey login and passkey signup through WebAuthn.
- Mandatory email-code verification.
- Recovery codes for passkey fallback.
- Optional GitHub social login when `GITHUB_CLIENT_ID` and
  `GITHUB_CLIENT_SECRET` are configured.
- `ALLOW_SIGNUPS=False` to pause new registrations while keeping existing
  logins active.

API keys are generated from Python's `secrets` module, shown once, stored as a
salted hash with a public lookup prefix, and accepted through Bearer or
`X-API-Key` headers.

## Environment Variables

Copy the env file that matches your workflow:

| File | Use case |
| --- | --- |
| `.env.agent.example` | Host-run app commands with Compose-managed backing services. |
| `.env.terminal.example` | Host-run app commands with local or remote Postgres/Redis. |
| `.env.example` | Docker Compose and production-like defaults. |

Required core variables:

| Variable | Description | Local example |
| --- | --- | --- |
| `ENVIRONMENT` | `dev` or `prod`. Production enables secure defaults. | `dev` |
| `DEBUG` | Django debug flag. Keep false in production. | `on` |
| `SECRET_KEY` | Django signing secret. Generate a strong production value. | `super-secret-key` |
| `SITE_URL` | Canonical public origin for emails, metadata, sitemap, and CSRF origin. | `http://localhost:8000` |
| `ALLOW_SIGNUPS` | Pause new signups when set to `False`. | `True` |

Database and Redis:

| Variable | Description |
| --- | --- |
| `DATABASE_URL` | Full Postgres URL. Takes precedence over split `POSTGRES_*` values. |
| `POSTGRES_HOST` | Postgres host, usually `localhost` for host-run dev or `db` for Compose. |
| `POSTGRES_DB` | Database name. |
| `POSTGRES_USER` | Database user. |
| `POSTGRES_PASSWORD` | Database password. |
| `POSTGRES_PORT` | Database port. |
| `REDIS_URL` | Full Redis URL. Leave blank to build from split Redis values. |
| `REDIS_HOST` | Redis host, usually `localhost` or `redis`. |
| `REDIS_PASSWORD` | Redis password. |
| `REDIS_PORT` | Redis port. |
| `REDIS_DB` | Redis logical database number. |
| `LOCAL_INSTANCE_ID` | Namespace seed for local cache and worker names. |
| `CACHE_KEY_PREFIX` | Django cache key prefix. |
| `Q_CLUSTER_NAME` | Django Q2 cluster name. |

Qdrant collection and connection:

| Variable | Description |
| --- | --- |
| `QDRANT_URL` | Qdrant HTTP API URL. Production uses the private CapRover service address. |
| `QDRANT_API_KEY` | Qdrant admin API key. Keep it in the deployment environment only. |
| `QDRANT_TIMEOUT_SECONDS` | Client request timeout in seconds. Defaults to `5`. |
| `CITEGUILD_QDRANT_COLLECTION` | Stable article collection name. Defaults to `citeguild-articles`. |
| `CITEGUILD_EMBEDDING_DIMENSIONS` | Must exactly match the collection vector size. Defaults to `1536`. |

The server startup validates or creates the cosine article collection. Use
`python manage.py rebuild_qdrant_articles` to reconstruct it from PostgreSQL.

Production security variables:

| Variable | Default |
| --- | --- |
| `SECURE_SSL_REDIRECT` | `True` when `ENVIRONMENT=prod`, else `False` |
| `SESSION_COOKIE_SECURE` | `True` when `ENVIRONMENT=prod`, else `False` |
| `CSRF_COOKIE_SECURE` | `True` when `ENVIRONMENT=prod`, else `False` |
| `SECURE_HSTS_SECONDS` | `31536000` when `ENVIRONMENT=prod`, else `0` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `False` |
| `SECURE_HSTS_PRELOAD` | `False` |

Logging and observability:

| Variable | Description |
| --- | --- |
| `DJANGO_LOG_LEVEL` | Minimum application log level. Defaults to `INFO`. |
| `DJANGO_LOG_FORMAT` | `console` in development or `json` in production by default. |
| `SERVICE_NAME` | Service facet; defaults to `citeguild-web` or `citeguild-worker`. |
| `SERVICE_VERSION` | Optional release/deploy identifier shared by log backends. |

Email:

| Variable | Description |
| --- | --- |
| `EMAIL_BACKEND` | Optional backend override. Console backend is useful locally. |
| `EMAIL_HOST` | SMTP host, `mailhog` in Compose. |
| `EMAIL_PORT` | SMTP port, `1025` for Mailhog. |
| `MAILGUN_API_KEY` | Enables Anymail Mailgun delivery outside debug mode. |
| `MAILGUN_SENDER_DOMAIN` | Mailgun sender domain. |
| `DEFAULT_FROM_EMAIL` | User-facing sender address. |
| `SERVER_EMAIL` | Error sender address. |

Optional feature variables:

| Variable | Feature |
| --- | --- |

| `AWS_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET_NAME` | S3-compatible media storage. |


| `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_CONTEXT`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_MONTHLY`, `WEBHOOK_UUID` | Stripe Checkout, Billing Portal, explicit account routing, and webhook verification for the single $10 monthly plan. |


| `MJML_URL` | MJML HTTP server for email rendering. |


| `APPRISE_API_URL`, `APPRISE_CONFIG_KEY`, `APPRISE_BASIC_AUTH_USER`, `APPRISE_BASIC_AUTH_PASSWORD`, `APPRISE_NOTIFICATION_FORMAT`, `APPRISE_REQUEST_TIMEOUT`, `ADMIN_NOTIFICATION_EMAIL_FALLBACK`, `ADMIN_NOTIFICATION_EMAIL_RECIPIENTS` | Admin/internal notifications through Apprise. |


| `OPENROUTER_API_KEY`, `OPENROUTER_APP_URL`, `OPENROUTER_APP_TITLE`, `OPENROUTER_MODEL_FAST`, `OPENROUTER_MODEL_SMART` | Product AI model routing and app attribution through OpenRouter. |


| `HEALTHCHECKS_PING_BASE_URL` | Optional outbound Healthchecks ping URL prefix. Leave empty to disable pings. |


| `SENTRY_DSN`, `SENTRY_ENABLED`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_BROWSER_ENABLED`, `SENTRY_BROWSER_TRACES_SAMPLE_RATE`, `SENTRY_BACKGROUND_TRACES_SAMPLE_RATE`, `SENTRY_PROFILE_SESSION_SAMPLE_RATE`, `SENTRY_ENABLE_LOGS`, `SENTRY_BREADCRUMB_LEVEL`, `SENTRY_EVENT_LEVEL`, `SENTRY_LOGS_LEVEL`, `SENTRY_SEND_DEFAULT_PII`, `SENTRY_INCLUDE_LOCAL_VARIABLES`, `SENTRY_MAX_BREADCRUMBS`, `SENTRY_DJANGO_MIDDLEWARE_SPANS`, `SENTRY_DJANGO_CACHE_SPANS` | Sentry server/browser errors, logs, traces, Web Vitals, and profiling controls. |


| `POSTHOG_API_KEY`, `POSTHOG_HOST`, `POSTHOG_BROWSER_HOST`, `POSTHOG_LOGS_ENABLED`, `POSTHOG_LOG_LEVEL` | Consented browser and server analytics plus optional batched privacy-filtered OTLP log export. Use a first-party browser proxy in production when possible. |

| `POSTHOG_AI_OBSERVABILITY_ENABLED`, `POSTHOG_SERVICE_NAME` | Optional content-free Pydantic AI model and embedding performance traces. |



| `CHATWOOT_BASE_URL`, `CHATWOOT_WEBSITE_TOKEN`, `CHATWOOT_HMAC_SECRET` | Chatwoot support chat and identity validation. |



The pages app includes a full generated environment variable reference under
the deployment documentation.


## API

The API is mounted at `/api/` and implemented with Django Ninja.

| Endpoint | Auth | Purpose |
| --- | --- | --- |
| `GET /api/healthcheck` | none | Checks database and Redis connectivity. |
| `POST /api/projects` | `X-API-Key` or Bearer API key | Validates one XML sitemap and queues its initial sync. |
| `GET /api/user` | `X-API-Key` or Bearer API key | Returns safe account/profile details for the authenticated profile. |
| `GET /api/user/settings` | browser session | Private settings data for the authenticated user settings page. |

The blog has no write API. Add or update posts by committing Markdown files
under `apps/pages/posts` and deploying the repository.


Example API calls:

```bash
curl "$SITE_URL/api/healthcheck"

curl "$SITE_URL/api/user" \
  -H "Authorization: Bearer $CITEGUILD_API_KEY"

curl "$SITE_URL/api/user" \
  -H "X-API-Key: $CITEGUILD_API_KEY"
```

API keys are managed from the user settings page. They are shown only once when
generated or rotated.


## Go CLI

The dependency-free Go CLI under `cli/` is the preferred CiteGuild interface
for OpenClaw, Hermes, shell agents, and scripts. It wraps the authenticated v1
API and provides human output, stable JSON, secret-safe local configuration
status, remote authentication checks, bounded requests, and deterministic exit
codes.

```bash
export CITEGUILD_API_KEY="<copy the key from CiteGuild settings>"
cd cli
go run ./cmd/citeguild config status
go run ./cmd/citeguild auth status
go run ./cmd/citeguild search --json --limit 5 \
  "How do Django transaction commit hooks work?"
```

Run `make cli-quality` for formatting, vet, unit/race tests, build, and a clean
install smoke. Versioned `cli/vX.Y.Z` tags on `main` publish checksum-backed
Linux amd64 and macOS arm64 archives. See [`cli/README.md`](cli/README.md) for
the install, output, exit-code, and release contracts.


## Hosted MCP Server

This project includes a hosted MCP server at `/mcp/`, spec-compatible OAuth
discovery endpoints, Dynamic Client Registration, browser authorization, token
refresh/revocation, and ready-to-copy runtime agent instructions at
`/AGENTS.md`.

The server intentionally exposes only two tools:

- `get_user_info`, backed by the same serializer as `GET /api/user`.
- `search_member_articles`, backed by the shared versioned `SearchService` used
  by `POST /api/v1/search`. It accepts a query or draft passage, a 1–50 result
  limit, an optional language, and up to 20 exact excluded domains. Results are
  candidate sources, not endorsements or forced-link instructions.

MCP URLs:

| URL | Purpose |
| --- | --- |
| `/mcp/` | Streamable HTTP MCP endpoint. |
| `/AGENTS.md` | Runtime agent setup instructions served by the app. |
| `/.well-known/oauth-protected-resource` | OAuth protected resource metadata. |
| `/.well-known/oauth-protected-resource/mcp` | MCP-specific protected resource metadata. |
| `/.well-known/oauth-authorization-server` | Authorization server metadata. |
| `/.well-known/openid-configuration` | OpenID-compatible discovery metadata. |
| `/oauth/register` | Dynamic Client Registration. |
| `/oauth/authorize` | Browser authorization endpoint. |
| `/oauth/token` | Token endpoint. |
| `/oauth/revoke` | Token revocation endpoint. |

Modern MCP clients should use OAuth:

1. Add `<production-url>/mcp/` to the MCP client.
2. Let the client discover metadata and register itself.
3. Complete the browser sign-in flow.
4. Verify the connection by calling `get_user_info`.

Legacy clients may authenticate with the user API key:

```text
X-API-Key: <api_key>
Authorization: Bearer <api_key>
```

API keys are intentionally not accepted in query strings.

For environment-backed bearer authentication in Codex, export
`CITEGUILD_API_KEY` and configure `~/.codex/config.toml` without placing the raw
key in the file:

```toml
[mcp_servers.citeguild]
url = "<production-url>/mcp/"
bearer_token_env_var = "CITEGUILD_API_KEY"
```

For Claude Code, use its OAuth flow or an HTTP MCP entry whose Authorization
header is `Bearer ${CITEGUILD_API_KEY}`. Project `.mcp.json` supports environment
variable expansion; never commit an expanded credential.

Give an agent this starter prompt:

```text
CiteGuild skills repository: https://github.com/LVTD-LLC/citeguild-skills
CiteGuild API key: <copy securely from the CiteGuild dashboard>
```

MCP uses ASGI. The generated production server command runs
`gunicorn citeguild.asgi:application` with
`uvicorn_worker.UvicornWorker`.

When `POSTHOG_API_KEY` is configured, MCP protocol and tool-usage events are
captured automatically. Argument values, tool responses, and exception payloads
are excluded; only argument names and coarse value types are retained.



## Frontend

The frontend is intentionally Django-native:

- Django templates are the source of UI truth.
- Tailwind CSS builds from `frontend/src/styles/index.css` to
  `frontend/static/css/app.css`.
- HTMX handles server-rendered partial updates.
- Alpine.js handles local browser state such as menus, toggles, and modals.
- Small shared browser modules live in `frontend/src/js/` and are copied to
  `frontend/static/js/` without bundling.

- Keyboard shortcuts are wired from rendered navigation controls and show
  desktop key hints.


Frontend commands:

```bash
npm ci
npm run build
npm run watch
npm run lint
```

Use HTMX when the server should return fresh HTML. Use Alpine.js when state is
local to the browser. Keep Django forms and server validation as the source of
truth.

### Theme and design system

This project includes a root `DESIGN.md` file based on the public Google Labs
Code `DESIGN.md` alpha format. It gives humans and coding agents a shared,
tool-neutral design source of truth for colors, typography, spacing, radii,
components, and practical UI rules.

Validate it with:

```bash
npx @google/design.md lint DESIGN.md
```

For UI implementation work, read
`.agents/skills/frontend-ui-quality/SKILL.md` before editing Django templates,
Tailwind classes, responsive layouts, motion, or component states.


Keyboard shortcuts are data-driven from controls that already render in the
current template. Add `data-shortcut-key` and a desktop-only `.shortcut-kbd`
hint to new navigation actions only when the shortcut is stable and unlikely to
conflict with text entry.


## AI-Assisted Development

The CiteGuild repository keeps coding-agent guidance tool-neutral and separates
durable context by concern:

- `AGENTS.md` is the canonical repo guidance for coding agents.
- `PRODUCT.md` is the canonical pricing, workflow, scope, and non-goal contract.
- `TECH.md` is the canonical architecture, security, integration, deployment,
  and command contract.
- `STRUCTURE.md` is the canonical file-placement and domain-boundary guide.
- `ANALYTICS.md` is the canonical metrics, event, identity, and privacy contract.
- `DESIGN.md` is the canonical design-system source of truth.
- `docs/quality.md` is the local CI path and touched-area quality command
  matrix for humans and coding agents.
- `.agents/skills/alpinejs-django/SKILL.md` covers Alpine.js patterns for
  Django templates and HTMX partial updates.
- `.agents/skills/django-ninja/SKILL.md` covers Django Ninja endpoints,
  schemas, routers, authentication, OpenAPI docs, and tests.
- `.agents/skills/django-q2/SKILL.md` covers Django Q2 workers, schedules,
  Redis broker defaults, and ORM broker fallback for tests.
- `.agents/skills/django-htmx/SKILL.md` covers server-rendered partial updates,
  forms, swaps, response headers, tests, and Alpine.js coordination.
- `.agents/skills/local-terminal-development/SKILL.md` covers terminal-first
  local development with or without Compose-backed services.
- `.agents/skills/pgsandbox-testing/SKILL.md` covers disposable local Postgres
  checks with PGSandbox MCP.
- `.agents/skills/frontend-ui-quality/SKILL.md` covers generated-project UI
  quality checks for templates, Tailwind CSS, accessibility, responsive states,
  and design-system alignment.
- `.agents/skills/agent-reliability/SKILL.md` covers repeatable agent task
  framing, high-risk behavior kernels, parity tests, coverage visibility,
  scoped type checking, and eval seed maintenance.
- `docs/agent-task-templates.md`, `docs/code-tours/`, and
  `docs/agent-evals/seed-tasks.md` give agents concrete task frames, flow
  tours, and repeatable seed tasks for mining failures back into tests and
  guidance.

- `.agents/skills/` contains bundled cross-agent Pydantic AI skills from
  [`pydantic/skills`](https://github.com/pydantic/skills).


- `apps/pages/content/AGENTS.md` contains scoped content-writing guidance.


- The hosted app serves runtime MCP setup instructions at `/AGENTS.md`.


Do not add IDE-specific or agent-vendor-specific instruction files unless the
team explicitly standardizes on one tool. Codex, Claude Code, Gemini, and other
agents should read the same canonical files rather than maintain duplicate
copies that drift.

`make pyscn-check` runs a CI-friendly static analysis gate for complexity and
dead code. `make pyscn-analyze` creates a local `.pyscn/` report with broader
structural findings, including clone detection, for refactoring passes.

Use `docs/quality.md` before PRs and when choosing targeted checks for a
touched area.


## ReviewGate AI reviews

The generated `.github/workflows/reviewgate.yml` reviews same-repository pull
requests with ReviewGate. Add `OPENROUTER_API_KEY` as a GitHub Actions
repository secret before relying on the check.

ReviewGate runs when a pull request is opened, updated, reopened, or marked
ready for review. Repository owners, members, and collaborators can request a
fresh review by commenting `@reviewgate review` on an open pull request.



### Pydantic AI model presets

Product AI features use OpenRouter with two model presets configured in
`citeguild/settings.py`:

- `OPENROUTER_MODEL_FAST` defaults to `openai/gpt-5-nano`.
- `OPENROUTER_MODEL_SMART` defaults to `anthropic/claude-sonnet-4.5`.

Set `OPENROUTER_API_KEY`, then change either preset when your product needs a
different cost, latency, or capability tradeoff.



### Sentry performance monitoring

Sentry is configured for backend Django traces, trace-lifecycle profiling,
Redis/Django spans, structured logs, and error monitoring. For slow page-load
work, start with traces: inspect the relevant page transaction, find the
slowest database/cache/middleware spans, make the optimization, then compare
the same transaction across releases.

The generated sampler drops healthcheck, static, media, favicon, and robots
traffic. Keep `SENTRY_TRACES_SAMPLE_RATE=1.0` briefly for a clean baseline on
low-volume projects, then reduce it for higher-traffic production apps. Keep
`SENTRY_BACKGROUND_TRACES_SAMPLE_RATE` lower unless worker performance is the
focus.

Give an AI agent this starter prompt when you want it to create a Sentry
page-load dashboard in your Sentry account:

```text
Create or update a Sentry dashboard for CiteGuild page-load performance. Use the connected Sentry integration or an API token from the environment, never a committed token. Find the project, environment, releases, and transaction names. Create widgets for p50/p75/p95 transaction duration by transaction, slowest transactions, throughput, error rate, slowest DB/cache spans, and a focused homepage or primary landing page transaction if present. Return the dashboard URL, transaction names, filters, and baseline time range.
```


## Available Commands

| Command | Description |
| --- | --- |
| `make agent-services` | Start Compose-managed backing services only. |
| `make agent-services-down` | Stop Compose-managed backing services without deleting volumes. |
| `make terminal-setup` | Run `uv sync --locked`, `npm ci`, and `npm run build`. |
| `make terminal-web` | Apply migrations and run the ASGI app (UI, API, and MCP) on `DJANGO_RUNSERVER_HOST:DJANGO_RUNSERVER_PORT`. |
| `make terminal-worker` | Start the Django Q2 worker. |
| `make terminal-assets` | Watch Tailwind CSS and browser modules. |
| `make terminal-manage <command>` | Run a Django management command on the host. |
| `make terminal-makemigrations` | Run `makemigrations` on the host. |
| `make terminal-migrate` | Run migrations on the host. |
| `make terminal-test` | Run pytest on the host. |
| `make terminal-shell` | Open `shell_plus` with IPython on the host. |
| `make serve` | Start the full local Docker Compose app stack. |
| `make manage <command>` | Run a Django management command inside the backend Compose container. |
| `make makemigrations` | Run `makemigrations` inside the backend Compose container. |
| `make migrate` | Run migrations inside the backend Compose container. |
| `make test` | Run pytest inside the backend Compose container. |
| `make test-local-postgres` | Run checks against an existing `DATABASE_URL`, usually from PGSandbox MCP. |
| `make coverage-high-risk` | Run coverage on selected high-risk files with a configurable baseline. |
| `make type-check` | Run ty inside the locked project environment over the low-noise typed baseline. |
| `make pyscn-check` | Run the CI-friendly pyscn static analysis gate. |
| `make pyscn-analyze` | Generate a local `.pyscn/` structural analysis report. |
| `make restart-worker` | Recreate the local worker container. |
| `npm run build` | Build vendor assets, CSS, and browser modules. |
| `npm run watch` | Watch frontend sources during local development. |
| `npm run lint` | Run ESLint for browser modules and scripts. |
| `uv run pre-commit run --all-files --show-diff-on-failure` | Run Python, template, and formatting checks. |

## Testing And Quality

Use `docs/quality.md` as the source of truth for local verification and
touched-area checks.

Run the host-level local CI path:

```bash
make ci-local
```

This runs Python quality, the typed baseline, frontend lint/build, migration
drift checks, Django system checks, pytest, and high-risk coverage visibility.

Run targeted checks while developing:

```bash
make python-quality
make type-check
make frontend-check
make migrations-check
make django-check
make pytest-check -- apps/core -q
make api-fuzz
make coverage-high-risk
make mutation-high-risk -- 'apps.core.utils.*'
```

`make api-fuzz` runs Schemathesis property tests against the Django WSGI app,
generating authenticated requests from the Django Ninja OpenAPI schema and
checking response and schema conformance without starting a live server.

`make coverage-high-risk` starts with `COVERAGE_FAIL_UNDER=0` so new projects
get coverage visibility without a fake baseline. Raise the threshold once your
project has meaningful tests around its own risky paths.

`make mutation-high-risk` uses mutmut to check whether tests detect broken logic
in the configured high-risk files. It is an opt-in, slower quality exercise
rather than part of `make ci-local` or per-commit CI. Inspect surviving mutants
with `make mutation-results`; see `docs/quality.md` for the workflow and
platform requirements.

The older direct-command path is still useful when debugging a specific tool:

```bash
make terminal-manage check
make terminal-test
npm run lint
npm run build
uv run pre-commit run --all-files --show-diff-on-failure
make pyscn-check
```

Run focused pytest checks:

```bash
make terminal-test apps/core/tests/test_api_keys.py
make terminal-test -- -k keyword -q
```

Check migrations before shipping model changes:

```bash
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate
```

CI runs three parallel jobs when generated with CI enabled:

- Python quality: locked uv sync and `make python-quality`.
- Frontend: `npm ci` and `make frontend-check`.
- Pytest: Postgres service, `make migrations-check`, `make django-check`, and
  `make coverage-high-risk COVERAGE_FAIL_UNDER=0 -- -q`.

Pytest uses `citeguild.test_settings`, which keeps cache,
media, email, and Django Q2 state isolated while preserving the PostgreSQL
migration path in CI.

Hypothesis is included for property-based tests and runs through the same pytest
commands. The generated API-key tests demonstrate a fast round-trip invariant.
Read `.agents/skills/property-based-testing/SKILL.md` before designing
strategies or adding database-backed properties.

## Deployment

Production deployments should set:

```env
ENVIRONMENT=prod
DEBUG=False
SECRET_KEY=<strong random value>
SITE_URL=https://your-domain.example
```

When `ENVIRONMENT=prod`, Django enables HTTPS redirects, secure cookies, HSTS,
and trusted proxy HTTPS detection through `X-Forwarded-Proto` by default.
Override security settings only when your edge proxy and domain setup require a
different value.

### Shared Docker image

`deployment/Dockerfile` builds one image for both web and worker roles:

```bash
docker build -f deployment/Dockerfile -t citeguild:dev .
```

At runtime, `deployment/entrypoint.sh` chooses the process from
`APP_PROCESS_TYPE`:

```bash
docker run --env-file .env -e APP_PROCESS_TYPE=server -p 8000:80 citeguild:dev
docker run --env-file .env -e APP_PROCESS_TYPE=worker citeguild:dev
```

The server role waits for the database, runs `collectstatic`, applies
migrations unless Fly.io release commands already handled them, and starts
Gunicorn. The worker role starts Django Q2.

### Production Docker Compose

`docker-compose-prod.yml` runs Postgres, Redis, authenticated Qdrant, web, and workers:

```bash
cp .env.example .env
docker build -f deployment/Dockerfile -t citeguild:dev .
export APP_IMAGE=ghcr.io/lvtd-llc/citeguild:<40-character-git-sha>
docker compose -f docker-compose-prod.yml -p "citeguild" up --detach --remove-orphans
```

`APP_IMAGE` is required and must name an immutable git-SHA image built by GitHub
Actions. Floating tags are intentionally rejected.

Expose the backend container through your reverse proxy and point it at port
`80` inside the container.

### Fly.io

This repo includes `fly.toml`. It builds `deployment/Dockerfile`, defines
separate `web` and `worker` process groups, runs migrations as a Fly release
command, and exposes only the web process.

Quick path:

```bash
fly auth login
fly apps create citeguild
fly secrets set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
fly deploy
```

Before deploying:

- Attach or configure Postgres and set `DATABASE_URL`.
- Create or configure Redis and set `REDIS_URL`.
- Update `app`, `primary_region`, and `SITE_URL` in `fly.toml` if you choose a
  different app name or region.

- Read the generated Fly deployment guide in the docs app for the full
  checklist.


### CapRover

The Python package slug is `citeguild`. The CapRover app slug is separate and the generated deploy workflow sets `CAPROVER_APP_NAME=citeguild`.

Create five CapRover apps:

- `citeguild`
- `citeguild-workers`
- `citeguild-postgres`
- `citeguild-redis`
- `citeguild-qdrant`

Runtime app settings:

- Set `APP_PROCESS_TYPE=server` on `citeguild`.
- Set `APP_PROCESS_TYPE=worker` on `citeguild-workers`.
- Put the rest of the production `.env` values on both web and worker apps.

GitHub Actions settings:

- Repository variable: `WORKERS_APP_PROCESS_TYPE=worker`.
- Repository secrets: `CAPROVER_SERVER`, `APP_TOKEN`, and `WORKERS_APP_TOKEN`.

On push to `main`, `.github/workflows/deploy.yml` builds one GHCR image and
deploys its git-SHA tag to both CapRover apps. The complete topology, release,
health, persistence, and rollback contract is in
`docs/operations/caprover-topology.md`.
The evidence-linked launch checklist, named ownership, incident paths, metrics
cadence, and current launch risks are in
`docs/operations/launch-readiness.md`.

### Render

`render.yaml` defines a Render blueprint with:

- A web service for Django.
- A worker service implemented as a web service process for free-plan
  compatibility.
- A Render Key Value Redis service.
- A Render PostgreSQL database.
- An `app-env` environment variable group.

Deploy by connecting the repository to Render and using the blueprint. Review
the generated env group before first deploy, especially `SECRET_KEY`,
`SITE_URL`, email settings, Stripe keys, Sentry DSN, and OpenRouter key.



### Manual process deployment

Use Docker when possible. If you deploy directly to a VM, run at least these
processes:

```bash
uv sync --locked --no-dev --no-install-project
npm ci
npm run build
uv run --no-sync python manage.py collectstatic --noinput
uv run --no-sync python manage.py migrate --noinput

uv run --no-sync gunicorn citeguild.asgi:application --bind 0.0.0.0:80 --workers 3 --worker-class uvicorn_worker.UvicornWorker

uv run --no-sync python manage.py qcluster
```

You also need managed Postgres, Redis, a process supervisor, HTTPS termination,
static/media handling, logs, backups, and a rollback strategy.


## Stripe Setup

This app uses Stripe Checkout for purchases and the Billing Portal for
subscription management.

Configure these variables:

```env
STRIPE_SECRET_KEY=
STRIPE_CONTEXT=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID_MONTHLY=
WEBHOOK_UUID=
```

Create a webhook endpoint in Stripe:

```text
https://<your-domain>/stripe/webhook/<WEBHOOK_UUID>/
```

If `WEBHOOK_UUID` is blank, use:

```text
https://<your-domain>/stripe/webhook/
```

Forward webhooks locally with the Stripe CLI container:

```bash
docker compose -f docker-compose-local.yml run --rm stripe listen --forward-to http://backend:8000/stripe/webhook/${WEBHOOK_UUID}/
docker compose -f docker-compose-local.yml run --rm stripe trigger customer.subscription.created
```



## Chatwoot Support Chat

Chatwoot support chat is disabled until both runtime env vars are set on the
Django web app:

```env
CHATWOOT_BASE_URL=
CHATWOOT_WEBSITE_TOKEN=
```

For self-hosted Chatwoot, use your own base URL, for example
`https://chatwoot.yourdomain.com`. For Chatwoot Cloud, use the base URL from
Chatwoot's snippet, commonly `https://app.chatwoot.com`.

Recommended for authenticated apps: enable Identity Validation for that Website
inbox and set:

```env
CHATWOOT_HMAC_SECRET=
```


## Troubleshooting

### Database connection refused

Check that Postgres is running and that `.env` points at the right host and
port.

```bash
docker compose -f docker-compose-local.yml ps db
pg_isready -h "$POSTGRES_HOST" -p "$POSTGRES_PORT"
```

For host-run commands with Compose services, `POSTGRES_HOST` should usually be
`localhost`. For commands running inside Docker Compose, it should usually be
`db`.

### Redis connection errors

Redis backs the default cache, Django Q2, and the healthcheck endpoint.

```bash
docker compose -f docker-compose-local.yml ps redis
make terminal-manage shell -c "from django.core.cache import cache; cache.set('ping', 'pong', 10); print(cache.get('ping'))"
```

Leave `REDIS_URL` blank when using split `REDIS_HOST`, `REDIS_PORT`,
`REDIS_PASSWORD`, and `REDIS_DB` values. A non-empty `REDIS_URL` takes
precedence.

### Migrations are pending

Run:

```bash
uv run python manage.py makemigrations
uv run python manage.py migrate
```

Run `makemigrations` without app labels so all generated apps are considered.

### Static assets are missing

Rebuild frontend assets:

```bash
npm ci
npm run build
uv run python manage.py collectstatic --noinput
```

During development, keep the watcher running:

```bash
make terminal-assets
```

### Passkeys fail locally

Local passkeys depend on the browser, origin, and allauth WebAuthn settings.
Use `http://localhost:8000` or keep `SITE_URL` aligned with your chosen local
port. In debug mode, `MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN` allows local HTTP.
In production, use HTTPS.

### Email confirmations do not arrive

In local development, prefer console email or Mailhog:

```env
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

or open Mailhog at `http://localhost:8025` when using Compose. In production,
set `MAILGUN_API_KEY`, `MAILGUN_SENDER_DOMAIN`, `DEFAULT_FROM_EMAIL`, and
`SERVER_EMAIL`.


### MCP client cannot connect

Check the exact URL first:

```text
https://<your-domain>/mcp/
```

Common issues:

- Missing trailing slash in clients that do not follow redirects.
- OAuth client did not request or validate the MCP resource.
- API key was sent in a query string instead of a header.
- Production server is running WSGI instead of ASGI. MCP requires the generated
  ASGI command with `uvicorn_worker.UvicornWorker`.



### Stripe webhooks are ignored

Verify:

- `STRIPE_WEBHOOK_SECRET` matches the endpoint secret from Stripe.
- `WEBHOOK_UUID` in the endpoint URL matches the app env var.
- The webhook route is reachable from Stripe or the Stripe CLI.
- The event type is one of the subscription and checkout events handled by the
  app.



### Sentry is silent

Verify:

- `SENTRY_DSN` is set.
- `SENTRY_ENABLED=True`.
- `ENVIRONMENT=prod`, or you intentionally enable Sentry in another
  environment.
- `SENTRY_TRACES_SAMPLE_RATE` and related sample rates are not `0`.


## Contributing

Before changing code, read:

- `AGENTS.md` for repo workflow, test, security, and architecture rules.
- `DESIGN.md` before UI changes.
- Relevant `.agents/skills/*/SKILL.md` files for the area you are touching.

Recommended change loop:

```bash
make terminal-manage check
make terminal-test
npm run lint
npm run build
uv run pre-commit run --all-files --show-diff-on-failure
```

Keep generated docs, env examples, tests, and deployment files aligned with
runtime behavior. Do not commit secrets, local machine paths, or tool-specific
agent instructions that should live in `AGENTS.md` or `.agents/skills/`.

## License

This project is generated with an MIT license in `package.json`. Replace or
expand this section if your product uses a different license.
