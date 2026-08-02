# Sitemap submission state machine

The MVP accepts a project name and one public HTTP(S) sitemap URL. Submission
does a bounded document validation, not a full crawl.

## Transitions

1. `submitted`: authenticate the account, require an active subscription, and
   normalize the URL.
2. `validating`: fetch only the sitemap through `SafeFetchClient`, enforce the
   configured sitemap byte limit, parse with `defusedxml`, and require a
   `urlset` or `sitemapindex` root.
3. `rejected`: return a stable, sanitized permanent error. No project or sync
   request is created.
4. `retryable`: return a sanitized `retryable: true` error for DNS, timeout,
   concurrency, unreachable, or temporary upstream failures. The user can
   resubmit without cleaning up partial state.
5. `queued`: atomically create the owned project and its single initial
   `ProjectSyncRequest`. The request is the durable queue boundary that CG-013
   workers will consume; sitemap URL enumeration remains in CG-012.

The unique `(project, kind)` constraint and `get_or_create` make initial-sync
staging idempotent. `Project.current_sync_uuid` points at the queued request so
the dashboard and later workers share the same status identity.
