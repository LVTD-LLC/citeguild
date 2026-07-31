# AGENTS.md - CiteGuild

This is a generated Django SaaS app. Keep changes small, tested, and aligned
with the app structure that Cookiecutter created.

## Agent Contract

- Treat this file as the canonical guidance for coding agents in this project.
- Keep guidance tool-neutral. Do not add IDE-specific, vendor-specific, or
  single-agent instruction files. Repo-scoped Agent Skills may live under
  `.agents/skills/` when they describe portable workflows.
- Add nested `AGENTS.md` files only when a subdirectory needs scoped guidance.
- Keep personal preferences and machine-local paths out of committed
  instructions.
- Store secrets in environment variables or `.env`; never print, log, hard-code,
  or commit API keys.
- Treat log fields as a public monitoring contract: use stable dotted
  `event.name` values, scalar `extra` fields, binary `success`/`failure`
  outcomes, and never include credentials, bodies, email addresses, arbitrary
  metadata, task arguments/results, or user-owned content.

## Project Map

- `apps/core/` - shared domain logic, auth-adjacent flows, profiles, forms,
  utilities, background tasks, and common tests.
- `apps/pages/` - landing, pricing, legal, and other static or marketing pages,
  plus repository-tracked content such as blog and docs when generated.
- `apps/api/` - Django Ninja API schemas, auth, services, and routers.
- `apps/pages/posts/` - Markdown-backed public blog posts.
- `apps/pages/content/docs/` - authenticated Markdown documentation content.
- `apps/mcp_server/` - hosted MCP tools for agent integrations.
- `apps/core/agents/` - PydanticAI model helpers and agent code.
- `citeguild/settings.py` - environment-driven Django
  settings.
- `citeguild/test_settings.py` - pytest-only settings
  that keep cache, media, email, and Django Q2 state local to test runs.
- `citeguild/urls.py` - top-level URL routing.
- `conftest.py` - shared pytest fixtures, including the guarded pgsandbox
  database settings hook used by `make test-local-postgres` so pytest-django
  reuses an existing PGSandbox database with `--reuse-db`.
- `frontend/templates/` - Django templates.
- `frontend/src/js/` - small browser modules copied to `frontend/static/js/`.
- `frontend/src/styles/` - Tailwind CSS and global styles.
- `frontend/static/` - Django-served static asset output.
- `docs/quality.md` - local CI path and touched-area quality command matrix.
- `docs/code-tours/` - concise flow tours for common generated-project
  architecture and verification paths.
- `docs/agent-task-templates.md` - task-framing templates for common Django,
  API, frontend, background job, dependency, and agent-guidance changes.
- `docs/agent-evals/seed-tasks.md` - seed tasks for repeatable agent evaluation
  and regression mining.
- `DESIGN.md` - design-system source of truth for humans and AI tools.
- `.agents/skills/` - bundled cross-agent skills for project-specific workflows.

## Workflow

1. Read `README.md`, `DESIGN.md`, `docs/quality.md`, and the files around the
   requested change.
2. Create a branch before implementation when working in git.
3. Put code in the smallest appropriate app or frontend module.
4. Add or update tests for feature work, bug fixes, and risky refactors.
5. Use `docs/quality.md` to run targeted checks first, then broader checks
   before finishing.
6. Update `CHANGELOG.md` under the current ISO date heading (`## YYYY-MM-DD`)
   for user-visible behavior changes.

## Repo-Scoped Skills

- `.agents/skills/caprover-deployment/SKILL.md` - portable CapRover deployment
  workflow for coding agents that support the Agent Skills convention, and
  readable fallback instructions for agents that do not.
- `.agents/skills/local-terminal-development/SKILL.md` - local agent
  development workflow for running Django, Django Q2, tests, and frontend
  assets from terminal commands, optionally backed by Compose services.
- `.agents/skills/alpinejs-django/SKILL.md` - Alpine.js patterns for
  Django-rendered templates, including coordination with HTMX partial updates.
- `.agents/skills/django-ninja/SKILL.md` - Django Ninja endpoint, schema,
  router, authentication, OpenAPI, and API test guidance.
