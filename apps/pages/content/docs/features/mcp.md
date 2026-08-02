---
title: MCP access
---

# MCP access

This project includes a hosted MCP server at `/mcp/`, OAuth discovery endpoints, Dynamic Client Registration, ready-to-copy agent instructions at `/AGENTS.md`, and a dashboard prompt that includes the exact URLs an agent needs.

The server exposes two focused tools:

- `get_user_info` returns safe account/profile details for the authenticated user.
- `search_member_articles` finds relevant active member articles for a query or draft passage. It accepts `query`, `limit` (1–50), optional `language`, and up to 20 exact `excluded_domains`. Results match the versioned REST search contract and contain public citation fields only.

Search relevance identifies candidate sources; it is not an endorsement or a requirement to link. Read and verify a result before citing it.

The dashboard reveals the **Connect an AI agent** prompt after the first site is
submitted. Copy that prompt into a clean agent session; it contains public URLs
and safe workflow instructions, never an API key.

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

Create an API key from **Settings** only when a client cannot complete OAuth.
The key is shown once. Store it in `CITEGUILD_API_KEY`, then close the page.
Rotating the key immediately revokes the previous value, so update every client
that still needs access. Never paste a key into a prompt, config file, URL,
support message, screenshot, or log.

### Provider-neutral setup

1. Start a clean agent session and paste the dashboard prompt.
2. Configure `{{ mcp_url }}` using the client's OAuth flow when supported.
3. Otherwise export `CITEGUILD_API_KEY` and configure an
   `Authorization: Bearer` header through the client's environment-variable
   mechanism.
4. Call `get_user_info`, then call `search_member_articles` with a real research
   question or draft passage.
5. Open and evaluate promising results. Cite only sources that genuinely support
   the work; never force a link or treat a similarity score as factual proof.

If the client does not support MCP, send the same Bearer credential to
`POST {{ api_base_url }}/v1/search`. The REST and MCP search surfaces return the
same versioned contract: public article identity and citation fields, an excerpt,
language, last-seen timestamp, and a `relevance` score from 0 to 1. That score is
for candidate ranking only.

### Codex bearer configuration

Export the key in the shell that starts Codex, then add this to `~/.codex/config.toml`:

```text
export CITEGUILD_API_KEY="<copy the key from CiteGuild settings>"
```

```toml
[mcp_servers.citeguild]
url = "{{ mcp_url }}"
bearer_token_env_var = "CITEGUILD_API_KEY"
```

Restart Codex, confirm the `citeguild` server is enabled, and call `get_user_info` before `search_member_articles`. Keep the key out of the TOML file.

### Claude Code bearer configuration

Claude Code expands environment variables in project `.mcp.json` files:

```json
{
  "mcpServers": {
    "citeguild": {
      "type": "http",
      "url": "{{ mcp_url }}",
      "headers": {
        "Authorization": "Bearer ${CITEGUILD_API_KEY}"
      }
    }
  }
}
```

Export `CITEGUILD_API_KEY` before starting Claude Code, approve the project MCP server, and use `/mcp` to verify the connection. OAuth remains preferred when the client supports it reliably.

## Give this prompt to a coding agent

```text
{{ agent_setup_prompt }}
```

## Deployment note

MCP uses ASGI. The generated server command runs `gunicorn citeguild.asgi:application` with `uvicorn_worker.UvicornWorker` when MCP is enabled.
