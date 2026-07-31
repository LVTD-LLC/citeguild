---
title: MCP access
---

# MCP access

This project includes a hosted MCP server at `/mcp/`, OAuth discovery endpoints, Dynamic Client Registration, ready-to-copy agent instructions at `/AGENTS.md`, and a dashboard prompt that includes the exact URLs an agent needs.

The first included MCP tool is `get_user_info`, which returns safe account/profile details for the authenticated user. The same data is available through the REST endpoint `GET /api/user`.

## URLs

```text
MCP URL: {{ mcp_url }}
Agent instructions: {{ agent_instructions_url }}
User API: {{ api_base_url }}/user
```

## Authentication

Use MCP OAuth when the client supports it. Add the MCP URL to the client; it should discover the protected resource metadata, register itself, open a browser sign-in flow, and then call MCP with `Authorization: Bearer <access_token>`.

OAuth discovery endpoints:

- `/.well-known/oauth-protected-resource`
- `/.well-known/oauth-protected-resource/mcp`
- `/.well-known/oauth-authorization-server`
- `/.well-known/openid-configuration`

Legacy clients can still authenticate with the API key shown on the user settings page. Never hardcode it into source control.

- `X-API-Key: <api_key>`
- `Authorization: Bearer <api_key>`

API keys are intentionally not accepted in query strings.

## Give this prompt to a coding agent

```text
{{ agent_setup_prompt }}
```

## Deployment note

MCP uses ASGI. The generated server command runs `gunicorn citeguild.asgi:application` with `uvicorn_worker.UvicornWorker` when MCP is enabled.
