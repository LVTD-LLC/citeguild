# Runtime Configuration Contract

`citeguild.config.RuntimeConfig` is the typed startup contract shared by the
web and worker processes. Django imports it before configuring external
clients, so invalid production configuration fails before either process
accepts work. Both processes print the same secret-safe fingerprint at startup;
the web healthcheck also exposes it as `configuration_fingerprint`.

`django-environ` loads the local `.env` file into the process environment
before this contract is constructed. Existing OS/container variables retain
precedence over `.env`, matching the scaffold's established behavior.

## Component Matrix

| Component | Variables | Production contract |
| --- | --- | --- |
| Runtime | `ENVIRONMENT`, `APP_PROCESS_TYPE`, `SECRET_KEY`, `SITE_URL` | Environment and process role are enumerated. The site origin uses HTTPS and the signing key cannot use the development template value. |
| PostgreSQL | `DATABASE_URL` or `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT` | A complete authenticated URL or complete split configuration is required. |
| Redis / Django Q2 | `REDIS_URL` or `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD` | Password authentication is required. Web and worker deployments must use the same logical Redis service and queue namespace. |
| Qdrant | `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_TIMEOUT_SECONDS`, `CITEGUILD_QDRANT_COLLECTION` | URL and API key are required. The private service need not have a public domain. |
| Embeddings | `CITEGUILD_EMBEDDING_MODEL`, `CITEGUILD_EMBEDDING_DIMENSIONS`, `CITEGUILD_INDEXING_ENABLED` | Model and positive dimensions are typed. Enable indexing only when the embedding provider and authenticated Qdrant collection are configured; a crawl is not reported successful until its ready articles are durably searchable. |
| Crawling and extraction | `CITEGUILD_CRAWL_REQUEST_TIMEOUT_SECONDS`, `CITEGUILD_CRAWL_MAX_REDIRECTS`, `CITEGUILD_CRAWL_MAX_SITEMAP_BYTES`, `CITEGUILD_CRAWL_MAX_SITEMAP_ENTRIES`, `CITEGUILD_CRAWL_MAX_SITEMAP_DEPTH`, `CITEGUILD_CRAWL_MAX_SITEMAP_FILES`, `CITEGUILD_CRAWL_MAX_PAGE_BYTES`, `CITEGUILD_CRAWL_CONCURRENCY`, `CITEGUILD_CRAWL_PER_SITE_CONCURRENCY`, `CITEGUILD_CRAWL_DISPATCH_BATCH_SIZE`, `CITEGUILD_CRAWL_MAX_ATTEMPTS`, `CITEGUILD_CRAWL_STALE_AFTER_SECONDS`, `CITEGUILD_EXTRACTION_MIN_TEXT_CHARS`, `CITEGUILD_EXTRACTION_MAX_TEXT_CHARS`, `CITEGUILD_EXTRACTION_MAX_TREE_SIZE` | Positive bounded defaults are explicit; sitemap traversal defaults to depth 3 and 100 files. Workers default to four global processes, two concurrent pages per site, 100-task dispatch batches, three attempts, and one-hour stale-work recovery. Extraction keeps 200–500,000 characters and bounds parser trees to 100,000 elements by default. |
| Scheduler | `CITEGUILD_RECONCILE_INTERVAL_HOURS` | Positive integer; defaults to daily sitemap reconciliation. A named 15-minute sweep claims due sites after this interval plus stable per-site jitter; unchanged pages without useful `lastmod` hints are availability-checked after seven intervals. |
| Stripe | `CITEGUILD_BILLING_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_CONTEXT`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_MONTHLY` | When billing is enabled, the key, explicit LVTD LLC account context, webhook secret, and fixed monthly Price are required. No yearly CiteGuild price is part of the MVP. |
| Observability | `SERVICE_NAME`, `SERVICE_VERSION`, `SENTRY_*`, `POSTHOG_*`, `DJANGO_LOG_*` | Optional integrations retain their existing typed settings. Do not include credentials or user content in logs or fingerprints. |

## Fingerprint Boundary

The fingerprint hashes behavior-affecting public configuration: environment,
site origin, collection/model/dimensions, feature gates, crawler limits,
scheduler interval, and Qdrant timeout. It deliberately excludes process role,
secrets, credentials, and connection URLs. A differing web/worker fingerprint
therefore identifies configuration drift without exposing sensitive values.

Run the same check used by container startup with:

```bash
uv run python manage.py config_fingerprint
```
