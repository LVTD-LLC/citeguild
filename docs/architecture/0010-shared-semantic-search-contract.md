# Shared semantic search contract

CG-019 introduces one transport-independent `SearchService`. API and MCP
adapters call this service rather than owning query embedding, eligibility,
ranking, or result shaping. Its internal contract is explicitly versioned as
`v1` so future adapters can expose a stable shape while the implementation
evolves.

CG-021 exposes that contract through one authenticated Streamable HTTP MCP tool,
`search_member_articles`. The MCP adapter injects the profile from validated
OAuth/API-key request context, applies protocol-level input bounds, and converts
safe `SearchError` codes into tool errors; it does not accept model-controlled
account identifiers or duplicate search logic. The tool description presents
matches as sources to verify, never as endorsements or forced-link obligations.

The service accepts an authenticated profile with an active subscription, a
non-empty query of at most 8,000 normalized characters, an optional BCP 47-like
language, up to 20 exact normalized domains to exclude, and a result limit from
1 through 50. Domain exclusions are exact hosts: excluding `example.com` does
not silently exclude `docs.example.com`.

Each result contains only the public article UUID, title, canonical URL, domain,
language, a deterministic excerpt of at most 320 characters, a cosine relevance
value clamped to `[0, 1]`, and the PostgreSQL last-seen timestamp. Similarity is
a ranking signal, not a statement of truth or endorsement.

Qdrant applies active, project, language, and excluded-domain filters before
ranking. PostgreSQL then remains authoritative: every candidate is rechecked
for active paid ownership, project and article lifecycle, ready extraction, and
a current successful embedding matching the configured model, dimensions, and
content hash. Qdrant payload metadata is never returned as application truth.

Empty corpora and no-match searches return an empty `v1` response. Invalid
inputs and dependency failures raise stable `SearchError` codes with a
retryability flag; provider messages and exception details do not cross the
service boundary. Structured completion events contain contract version,
latency, result count, status, error code, and retryability only. Query text,
article text, excerpts, URLs, vectors, and provider payloads never enter logs or
metrics.
