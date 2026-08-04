# MVP Acceptance Suite

CG-030 defines the cross-component launch acceptance boundary. CG-022 adds the
independently distributed CLI acceptance contract over the completed v1 API.

## CI lanes

| Lane | Boundary | Budget |
| --- | --- | --- |
| Python quality | Ruff, formatting, templates, static complexity, and typed baseline | 10 minutes |
| Frontend | Locked install, lint, and production asset build | 10 minutes |
| Go CLI | Formatting, vet, unit/race tests, build, and clean install smoke | 10 minutes |
| Dependency security | Locked Python runtime dependencies and npm runtime dependencies | 10 minutes; high findings fail CI |
| PostgreSQL tests | Migrations, Django checks, full pytest suite, and high-risk coverage report | 15 minutes |
| Real-service acceptance | PostgreSQL 18, Redis 8.6.3, Qdrant 1.18.3, and the paid-site scenario | 10 minutes |

The real-service lane uses fixed service versions and isolated test data. It never
calls Stripe, an embedding provider, a submitted website, or another live service.

## Acceptance matrix

| Risk or behavior | Evidence |
| --- | --- |
| Billing and duplicate/stale webhooks | `apps/core/tests/test_stripe_webhooks.py`, `test_billing.py` |
| Owner isolation and paid access | `test_projects.py`, API v1 tests, MCP OAuth tests, dashboard tests |
| XML, gzip, entity, size, and sitemap bounds | `test_sitemap_parser.py`, `test_sitemap_submission.py` |
| SSRF, redirects, DNS rebinding, ports, types, and encodings | `test_safe_fetch.py` |
| Queue idempotency, retries, cancellation, and recovery | `test_crawl_jobs.py`, `test_daily_reconciliation.py` |
| Extraction, canonical URLs, hashes, and lifecycle | `test_html_extraction.py`, `test_article_ingestion.py` |
| Embedding bounds, failures, and idempotency | `test_article_embeddings.py` |
| Qdrant collection, lifecycle, authorization, and search | `apps/search/tests/test_qdrant.py`, `test_service.py` |
| API auth, rate limits, schema, and stable errors | `apps/api/test_v1.py`, `test_schema.py` |
| MCP auth, protocol, analytics, and shared search parity | `apps/mcp_server/tests/` |
| CLI parsing, auth, bounded HTTP behavior, output, and exit codes | `cli/internal/api`, `cli/internal/command`, and native tagged-artifact smoke |
| Link graph and dashboard privacy/ownership | `test_network_graph.py`, `test_dashboard.py` |
| Cross-component paid account to detected citation | `test_mvp_acceptance.py` against real PostgreSQL, Redis, and Qdrant |

## Measured budgets

The representative CI fixture contains two authoritative articles and 250
non-authorized Qdrant points. A paid-account search, including query embedding
stub, Qdrant filtering, and PostgreSQL reauthorization, must complete within two
seconds. This is a regression smoke budget, not a production percentile claim.

The full real-service lane must finish within ten minutes. When the production
corpus becomes materially larger, replace the 250-point smoke fixture with a
captured synthetic distribution and set p50/p95 budgets from production traces.

## Known exceptions

- Stripe signatures and lifecycle semantics use inert fixtures. Live Stripe is
  reserved for an explicit protected smoke job.
- Embedding responses are deterministic fixtures; provider availability and
  latency are operational metrics, not ordinary-CI dependencies.
- Browser design acceptance is deferred. Server-rendered dashboard ownership,
  pagination, and accessibility states remain covered by Django tests.
- CLI API behavior uses deterministic local HTTP fixtures in ordinary CI.
  Publishing and production-key smoke remain protected release/operations
  actions rather than pull-request tests.

## Local commands

Start PostgreSQL, Redis, and Qdrant with the local Compose file, export the
matching terminal variables, then run:

```bash
make acceptance-test -- -q
make security-check
```

Run the normal deterministic path with `make ci-local`.
