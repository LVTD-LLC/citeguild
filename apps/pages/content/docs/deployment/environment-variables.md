---
title: Environment Variables
description: Complete guide to configuring CiteGuild environment variables.
keywords: CiteGuild, environment variables, configuration, API keys
author: LVTD LLC
---

This guide covers all environment variables needed to configure CiteGuild.

## Runtime settings

**PYTHON_VERSION**
- Python runtime version for Render deployments
- Default in `render.yaml`: `3.14.5`

**NODE_VERSION**
- Node.js runtime version for frontend builds on Render
- Default in `render.yaml`: `24.15.0`

**PORT**
- Port for the Gunicorn web process to bind to
- Defaults to `80` in Docker-based deployments
- Set to `8080` in `fly.toml` to match Fly.io's default internal HTTP service port

**APP_PROCESS_TYPE**
- Container role for the shared deployment image
- Values: `server` or `worker`
- Required for production deployment containers
- Set to `server` for the web container and `worker` for the background workers container or CapRover workers app
- In development without `ENVIRONMENT=prod`, the entrypoint defaults to `server` when this is unset

**APP_IMAGE**
- Optional Docker image used by `docker-compose-prod.yml` for both backend and workers
- Example: `ghcr.io/<owner>/<repository>:latest`
- Leave empty to use the compose file's local `citeguild:latest` fallback

**LOCAL_WEB_PORT**, **LOCAL_POSTGRES_PORT**, **LOCAL_REDIS_PORT**, **LOCAL_MAILHOG_SMTP_PORT**, **LOCAL_MAILHOG_UI_PORT**
- Host ports published by `docker-compose-local.yml`
- Defaults: `8000`, `5432`, `6379`, `1025`, and `8025`
- Change these when multiple generated projects run on one machine
- Keep `SITE_URL`, `POSTGRES_PORT`, `REDIS_PORT`, and email settings aligned when host-run Django connects to Compose-published services. Leave `REDIS_URL` blank unless you intentionally want one full external Redis URL to override the individual Redis values

**LOCAL_MJML_PORT**
- Host port for the local MJML service in `docker-compose-local.yml`
- Default: `15500`
- Keep `MJML_URL` aligned when host-run Django uses the Compose MJML service

**LOCAL_MINIO_API_PORT**, **LOCAL_MINIO_CONSOLE_PORT**
- Host ports for Minio in `docker-compose-local.yml`
- Defaults: `9000` and `9001`
- Keep `AWS_S3_ENDPOINT_URL` aligned when host-run Django uses Compose Minio

**COMPOSE_PROJECT_NAME**
- Optional Docker Compose namespace
- Set this before running Compose when two clones have the same directory name or generated project slug
- Example: `COMPOSE_PROJECT_NAME=citeguild-agent-a make agent-services`

**CAPROVER_APP_NAME**
- GitHub Actions workflow environment variable used by `.github/workflows/deploy.yml`
- Generated from the Cookiecutter `caprover_app_name` value
- Default in the generated workflow: `citeguild`
- Separate from the Python package slug `citeguild`
- Workers deploy to `citeguild-workers`

**WORKERS_APP_PROCESS_TYPE**
- GitHub Actions repository variable used by `.github/workflows/deploy.yml`
- Must be set to `worker` before the workflow deploys the CapRover workers app
- This is separate from the runtime `APP_PROCESS_TYPE` value that must be set on the CapRover workers app

## Required variables

These variables are essential for CiteGuild to function:

### Core Django settings

**ENVIRONMENT**
- Environment mode for the application
- Values: `dev` or `prod`
- Set to `prod` for production deployments
- Set to `dev` for local development

**SECRET_KEY**
- Secret key for Django security features
- Must be kept confidential in production
- Generate one with: `python -c "import secrets; print(secrets.token_urlsafe(50))"`

**DEBUG**
- Set to `False` in production
- Set to `True` only for local development
- Never deploy to production with DEBUG=True

**SITE_URL**
- Full URL where your CiteGuild instance is accessible
- Example: `https://yourdomain.com`
- Used for generating absolute URLs in emails, notifications, canonical tags, Open Graph tags, `robots.txt`, and `sitemap.xml`