- `.agents/skills/django-q2/SKILL.md` - Django Q2 background task, schedule,
  worker, Redis broker, and ORM broker guidance.
- `.agents/skills/django-htmx/SKILL.md` - portable Django/HTMX patterns for
  server-rendered partial updates, forms, swaps, events, and Alpine.js
  coordination.
- `.agents/skills/pgsandbox-testing/SKILL.md` - disposable local Postgres
  testing with PGSandbox MCP and this project's `DATABASE_URL` test target.
- `.agents/skills/frontend-ui-quality/SKILL.md` - portable UI quality workflow
  for Django templates, Tailwind CSS, responsive behavior, accessibility,
  motion, and generated-project design-system alignment.
- `.agents/skills/agent-reliability/SKILL.md` - reliability workflow for
  agent-driven changes, including task framing, high-risk behavior kernels,
  parity tests, coverage visibility, type-check rollout, and eval seeds.
- `.agents/skills/property-based-testing/SKILL.md` - Hypothesis workflow for
  invariants, round trips, parsers, state transitions, and Django database
  properties.

## Commands

Agent local development with Compose-backed services:

```bash
cp .env.agent.example .env
make agent-services
make terminal-setup
uv run python manage.py makemigrations
make terminal-migrate
make terminal-manage check
make terminal-web
```

Terminal local development without Docker:

```bash
cp .env.terminal.example .env
make terminal-setup
uv run python manage.py makemigrations
make terminal-migrate
make terminal-manage check
make terminal-web
```

Run these in separate terminals when the web app needs background jobs and live
frontend assets:

```bash
make terminal-worker
make terminal-assets
```

Local Docker-backed development:

```bash
make serve
make manage check
make test
```

When running multiple generated projects or same-slug clones on one machine,
override local ports and, for same directory names, `COMPOSE_PROJECT_NAME`:

```bash
LOCAL_WEB_PORT=8001 LOCAL_POSTGRES_PORT=55433 LOCAL_REDIS_PORT=56380 make agent-services
DJANGO_RUNSERVER_PORT=8001 SITE_URL=http://localhost:8001 POSTGRES_PORT=55433 REDIS_PORT=56380 make terminal-web
COMPOSE_PROJECT_NAME=citeguild-agent-a LOCAL_WEB_PORT=8002 LOCAL_POSTGRES_PORT=55434 LOCAL_REDIS_PORT=56381 LOCAL_MAILHOG_SMTP_PORT=11025 LOCAL_MAILHOG_UI_PORT=18025 make serve
```

Quality checks:

```bash
make ci-local
make python-quality
make frontend-check
make migrations-check
make django-check
make coverage-high-risk -- -q
make mutation-high-risk -- 'apps.core.utils.*'
```

Targeted tests:

```bash
make test apps/core/tests/test_example.py
make test apps/core/tests/test_example.py::test_specific_case
make test -- -k keyword -q
make terminal-test apps/core/tests/test_example.py
make terminal-test apps/core/tests/test_example.py::test_specific_case
make terminal-test -- -k keyword -q
```

Disposable local Postgres tests:

```bash
DATABASE_URL="<pgsandbox connection string>" make test-local-postgres
DATABASE_URL="<pgsandbox connection string>" make test-local-postgres -- -k keyword -q
```

Host-level checks used by CI:

```bash
make python-quality
make frontend-check
make migrations-check
make django-check
make coverage-high-risk COVERAGE_FAIL_UNDER=0 -- -q
```

Mutation testing is an opt-in strength check, not part of the default local or
per-commit CI path. Run it after focused pytest checks for high-risk behavior
kernels, then inspect survivors with `make mutation-results`.

Frontend:

```bash
npm ci
npm run build
npm run lint
```

## Implementation Rules

- Use Django conventions and the existing app boundaries before creating new
  abstractions.
- Keep business logic out of templates; use views, forms, services, model
  methods, or template tags as appropriate.
- Change models first, then generate migrations with `make makemigrations`
  inside Docker or `make terminal-makemigrations` without Docker. Inspect
  generated migrations before committing them.
