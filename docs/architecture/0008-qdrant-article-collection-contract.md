# Qdrant article collection contract

CG-017 adds one unnamed-vector collection configured by
`CITEGUILD_QDRANT_COLLECTION`. It uses the exact configured embedding dimensions
and cosine distance. Startup creates a missing collection and its filter indexes
idempotently, but rejects existing collections with named vectors, a different
dimension, or a different distance. The public health check verifies authenticated
reachability and the same compatibility contract without mutating Qdrant.

Each point ID is the stable `Article.qdrant_point_id`, which is the article UUID.
Payloads contain only the article UUID, project UUID, site host, language, content
hash, embedding model, and active flag. They exclude article content, account
details, and credentials. Upsert requires a current succeeded PostgreSQL embedding
whose hash, model, dimensions, and vector length match the current eligible article.
Only after a synchronous Qdrant write succeeds does PostgreSQL mark the article
active. Deactivation deletes the point and retains lifecycle history in PostgreSQL.

Search requires a non-empty set of project UUIDs that the application has already
authorized. Qdrant applies active, project, site, and language filters with a hard
50-result limit. Every returned point is then re-authorized against active
PostgreSQL article and project rows, and result metadata comes from PostgreSQL.
Qdrant payloads are therefore never an authorization or lifecycle source of truth.

`rebuild_qdrant_articles` creates or validates the collection, streams eligible
PostgreSQL embeddings in bounded batches, upserts them with stable IDs, and removes
points absent from the authoritative corpus. This is the recovery path for a lost
collection, interrupted writes, and lifecycle drift. Local Compose runs the pinned
Qdrant version with API-key authentication and a named persistent volume; production
uses the private authenticated CapRover service.