**ALLOW_SIGNUPS**
- Set to `False` to pause new account creation
- Defaults to `True`
- Existing users can still log in while signups are paused

**ALLOWED_HOSTS**
- Comma-separated list of domains that can access your application
- Example: `yourdomain.com,www.yourdomain.com`
- Use `*` for testing only (not secure for production)

**SECURE_SSL_REDIRECT**
- Redirect HTTP requests to HTTPS
- Defaults to `True` when `ENVIRONMENT=prod`, otherwise `False`
- Set to `False` only when your edge proxy already enforces HTTPS and passes secure requests correctly
- When `ENVIRONMENT=prod`, Django trusts the proxy-controlled `X-Forwarded-Proto` header for HTTPS detection

**SESSION_COOKIE_SECURE**
- Sends session cookies only over HTTPS
- Defaults to `True` when `ENVIRONMENT=prod`, otherwise `False`

**CSRF_COOKIE_SECURE**
- Sends CSRF cookies only over HTTPS
- Defaults to `True` when `ENVIRONMENT=prod`, otherwise `False`

**SECURE_HSTS_SECONDS**
- Enables HTTP Strict Transport Security for HTTPS responses
- Defaults to `31536000` when `ENVIRONMENT=prod`, otherwise `0`
- Set to `0` if you are not ready to commit the domain to HTTPS-only access

**SECURE_HSTS_INCLUDE_SUBDOMAINS**
- Extends HSTS to all subdomains
- Defaults to `False`
- Enable only when every subdomain is served over HTTPS

**SECURE_HSTS_PRELOAD**
- Marks the domain as eligible for browser HSTS preload lists
- Defaults to `False`
- Enable only when you intend to submit and maintain preload requirements

### Database configuration

Set either `DATABASE_URL` or the split `POSTGRES_*` settings below. `DATABASE_URL` takes precedence when present.

**DATABASE_URL**
- Full PostgreSQL connection URL
- Example: `postgres://user:password@host:5432/citeguild`
- Used by Fly.io Postgres attachments and many hosted Postgres providers
- Can be set temporarily from a PGSandbox MCP connection string when an agent
  runs disposable local Postgres tests
- Leave empty for Docker Compose and other deployments that use the split `POSTGRES_*` settings

**POSTGRES_DB**
- Name of the PostgreSQL database
- Example: `citeguild_db`

**POSTGRES_USER**
- PostgreSQL username
- Example: `citeguild_user`

**POSTGRES_PASSWORD**
- Password for your PostgreSQL database
- Use a strong, randomly generated password
- Generate one with: `openssl rand -base64 32`

**POSTGRES_HOST**
- PostgreSQL server hostname
- Example: `localhost` (for local), `db` (for Docker)

**POSTGRES_PORT**
- PostgreSQL server port
- Default: `5432`
- Optional - defaults to 5432 if not specified

### Redis configuration

Redis backs Django's default cache, the `django-q2` worker queue, and the `/api/healthcheck` Redis check.

**REDIS_URL**
- Optional full Redis connection URL
- Example: `redis://:password@redis:6379/0`
- Leave empty to build the URL from the `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, and `REDIS_DB` settings

**REDIS_HOST**
- Redis server hostname
- Example: `localhost` (for local), `redis` (for Docker)
- Default: `localhost`

**REDIS_PORT**
- Redis server port
- Default: `6379`

**REDIS_PASSWORD**
- Password for your Redis instance
- Use a strong, randomly generated password
- Generate one with: `openssl rand -base64 32`

**REDIS_DB**
- Redis database number
- Default: `0`

**LOCAL_INSTANCE_ID**
- Local namespace seed for generated cache and worker names
- Defaults to `citeguild`
- Override when two same-slug clones intentionally share one Redis service

### Qdrant configuration

Qdrant stores the derived semantic-search index. PostgreSQL remains authoritative.

**QDRANT_URL**
- Authenticated Qdrant HTTP endpoint
- Local Compose example: `http://qdrant:6333`

