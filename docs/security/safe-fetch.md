# Safe outbound fetch threat model

CiteGuild treats every sitemap URL, sitemap entry URL, redirect target, DNS
answer, response header, and response byte as attacker controlled. No ingestion
code may call a general-purpose HTTP client with one of those URLs. The shared
`apps.core.safe_fetch.SafeFetchClient` is the only crawler transport boundary.

## Concrete attack paths

- Direct and encoded URLs targeting loopback, RFC 1918, link-local/cloud
  metadata, shared, multicast, reserved, or unspecified addresses.
- Hostnames returning a mix of public and non-public addresses.
- DNS rebinding between application validation and the socket connection.
- Public URLs redirecting to internal services or cycling indefinitely.
- Credentials, unsupported schemes, unusual ports, or control characters in
  submitted URLs.
- Oversized, slowly streamed, compressed, or incorrectly typed responses.
- Error bodies, URLs, queries, and transport exceptions leaking secrets into
  user-visible messages or logs.

## Load-bearing controls

The client resolves each request and redirect once, rejects the entire DNS
answer set unless every address is globally routable, and connects the socket
to one of those already-validated IPs. For TLS, certificate validation and SNI
still use the original normalized hostname. The HTTP `Host` header also uses
that hostname. This pinning is the defense against DNS rebinding; validation
without connection pinning is insufficient.

Only HTTP on port 80 and HTTPS on port 443 are accepted. Redirects are manual
and repeat the full validation/pinning process. Streaming byte limits apply to
both transferred and decompressed data. Only explicitly requested content
types and supported encodings are accepted. Typed errors expose stable codes
and retryability without echoing URLs, response bodies, or raw exceptions.

Per-host concurrency and minimum-interval limits are process-local safeguards;
global worker concurrency remains bounded by the shared runtime configuration.
If CiteGuild later runs many worker replicas, distributed per-domain fairness
belongs in the queue scheduler rather than weakening this fetch boundary.
