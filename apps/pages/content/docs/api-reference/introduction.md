---
title: Introduction
description: Learn how CiteGuild API authentication works and where to find generated API docs.
keywords: CiteGuild API, API authentication, OpenAPI docs
---

# Introduction

CiteGuild exposes authenticated REST endpoints for account checks and product-specific integrations.

## Base URL

```text
{{ api_base_url }}
```

## Authentication

Generate an API key from **Settings**, store it in an environment variable, and send it as a header:

```http
Authorization: Bearer ${{ api_key_env_var }}
```

Example request:

```bash
curl -H "Authorization: Bearer ${{ api_key_env_var }}" "{{ api_base_url }}/v1/account"
```

API keys are shown only once when generated or rotated. Rotating a key immediately
revokes its previous value. Treat keys like passwords: do not put them in prompts,
URLs, frontend code, public repos, shared screenshots, or logs.

## Interactive API docs

CiteGuild also exposes generated API docs from the backend schema:

[Open generated API docs]({{ api_docs_url }})

Use those generated docs when you want request/response schemas or to inspect lower-level endpoint details. Use this docs section for workflow-oriented guidance.

## Version 1 endpoints

- `GET /v1/account` — inspect the credential owner's account and subscription state.
- `GET /v1/projects` — list owner-scoped site and indexing status with bounded pagination.
- `GET /v1/projects/{project_uuid}` — inspect one owner-scoped site without revealing whether another account owns an identifier.
- `POST /v1/projects` — validate a sitemap and start its initial sync.
- `POST /v1/search` — search the active member corpus through the shared `v1` semantic-search contract.

Search accepts a query of at most 8,000 characters, a result limit from 1 to 50,
an optional language, and at most 20 exact domains to exclude. Responses include
the contract version and public article metadata, excerpt, relevance, language,
and last-seen timestamp. The `relevance` value ranges from 0 to 1 and is a
candidate-ranking signal, not an endorsement, factual guarantee, or requirement
to cite a result.

Versioned endpoints return an `X-Request-ID` response header. Error bodies use
stable `code`, `message`, `retryable`, and `request_id` fields without provider
or application internals. Each API key has an atomic 60-request fixed-window
limit; a `429` response includes `Retry-After` and rate-limit headers.

## Sections

- **Version 1 API** — account status, owner-scoped sites, and shared semantic search.
