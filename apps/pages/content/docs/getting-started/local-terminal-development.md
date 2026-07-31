---
title: Local Agent And Terminal Development
description: Run CiteGuild from host terminal commands, with or without Compose-backed services.
---

# Local Agent And Terminal Development

Use this workflow when you want normal terminal processes for Django, tests,
workers, and frontend assets. AI coding agents should usually run commands on
the host and use Compose only for backing services when they need real Postgres
or Redis.

## Requirements

- Python version matching `pyproject.toml` `requires-python`
- uv
- Node.js version matching `.nvmrc`
- PostgreSQL reachable through `.env` values or a full `DATABASE_URL`
- Redis reachable through `.env` values or a full `REDIS_URL`

## Agent services first run

Use this when an agent should run Django and tests on the host while Docker
Compose manages Postgres, Redis, Mailhog, and optional local emulators:

```bash
cp .env.agent.example .env
make agent-services
make terminal-setup
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py check
```

Run `makemigrations` without app labels so Django detects model changes across
all generated apps.

## Terminal-only first run

Copy the terminal-specific environment defaults:

```bash
cp .env.terminal.example .env
```

Create the local PostgreSQL role and database named in `.env`, or edit
`DATABASE_URL` to point at your existing local database.

Install dependencies and build assets:

```bash
make terminal-setup
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py check
```

Run `makemigrations` without app labels so Django detects model changes across
all generated apps.

## Multi-repo agent isolation

Generated projects default to common local ports. When multiple agents run
multiple generated projects at once, choose a unique port set per repo:

```bash
LOCAL_WEB_PORT=8001 LOCAL_POSTGRES_PORT=55433 LOCAL_REDIS_PORT=56380 make agent-services
DJANGO_RUNSERVER_PORT=8001 SITE_URL=http://localhost:8001 POSTGRES_PORT=55433 REDIS_PORT=56380 make terminal-web
```

If two clones have the same directory name or generated project slug, also set
a unique Compose namespace and Redis prefixes:

```bash
COMPOSE_PROJECT_NAME=citeguild-agent-a make agent-services
LOCAL_INSTANCE_ID=citeguild-agent-a CACHE_KEY_PREFIX=citeguild-agent-a Q_CLUSTER_NAME=citeguild-agent-a-q make terminal-worker
```

## Run processes

Open separate terminal sessions:

```bash
make terminal-web
make terminal-worker
make terminal-assets
```

`terminal-web` runs migrations and starts Django at `http://localhost:8000`.
`terminal-worker` starts Django Q2. `terminal-assets` watches Tailwind CSS and
browser modules.

## Useful checks

```bash
make terminal-manage check
make terminal-test
make terminal-test apps/core/tests/test_example.py
make terminal-test -- -k keyword -q
```

Use the Docker-backed `make serve` workflow only when you want Compose to manage
Postgres, Redis, Mailhog, workers, the Django web process, and the frontend
watcher together. Override `LOCAL_WEB_PORT`, `LOCAL_POSTGRES_PORT`,
`LOCAL_REDIS_PORT`, `LOCAL_MAILHOG_SMTP_PORT`, `LOCAL_MAILHOG_UI_PORT`, and any
optional emulator ports when more than one generated project runs on the same
machine.
