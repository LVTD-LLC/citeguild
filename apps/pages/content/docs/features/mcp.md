---
title: MCP access
---

# MCP access

This project includes a hosted MCP server at `/mcp/`, OAuth discovery endpoints, Dynamic Client Registration, ready-to-copy agent instructions at `/AGENTS.md`, and a dashboard prompt that includes the exact URLs an agent needs.

The server exposes two focused tools:

- `get_user_info` returns safe account/profile details for the authenticated user.
- `search_member_articles` finds relevant active member articles for a query or draft passage. It accepts `query`, `limit` (1–50), optional `language`, and up to 20 exact `excluded_domains`. Results match the versioned REST search contract and contain public citation fields only.

Search relevance identifies candidate sources; it is not an endorsement or a requirement to link. Read and verify a result before citing it.

## Install the official plugin

The [CiteGuild Skills repository](https://github.com/LVTD-LLC/citeguild-skills) packages the hosted MCP connection and the `find-editorial-citations` workflow for Claude Code, ChatGPT, and Codex.

For Claude Code:

```text
/plugin marketplace add LVTD-LLC/citeguild-skills
/plugin install citeguild@citeguild-skills
```

For ChatGPT and Codex plugin surfaces:

```text
codex plugin marketplace add LVTD-LLC/citeguild-skills
codex plugin add citeguild@citeguild-skills
```

For Codex, copy the protected dashboard prompt so the plugin receives the account API key from `CITEGUILD_API_KEY`. For Claude Code and ChatGPT, start a new conversation after installation and complete the CiteGuild OAuth flow on the first tool call. The plugin searches opted-in member articles; it does not turn CiteGuild into broad web search or promise reciprocal placement.

New accounts receive an API key automatically. The dashboard reveals the
**Connect an AI agent** prompt after the first site is submitted, but redacts the
key from the page and its HTML. The authenticated **Copy prompt** action fetches
the full prompt, including the key, from a private non-cacheable endpoint. Share
that copied prompt only with an agent you trust.

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

Codex uses the API key embedded in the protected copied prompt. The prompt stores
it as `CITEGUILD_API_KEY` in `~/.codex/.env`; the official plugin reads that
environment variable as a bearer token after Codex restarts. Other clients can
still use an API key when configured explicitly. Never hardcode it into source
control or paste the copied prompt into an untrusted agent.

- `X-API-Key: <api_key>`
- `Authorization: Bearer <api_key>`

API keys are intentionally not accepted in query strings.

Use **Settings** to rotate the API key if it may have been exposed. Rotation
immediately revokes the previous value, so copy the updated agent prompt into
every client that still needs access. Never put a key in source control, a URL,
support message, screenshot, or log.

### Provider-neutral setup

1. Copy the protected dashboard prompt and paste it into a trusted clean agent session.
2. In Codex, let the prompt install the plugin and store `CITEGUILD_API_KEY` in
   `~/.codex/.env`; restart before verification.
3. In another local client, export `CITEGUILD_API_KEY` and configure an
   `Authorization: Bearer` header through the client's environment-variable
   mechanism, or use OAuth when it is reliable.
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

The official Codex plugin already declares `CITEGUILD_API_KEY` as its bearer
token source. The protected copied prompt writes the key to `~/.codex/.env`,
which desktop and IDE clients can load after restart. No duplicate standalone
MCP entry is needed.

```text
CITEGUILD_API_KEY=<copied securely from the CiteGuild dashboard prompt>
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

Export `CITEGUILD_API_KEY` before starting Claude Code, approve the project MCP server, and use `/mcp` to verify the connection. The official Claude Code plugin continues to use OAuth by default.

## Give this prompt to a coding agent

```text
{{ agent_setup_prompt }}
```

## Deployment note

MCP uses ASGI. The generated server command runs `gunicorn citeguild.asgi:application` with `uvicorn_worker.UvicornWorker` when MCP is enabled.
