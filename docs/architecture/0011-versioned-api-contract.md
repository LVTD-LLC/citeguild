# Versioned API contract

CG-020 publishes the durable REST adapter at `/api/v1`. Existing unversioned
routes remain available for compatibility, but new integrations use the
versioned account, project, and search operations documented in OpenAPI.

Authentication reuses the existing profile credential: a high-entropy API key
is displayed only when generated or rotated, the database retains its public
lookup prefix and a per-key salted hash, and verification uses constant-time
digest comparison. Both `X-API-Key` and `Authorization: Bearer` are accepted.
Rotation immediately revokes the previous key. The public key prefix is bound
as a usage-attribution identifier; raw credentials never enter logs, cache
keys, analytics, URLs, or responses.

Account and project queries always derive their scope from the authenticated
profile. Project detail deliberately returns the same stable `404` for missing
and other-account UUIDs. List pagination is bounded to 100 results and an
offset of 10,000. Sitemap submission continues to use the shared SSRF-safe
validation and durable initial-sync service.

`POST /api/v1/search` is a thin adapter over `SearchService`: it does not embed,
rank, authorize, or shape results independently. Request schemas narrow the
shared bounds so schema-compliant OpenAPI examples reach the service, and its
stable errors map to `403`, `422`, or `503` without exposing dependency details
or query content.

Every authenticated v1 operation consumes an atomic Redis-backed fixed-window
allowance of 60 requests per credential per minute. Cache keys contain a digest
of the public credential identifier. If limiting is unavailable the API fails
closed with a retryable `503`; exceeded limits return `429` plus `Retry-After`.
All error bodies carry the middleware request ID, and successful or failed
requests retain content-free profile/key attribution through structured logs.
