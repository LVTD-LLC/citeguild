# Production dogfood

This runbook validates the real member journey without treating search results as
an instruction to publish a link. Use approved sites and an account authorized by
a live subscription or the production-only superuser test bypass. Store the API
key in a secret manager and pass it only through an authorization header.

## Flow

1. Submit each approved sitemap through `POST /api/v1/projects`.
2. Poll `GET /api/v1/projects/{project_uuid}` until the initial sync has a
   completion timestamp, no current start timestamp, no safe error code, and a
   non-zero active article count.
3. Connect an actual MCP client to `/mcp/`, call `get_user_info`, then call
   `search_member_articles` with the writer's real question and the source site's
   domain excluded. The two calls must succeed in the same client lifecycle.
4. Treat every result as a candidate. Open the source, verify that it answers the
   reader's question, and reject it if the citation would be forced, reciprocal,
   or immaterial.
5. Publish only through the site's normal editorial PR and approval process.
6. Re-run the source sitemap sync. Verify an active `DetectedNetworkLink` joins
   the source article to the intended target project and preserves the observed
   destination and anchor text.
7. Record submission, indexing, search, publication, re-sync, and edge-detection
   durations plus any product defects found.

## 2026-08-02 evidence

- A dedicated `citeguild-dogfood` identity was authorized through the
  production-only superuser test bypass. Its rotated key is hashed in PostgreSQL
  and stored in Infisical at `/projects/citeguild/dogfood`.
- The authenticated public API admitted Built with Django, OSIG, and LVTD using
  their public sitemaps. OSIG indexed one active page and LVTD indexed six active
  pages; LVTD completed its initial sync in 20.2 seconds. Built with Django's
  larger 465-page inventory continued in the background.
- API and MCP semantic searches for an open-source Open Graph image generator
  returned OSIG as the top result. The authenticated MCP result identified
  `https://osig.app/` with relevance `0.524577` while excluding `lvtd.dev`.
- The first multi-call MCP run found a production-only failure: Gunicorn's three
  workers did not share FastMCP's in-memory session state, so valid clients could
  receive `Session terminated`. The hosted app now uses stateless Streamable HTTP
  so tool discovery, account verification, and search remain safe across workers.
- The 465-page Built with Django crawl exposed a dispatch starvation defect:
  work beyond the per-site concurrency limit could leave the broker without a
  later refill. Dispatch now reserves only open site slots and refills a slot
  after every terminal page outcome.

The dogfood is complete only after the editorial agent selects or rejects a
candidate, any approved publication is synced, and the expected active graph edge
is verified. A search result by itself is not citation evidence.
