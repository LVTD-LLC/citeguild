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
curl -H "Authorization: Bearer ${{ api_key_env_var }}" "{{ api_base_url }}/user"
```

API keys are shown only once when generated or rotated. Treat them like passwords: do not put them in URLs, frontend code, public repos, shared screenshots, or logs.

## Interactive API docs

CiteGuild also exposes generated API docs from the backend schema:

[Open generated API docs]({{ api_docs_url }})

Use those generated docs when you want request/response schemas or to inspect lower-level endpoint details. Use this docs section for workflow-oriented guidance.

## Sections

- **User API** — verify a key and inspect safe profile details.
- Add product-specific API pages here as you add user-facing endpoints.
