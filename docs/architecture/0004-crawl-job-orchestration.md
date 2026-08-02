# Crawl job orchestration

CG-013 uses PostgreSQL as workflow truth and Django Q2/Redis only for delivery.
Queue payloads contain durable sync or page-work UUIDs, never URLs, response
bodies, credentials, or model instances. Submission commits one uniquely keyed
initial sync and publishes it from `transaction.on_commit`; broker failure
leaves queued intent for recovery instead of rolling back the site.

`run_sitemap_sync` claims the sync transactionally, rechecks project and
subscription eligibility, parses and atomically promotes the candidate
inventory, and creates one unique `PageCrawlWork` per candidate. Dispatch uses
bounded batches. Project-row locking serializes page claims and enforces the
configured per-site running limit across worker processes; the Q2 worker count
provides the global process limit.

Fetch errors carry only stable codes and retryability. Retryable work returns
to `queued` with capped exponential backoff plus deterministic jitter; attempt
counts are durable and terminal failures are visible in admin. Page outcomes
derive sync progress and final `succeeded`, `partial`, or `failed` state.
Suspension or lost subscription cancels unfinished work, including races with
an already-running fetch.

A named five-minute Q2 schedule and a worker-startup sweep recover due work,
stale `running` claims, and interrupted broker publication markers. Schedule
creation is idempotent and Q2 catch-up is disabled, so downtime does not replay
every missed sweep. CG-014 will replace the current bounded HTML fetch outcome
with extraction; CG-015 will persist article lifecycle/content results.
