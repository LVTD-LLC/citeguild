---
name: local-terminal-development
description: "Use when running, testing, or debugging the generated Django SaaS app from host terminal commands, optionally with Docker Compose backing services."
---

# Local Terminal Development

Use this workflow when an agent needs to run the generated Django app, tests,
Django Q2 worker, or frontend asset watcher from host terminal commands. Prefer
the Compose-backed service path when a task needs real Postgres or Redis and
the fully terminal path when those services already run locally.

## Choose A Path

- Use `.env.agent.example` plus `make agent-services` when Docker Compose
  should provide Postgres, Redis, Mailhog, and optional local service emulators
  while Django and tests run on the host.
- Use `.env.terminal.example` when Postgres and Redis already run directly on
  the machine.
- Use full `make serve` only for full-stack Docker verification or when testing
  behavior that depends on the Docker web, worker, frontend, Mailhog, Minio,
  MJML, or Stripe CLI containers together.

## Requirements

- Python and uv compatible with the project's `pyproject.toml`.
- Node.js compatible with `.nvmrc`.
- A PostgreSQL service reachable through `.env` values or `DATABASE_URL`.
- A Redis service reachable through `REDIS_URL` or `REDIS_HOST` settings.

Do not print or commit `.env` contents.

## Agent Services First Run

Use this when an agent needs isolated services for this repo:

```bash
cp .env.agent.example .env
make agent-services
uv sync --locked
npm ci
npm run build
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py check
```

This starts only backing services with Compose. Django, pytest, the worker, and
the asset watcher still run from the host terminal.

## Terminal-Only First Run

Use this when Postgres and Redis already run directly on the host:

```bash
cp .env.terminal.example .env
uv sync --locked
npm ci
npm run build
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py check
```

Run `makemigrations` without app labels so Django detects model changes across
all apps before feature work.

## Multi-Repo Port Isolation

Generated projects default to common local ports. When multiple agents run
multiple generated projects on one machine, choose a unique port set per repo:

```bash
LOCAL_WEB_PORT=8001 LOCAL_POSTGRES_PORT=55433 LOCAL_REDIS_PORT=56380 make agent-services
DJANGO_RUNSERVER_PORT=8001 SITE_URL=http://localhost:8001 POSTGRES_PORT=55433 REDIS_PORT=56380 make terminal-web
```

If two clones have the same directory name or generated slug, also set a unique
Compose namespace and Redis prefixes:

```bash
COMPOSE_PROJECT_NAME=<project-slug>-agent-a make agent-services
LOCAL_INSTANCE_ID=<project-slug>-agent-a CACHE_KEY_PREFIX=<project-slug>-agent-a Q_CLUSTER_NAME=<project-slug>-agent-a-q make terminal-worker
```

## Run the App

Use separate terminal sessions so each long-running process has readable logs:

```bash
make terminal-web
make terminal-worker
make terminal-assets
```

The web process runs migrations and then starts the project's ASGI application
on `http://localhost:8000`, so Django UI, API, OAuth discovery, and MCP routes
are all available from the same local server. The worker process starts Django
Q2. The asset watcher keeps Tailwind CSS and browser modules current while
templates, CSS, and JavaScript change.

## Common Commands

```bash
make terminal-manage check
make terminal-makemigrations
make terminal-migrate
make terminal-test
make terminal-test apps/core/tests/test_example.py
make terminal-test -- -k keyword -q
make terminal-shell
```

## Troubleshooting

- If Docker reports a port is already allocated, rerun with unique
  `LOCAL_WEB_PORT`, `LOCAL_POSTGRES_PORT`, `LOCAL_REDIS_PORT`,
  `LOCAL_MAILHOG_SMTP_PORT`, and `LOCAL_MAILHOG_UI_PORT` values. Keep `.env`
  connection values aligned with those ports.
- If Django cannot connect to Postgres, verify `.env` has `POSTGRES_HOST`,
  `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`
  values that match the selected path, or set `DATABASE_URL`.
- If Redis checks fail, prefer `REDIS_URL` for a single unambiguous connection
  string only when connecting to an external Redis service. For Compose-backed
  services, keep `REDIS_URL` blank and align `REDIS_PORT` with
  `LOCAL_REDIS_PORT`.
- If signup or password emails fail locally, keep
  `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` so Django logs
  emails to the terminal instead of trying Mailhog.
- If styles are stale, run `npm run build` once or keep `make terminal-assets`
  running while editing frontend files.