- Do not hand-edit historical migrations unless explicitly required.
- Keep auth flows compatible with `django-allauth`, including email, passkey,
  MFA, signup gating, and password reset flows.
- Keep light and dark mode readable when changing templates.
- Use HTMX for server-rendered partial updates and Alpine.js for local browser
  state. Keep plain browser modules in `frontend/src/js/` for shared DOM
  behavior.
- Read `.agents/skills/frontend-ui-quality/SKILL.md` before changing Django
  templates, Tailwind CSS, layout, responsive behavior, motion, frontend copy,
  or UI component states.
- Read `.agents/skills/agent-reliability/SKILL.md` before broad agent-driven
  changes, CI/quality workflow updates, test architecture changes, multi-surface
  behavior changes, or agent-evaluation work.
- Use `docs/agent-task-templates.md` to frame repeatable tasks and
  `docs/code-tours/README.md` to orient before changing established flows.
- Use `docs/agent-evals/seed-tasks.md` when evaluating agents or mining
  repeated agent failures back into tests, docs, or workflow guardrails.
- Read `.agents/skills/alpinejs-django/SKILL.md` before adding or changing
  Alpine.js behavior in Django templates.
- Read `.agents/skills/django-htmx/SKILL.md` before adding or changing HTMX
  interactions.
- Keep styles aligned with `DESIGN.md` and Tailwind conventions.
- Keep Stripe webhook handling idempotent and defensive. Billing code belongs in
  `apps/core/stripe_webhooks.py` and related core/API paths.
- For PydanticAI work, prefer typed dependencies, typed outputs, stable
  constructor `instructions`, and small dynamic `@agent.instructions`
  functions.
- AI model presets live in `settings.AI_MODELS`; values must be OpenRouter
  model IDs, such as `anthropic/claude-sonnet-4.5`.
- Read `.agents/skills/building-pydantic-ai-agents/SKILL.md` before implementing
  Pydantic AI agents, tools, streaming, or agent tests.
- Read `.agents/skills/pydantic-ai-harness/SKILL.md` before adding optional
  Pydantic AI Harness capabilities.
- For MCP work, verify both `/mcp/` and `GET /api/user` authentication paths.
  Never expose user API keys in logs or committed files.
- For CapRover deploys or deploy fixes, read `.agents/skills/caprover-deployment/SKILL.md` first.
- Before running the generated app locally for agent work, read
  `.agents/skills/local-terminal-development/SKILL.md` first.
- For pre-PR verification and touched-area command choices, use
  `docs/quality.md`.
- For Django Ninja API endpoints, schemas, routers, authentication, OpenAPI
  docs, or API tests, read `.agents/skills/django-ninja/SKILL.md` first.
- For Django Q2 background tasks, scheduled jobs, worker changes, or broker
  changes, read `.agents/skills/django-q2/SKILL.md` first.
- For disposable local Postgres testing through MCP, read
  `.agents/skills/pgsandbox-testing/SKILL.md` first. Create the sandbox with the
  MCP tool, run checks with `DATABASE_URL`, then delete the sandbox.
- For test-suite speed, profiling, CI split changes, parallel execution,
  fixture/data refactors, or test mocks, read the matching Django test skill
  under `.agents/skills/` before changing code or workflow files.
- For invariants, round trips, parsers, normalizers, state transitions, or broad
  input spaces, read `.agents/skills/property-based-testing/SKILL.md` before
  adding Hypothesis tests.

## Agent Guidance

- This file ships regardless of optional product features. Optional focused
  skills under `.agents/skills/` may be removed when their corresponding
  runtime feature is disabled.
- Keep this file concise enough for agents to read before every task.
- Prefer exact commands and file paths over generic "follow best practices"
  instructions.
- Update this file when project structure, test commands, security constraints,
  or major workflows change.
- Content-specific writing guidance lives in `apps/pages/content/AGENTS.md`.
- The hosted app serves runtime MCP setup instructions at `/AGENTS.md`; keep
  those instructions tool-neutral and secret-safe.