**QDRANT_API_KEY**
- Required secret for all Qdrant operations; use a unique random value in production

**QDRANT_TIMEOUT_SECONDS**
- Bounded client timeout; defaults to `5`

**CITEGUILD_QDRANT_COLLECTION**
- Stable article collection name; defaults to `citeguild-articles`

**CITEGUILD_EMBEDDING_DIMENSIONS**
- Exact unnamed-vector size; an incompatible existing collection fails startup

**CACHE_KEY_PREFIX**
- Prefix for Django cache keys stored in Redis
- Defaults to `LOCAL_INSTANCE_ID`
- Override when sharing Redis across same-slug clones

**Q_CLUSTER_NAME**
- Django Q2 cluster name
- Defaults to `<LOCAL_INSTANCE_ID>-q`
- Override when sharing Redis across same-slug clones or when running distinct worker groups

## Optional variables

These variables enhance functionality but aren't required:

### Healthchecks (Outbound Pings)

**HEALTHCHECKS_PING_BASE_URL**
- URL prefix used by `ping_healthchecks(...)` before appending the ping id
- Healthchecks.io example: `https://hc-ping.com`
- Self-hosted example: `https://healthchecks.example.com/ping`
- Leave empty to disable outbound pings

### Sentry (Error Tracking)

**SENTRY_DSN**
- DSN for Sentry error tracking
- Get your DSN from [Sentry](https://sentry.io/)
- Used for error monitoring, tracing, profiling, and logs
- Leave empty to disable Sentry

**SENTRY_ENABLED**
- Set to `False` to force-disable Sentry even when `SENTRY_DSN` is configured
- Defaults to enabled only when `ENVIRONMENT=prod` and `SENTRY_DSN` is present; the example env keeps it `True` so copied production env files do not silently disable Sentry

**SENTRY_RELEASE**
- Optional release identifier, usually your deployed commit SHA or app version
- Defaults to `SERVICE_VERSION`, then the immutable `CITEGUILD_RELEASE` image value
- Enables Sentry release/regression tracking and links issues to deploys

**SENTRY_TRACES_SAMPLE_RATE**
- HTTP/web transaction sample rate from `0.0` to `1.0`, after healthcheck/static/media filters
- Defaults to `1.0` so low-volume projects can get complete page-load traces

**SENTRY_BROWSER_ENABLED**
- Set to `True` to capture browser errors, navigation traces, and Web Vitals
- Defaults to the server-side Sentry enabled state

**SENTRY_BROWSER_TRACES_SAMPLE_RATE**
- Browser page-load and navigation trace sample rate from `0.0` to `1.0`
- Defaults to `SENTRY_TRACES_SAMPLE_RATE`
- Same-origin requests propagate trace headers to Django for end-to-end traces

**SENTRY_BACKGROUND_TRACES_SAMPLE_RATE**
- Background/task transaction sample rate from `0.0` to `1.0`
- Defaults to `0.1` so workers and cron-like jobs do not drown out page-load traces

**SENTRY_PROFILE_SESSION_SAMPLE_RATE**
- Continuous profiling sample rate from `0.0` to `1.0`
- Defaults to `1.0`; reduce for high-traffic projects after collecting a baseline

**SENTRY_ENABLE_LOGS**
- Set to `True` to enable Sentry structured logs support
- Defaults to `True`

**SENTRY_BREADCRUMB_LEVEL**
- Minimum Python logging level captured as Sentry breadcrumbs
- Defaults to `INFO`

**SENTRY_EVENT_LEVEL**
- Minimum Python logging level promoted to Sentry error events
- Defaults to `ERROR`

**SENTRY_LOGS_LEVEL**
- Minimum Python logging level sent to Sentry's searchable Logs product
- Defaults to `WARNING`

**SENTRY_SEND_DEFAULT_PII**
- Set to `True` to attach authenticated user/request PII to Sentry events
- Defaults to `False`; only enable when your privacy policy and data handling allow it

**SENTRY_INCLUDE_LOCAL_VARIABLES**
- Set to `True` to include stack-frame local variables in Sentry events
- Defaults to `False` to avoid accidentally capturing secrets or sensitive form data

**SENTRY_MAX_BREADCRUMBS**
- Number of breadcrumbs kept with each event
- Defaults to `100`

**SENTRY_DJANGO_MIDDLEWARE_SPANS**
- Set to `True` to include Django middleware spans in traces
- Defaults to `True`

**SENTRY_DJANGO_CACHE_SPANS**
- Set to `True` to include Django cache spans in traces
- Defaults to `True`

### PostHog (Analytics and Logs)

**POSTHOG_API_KEY**
- PostHog `phc_` project token for analytics and log ingestion
- Get your key from [PostHog](https://posthog.com/)
- Used for consented product analytics and feature flags
- Leave empty to disable PostHog

**POSTHOG_HOST**
- Regional PostHog ingestion host
- Defaults to `https://us.i.posthog.com`; use the matching regional host for your project

**POSTHOG_LOGS_ENABLED**
- Enables privacy-filtered batched OpenTelemetry log export
- Defaults to enabled in production when `POSTHOG_API_KEY` is configured
- Export failures never interrupt request or worker execution

**POSTHOG_LOG_LEVEL**
- Minimum level exported to PostHog Logs
- Defaults to `INFO`

The exporter sends a sanitized clone containing only explicitly allowlisted
scalar fields. Unknown attributes and the original formatted message are
dropped. When `profile_id` is available, the exporter derives
`posthogDistinctId` inside the PostHog-only clone. Console and Sentry handlers
still receive the original record, including normal exception diagnostics.

**POSTHOG_BROWSER_HOST**
- Browser ingestion and asset host
- Prefer a first-party reverse proxy in production to reduce blocked events
- Defaults to `POSTHOG_HOST` when empty
- The proxy must not cache ingestion responses

See `ANALYTICS.md` for the event, consent, attribution, and privacy contracts.


**POSTHOG_AI_OBSERVABILITY_ENABLED**
- Set to `True` to export Pydantic AI agent and embedding performance spans
- Defaults to `False`
- Prompt, response, tool, embedding input, binary, and exception contents are excluded

**POSTHOG_SERVICE_NAME**
- Service name attached to AI performance spans
- Defaults to the generated project slug

### Chatwoot (Support Chat)

**CHATWOOT_BASE_URL**
- Base URL for your Chatwoot instance.
- Self-hosted example: `https://chatwoot.yourdomain.com`.
- Chatwoot Cloud example: `https://app.chatwoot.com`.
- Leave empty to disable the support chat widget.
- Do not include a trailing slash; the app also strips it defensively.

**CHATWOOT_WEBSITE_TOKEN**
- Website inbox token from Chatwoot.
- In Chatwoot: **Settings → Inboxes → Add Inbox → Website**, finish setup, then copy the `websiteToken` from the install snippet or inbox configuration.
- Leave empty to disable the support chat widget.

**CHATWOOT_HMAC_SECRET**
- Optional but recommended for authenticated SaaS apps.
- In Chatwoot: **Settings → Inboxes → your Website inbox → Settings → Configuration → Identity Validation** and copy the HMAC token.
- Used to sign the authenticated user's identifier before calling `window.$chatwoot.setUser(...)`, which helps prevent customer impersonation.
- Leave empty if Identity Validation is disabled in Chatwoot.

Gotchas:
- Add these variables to the web app/container that serves Django pages. Worker-only apps will not make the browser widget appear.
- Restart/redeploy the web app after changing environment variables so Django reloads settings.
- If Chatwoot Identity Validation is enabled but `CHATWOOT_HMAC_SECRET` is missing or wrong, the widget can load but user identity can fail.
- If the bubble does not appear, confirm both `CHATWOOT_BASE_URL` and `CHATWOOT_WEBSITE_TOKEN` are non-empty in the running web process and check the browser console/network tab for blocked `sdk.js` requests.

### Apprise (Admin Notifications)

**APPRISE_API_URL**
- Base URL for your Apprise API instance.
- Example: `https://apprise.yourdomain.com`.
- Leave empty to disable Apprise and use email fallback.

**APPRISE_CONFIG_KEY**
- Saved Apprise configuration key used by `/notify/{key}`.
- Example: `citeguild`.
- Keep Slack bot tokens and webhook URLs inside Apprise, not in this Django app's env vars.

**APPRISE_BASIC_AUTH_USER**
- Optional Basic Auth username if your Apprise API is protected.
- Leave empty when Apprise does not require Basic Auth.

**APPRISE_BASIC_AUTH_PASSWORD**
- Optional Basic Auth password if your Apprise API is protected.
- Store as a secret in production.

**APPRISE_NOTIFICATION_FORMAT**
- Payload format sent to Apprise.
- Defaults to `markdown`.

**APPRISE_REQUEST_TIMEOUT**
- HTTP timeout in seconds for Apprise requests.
- Defaults to `10`.

**ADMIN_NOTIFICATION_EMAIL_FALLBACK**
- Set to `true` to send email if Apprise delivery fails.
- Defaults to `true`.

**ADMIN_NOTIFICATION_EMAIL_RECIPIENTS**
- Comma-separated recipients for email fallback.
- Defaults to `LVTD LLC <rasul@lvtd.dev>`.

Gotchas:
- Add Apprise env vars to any process that can emit admin notifications, including workers.
- Restart/redeploy after changing env vars so Django reloads settings.
- If `send_admin_notification(...)` returns `email`, confirm `APPRISE_API_URL` and `APPRISE_CONFIG_KEY` are set in the running process.
- See the Apprise deployment guide for saved-key setup and smoke-test commands.

### Stripe (Payments)

**STRIPE_LIVE_SECRET_KEY**
- Stripe secret key for live/production mode
- Get from [Stripe Dashboard](https://dashboard.stripe.com/)
- Used for processing real payments
- Leave empty if only using test mode

**STRIPE_TEST_SECRET_KEY**
- Stripe secret key for test mode
- Get from [Stripe Dashboard](https://dashboard.stripe.com/)
- Used for testing payment flows
- Required for development

**DJSTRIPE_WEBHOOK_SECRET**
- Webhook signing secret from Stripe
- Get from Stripe webhook configuration
- Used to verify webhook authenticity
- Required for handling Stripe events

### Email configuration

Configure these to send emails from CiteGuild (for notifications, password resets, etc.):

**MAILGUN_API_KEY**
- API key for Mailgun email service
- Get your key from [Mailgun](https://www.mailgun.com/)
- Used for sending transactional emails
- Leave empty to use console email backend (emails printed to console)

**MAILGUN_SENDER_DOMAIN**
- Mailgun sender domain for transactional email
- Defaults to `mg.citeguild.app`
- Override this when the project sends from another verified Mailgun domain

**DEFAULT_FROM_EMAIL**
- Default visible sender for transactional email
- Defaults to `LVTD LLC from CiteGuild <hello@citeguild.app>`

**SERVER_EMAIL**
- Sender used for server/admin error emails
- Defaults to `CiteGuild Errors <error@citeguild.app>`

**EMAIL_BACKEND**
- Optional Django email backend override
- Use `django.core.mail.backends.console.EmailBackend` for no-Docker local
  terminal development when Mailhog is not running
- Leave unset in Docker-backed development to use the Mailhog SMTP default

**EMAIL_HOST**, **EMAIL_PORT**, **EMAIL_USE_TLS**, **EMAIL_HOST_USER**, **EMAIL_HOST_PASSWORD**
- Optional SMTP settings used when `EMAIL_BACKEND` points at an SMTP backend
- Docker-backed development defaults to Mailhog at `mailhog:1025`

### AI configuration

Optional product AI features use Pydantic AI through OpenRouter by default, so one API key can route to any OpenRouter-supported model. Generated projects install `pydantic-ai-slim[openai]`, which provides the OpenAI-compatible client used by OpenRouter without installing provider extras the template does not use.

**OPENROUTER_API_KEY**
- API key from [OpenRouter](https://openrouter.ai/keys)
- Required before calling `apps.core.agents.build_model`

**OPENROUTER_APP_URL**, **OPENROUTER_APP_TITLE**
- Attribution sent with every Pydantic AI model and embedding request
- Default to `SITE_URL` and `CiteGuild`
- OpenRouter uses the app URL as the attribution identifier and the title as its display name

**OPENROUTER_MODEL_FAST**
- OpenRouter model id for latency-sensitive work
- Defaults to `openai/gpt-5-nano`

**OPENROUTER_MODEL_SMART**
- OpenRouter model id for higher-quality work
- Defaults to `anthropic/claude-sonnet-4.5`

### OAuth/Social Authentication

**GITHUB_CLIENT_ID**
- GitHub OAuth application client ID
- Get from [GitHub Developer Settings](https://github.com/settings/developers)
- Used for GitHub social login
- Leave empty to disable GitHub authentication

**GITHUB_CLIENT_SECRET**
- GitHub OAuth application client secret
- Get from [GitHub Developer Settings](https://github.com/settings/developers)
- Required if GITHUB_CLIENT_ID is set

### Storage configuration

Configure these to use cloud storage for media files:

**AWS_ACCESS_KEY_ID**
- Your AWS access key ID
- Get from AWS IAM console
- Required for S3 storage

**AWS_SECRET_ACCESS_KEY**
- Your AWS secret access key
- Get from AWS IAM console
- Required for S3 storage

**AWS_STORAGE_BUCKET_NAME**
- Name of your S3 bucket
- Create bucket in AWS S3 console

**AWS_S3_REGION_NAME**
- AWS region for your S3 bucket
- Example: `us-east-1`

**AWS_S3_ENDPOINT_URL**
- Custom S3 endpoint URL (optional)
- Used for S3-compatible services (DigitalOcean Spaces, Wasabi, etc.)
- Leave empty for standard AWS S3

### MJML (Email Templates)

**MJML_URL**
- URL for MJML HTTP server
- Used for rendering MJML email templates to HTML
- Leave empty to use MJML command-line tool

### Logging

**DJANGO_LOG_LEVEL**
- Application logging level
- Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- Default: `INFO`

**DJANGO_LOG_FORMAT**
- Output format for Python's standard `logging` module
- Values: `console`, `json`
- Default: `console` when `ENVIRONMENT=dev`, `json` when `ENVIRONMENT=prod`
- JSON logs include canonical fields such as `event.name`, `request.id`, `request.interface`, `http.route`, `http.response.status_code`, `duration_ms`, and actor IDs when available
- Use stable dotted event names and normal stdlib calls such as `logger.info("job.completed", extra={"event.name": "job.completed", "outcome": "success"})`
- `outcome` is always `success` or `failure`; use `operation.status` for richer states
- Do not log credentials, cookies, email addresses, request/response bodies, arbitrary metadata, task arguments/results, or user-owned content

**SERVICE_NAME**
- Service facet shared by JSON and PostHog logs
- Defaults to `citeguild-web` or `citeguild-worker` from `APP_PROCESS_TYPE`

**SERVICE_VERSION**
- Optional deploy/release identifier shared by log backends

## Getting the .env.example file

The complete `.env.example` file with all variables and detailed comments is available in the CiteGuild repository.

Download it directly:

```bash
wget https://github.com/LVTD-LLC/citeguild/raw/main/.env.example -O .env
```

Or with curl:

```bash
curl -o .env https://github.com/LVTD-LLC/citeguild/raw/main/.env.example
```

This file includes all available options with explanations and example values.

## Security best practices

Follow these guidelines to keep your CiteGuild installation secure:

**Never commit .env files**
- Add `.env` to your `.gitignore`
- Use environment variables or secret management systems for production

**Use strong passwords**
- Generate random passwords for database and Redis
- Use at least 32 characters for production passwords

**Keep secrets confidential**
- Don't share your SECRET_KEY or API keys
- Rotate keys immediately if exposed

**Use HTTPS in production**
- Set ALLOWED_HOSTS to specific domains only
- Configure SSL/TLS certificates for your domain
- Never set DEBUG=True in production

**Limit access**
- Use firewall rules to restrict database and Redis access
- Only expose necessary ports to the internet
- Use strong authentication for all services
