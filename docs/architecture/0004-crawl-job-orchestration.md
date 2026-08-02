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

CG-024 adds a named 15-minute reconciliation schedule and runs the same bounded
sweep when a worker starts. Each active paid site becomes due after the configured
interval plus stable UUID-derived jitter. A PostgreSQL project-row claim, the
one-active-sync constraint, and a due-time idempotency key prevent concurrent
schedulers from creating duplicate daily work. Redis remains delivery only; a
broker outage leaves the queued daily request visible for the recovery sweep.

Every due run fetches and atomically promotes the complete sitemap inventory so
removed URLs reconcile immediately. Page work is limited to new URLs, changed
non-empty `lastmod` hints, URLs that never produced an active article source, and
unchanged articles not fetched for seven reconciliation intervals. This keeps an
unchanged daily sitemap cheap without allowing hint-free content to remain stale
forever. Terminal sitemap failures set the project's visible error code, and the
owner-scoped dashboard action creates or republishes one manual retry.

## Article lifecycle truth table

PostgreSQL is authoritative for article lifecycle; Qdrant is a derived search
index. Lifecycle transitions preserve the article UUID, content, crawl history,
and link history.

| Observation | Lifecycle action |
| --- | --- |
| URL present and page ready | Reset the sitemap-absence counter, preserve the article UUID, refresh content when changed, and publish the current point before marking the article active. |
| URL absent from one successful sitemap | Increment the source absence counter but keep the source and article active. |
| URL absent from two consecutive successful sitemaps | Soft-deactivate the source; soft-deactivate the article only when it has no other active source; queue removal of its Qdrant point. |
| HTTP 404 or 410 | Record the status in crawl history and soft-deactivate the source/article immediately; queue point removal and limit rechecks to once per seven reconciliation intervals. |
| Timeout, DNS/network error, 408, 425, 429, or 5xx | Retry within the crawl budget and preserve the last healthy article and point. |
| Same-host redirect to a healthy page | Follow the redirect and preserve the existing article UUID when the canonical target is not already owned by another article. |
| Empty or noindex page | Preserve last good content and history, mark inactive with the extraction reason, and synchronously remove the point. |
| Previously inactive URL returns ready | Reset absence state, clear inactivity metadata, refresh/reuse its embedding, and reactivate only after Qdrant publication succeeds. |

Search always rechecks project eligibility, article state, and embedding state in
PostgreSQL, so a lagging Qdrant point cannot leak an inactive article while an
asynchronous deletion is pending.
