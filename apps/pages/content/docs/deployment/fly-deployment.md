---
title: Deploying CiteGuild to Fly.io
description: Learn how to deploy CiteGuild on Fly.io.
keywords: CiteGuild, deployment, fly.io, fly, django
author: LVTD LLC
---

This project includes a `fly.toml` that deploys the existing Docker server image to Fly.io. It defines a public `web` process, a private `worker` process for `django-q2`, a migration release command, and a health check on `/api/healthcheck`.

## What the Fly config does

- Builds `deployment/Dockerfile`.
- Runs `uv run --no-sync python manage.py migrate --noinput` as a Fly release command before new Machines are promoted.
- Starts the Django web process with `sh deployment/entrypoint.sh -s`.
- Starts the background worker with `sh deployment/entrypoint.sh -w`.
- Exposes only the `web` process through Fly's HTTP service on internal port `8080`.
- Keeps one web Machine warm by default with `min_machines_running = 1`.

## Prerequisites

- Install and log in to `flyctl`.
- Commit `uv.lock`. It should be generated automatically when Cookiecutter creates the project.
- Choose an app name. Fly app names are globally unique and must use DNS-safe characters. The generated config uses `citeguild` by default.
- Choose a primary region close to your users and your databases. Update `primary_region` in `fly.toml`.

## Create the app

```bash
fly auth login
fly apps create citeguild
```

If that app name is taken, create a different one and update these values in `fly.toml`:

- `app`
- `SITE_URL`

## Configure Postgres

The generated settings prefer `DATABASE_URL` when it is present. Use Fly.io Managed Postgres, Fly Postgres, or an external Postgres provider, then set `DATABASE_URL` on the app.

With Fly Postgres, attaching the database sets `DATABASE_URL` for the app:

```bash
fly postgres create --name citeguild-db
fly postgres attach citeguild-db --app citeguild
```

For any external Postgres provider:

```bash
fly secrets set DATABASE_URL="postgres://USER:PASSWORD@HOST:5432/DBNAME"
```

## Configure Redis

Redis backs Django's default cache and the `django-q2` worker queue. Fly's managed Redis path uses Upstash.

```bash
fly redis create --name citeguild-redis
fly redis status citeguild-redis
fly secrets set REDIS_URL="redis://default:PASSWORD@HOST"
```

Use the private Redis URL from `fly redis status` when available. Keep `REDIS_DB=0` for Upstash.

## Configure secrets

Set at least the Django secret key. Add optional provider secrets only for the features you use.

```bash
fly secrets set SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
```

Common optional secrets:

```bash
fly secrets set MAILGUN_API_KEY="..."
fly secrets set GITHUB_CLIENT_ID="..." GITHUB_CLIENT_SECRET="..."
```

For S3-compatible media storage, also set:

```bash
fly secrets set AWS_S3_ENDPOINT_URL="..." AWS_ACCESS_KEY_ID="..." AWS_SECRET_ACCESS_KEY="..."
```

For Stripe, also set:

```bash
fly secrets set STRIPE_SECRET_KEY="..." STRIPE_WEBHOOK_SECRET="..."
```

Do not import the full local `.env` file into Fly without reviewing it first. The local file includes Docker hostnames such as `db` and `redis` that are not valid for Fly-hosted databases.

## Deploy

```bash
fly deploy
fly apps open
```

The first deploy creates Machines for the `web` and `worker` process groups. To change process counts:

```bash
fly scale count web=1 worker=1
```

Scale `worker=0` only if you do not need background tasks.

## Operational notes

- The server entrypoint uses `$PORT` when present and falls back to port `80` for Docker Compose and CapRover deployments.
- On Fly.io, migrations run through `fly.toml`'s release command, so the server entrypoint skips its normal startup migration step when `FLY_APP_NAME` is present.
- `SITE_URL` must match the public HTTPS URL for the app, for example `https://citeguild.fly.dev`.
- Fly secrets are runtime environment variables. They are not available during Docker image build.
- If deploys time out during the first image build, rerun with `fly deploy --wait-timeout=10m`.
