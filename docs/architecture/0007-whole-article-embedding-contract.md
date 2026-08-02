# Whole-article embedding contract

CG-016 produces exactly one current MVP embedding record per article. The
one-to-one `ArticleEmbedding` row stores the vector together with the exact
article content hash, configured provider/model identifier, dimensions, bounded
input size, token usage, latency, outcome, and stable error code. A succeeded
record is reused only when all of content hash, model, dimensions, and actual
vector length still match. Changed content or configuration refreshes that same
row; it never creates chunk records or multiple current vectors.

Only normalized extracted article text is sent to the provider. Account data,
URLs, raw HTML, credentials, and provider response bodies are excluded. Text is
whitespace-normalized and capped at 24,000 characters by retaining deterministic
head and tail portions around an explicit truncation marker. This preserves one
provider input and one article vector while making long-input behavior stable
and testable. Empty input and dimension mismatch are nonretryable failures.
Transport, timeout, throttling, and provider 5xx failures use stable retryable
codes; exception payloads are never logged.

Provider calls happen outside database transactions. The article content hash
is rechecked under a row lock before committing the result, so a vector computed
for stale content cannot become current. Django Q retries only retryable
embedding failures. Ingestion queues work only when the indexing feature gate is
enabled; unchanged work may reach the worker but is rejected before any provider
call. Structured completion logs expose duration, input characters, input
tokens, model, dimensions, and outcome without content.

The default MVP contract is
`openrouter:openai/text-embedding-3-small` at 1,536 dimensions. The vector stays
in PostgreSQL as durable handoff state for now. A later task will upsert the same
stable article UUID and vector into Qdrant and only then mark the article active
for search.
