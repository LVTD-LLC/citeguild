---
title: CLI access
---

# Search CiteGuild from a CLI agent

The `citeguild` command gives OpenClaw, Hermes, shell agents, and scripts a
small authenticated search interface with readable or stable JSON output. It
uses the same v1 search contract as the API and MCP server.

Search results are candidate sources, not endorsements. Open and verify a
result before citing it; never force a link because CiteGuild returned it.

## Install the command

Download the archive for Linux amd64 or macOS arm64 from the
[CiteGuild releases page](https://github.com/LVTD-LLC/citeguild/releases) and
verify it with the published `checksums.txt` file.

With Go 1.25 or newer, you can install a pinned release directly:

```bash
go install github.com/LVTD-LLC/citeguild/cli/cmd/citeguild@v0.1.0
```

## Keep authentication out of command history

Create or rotate an API key in **Settings**. The key is shown once. Export it in
the shell that starts your agent:

```bash
export CITEGUILD_API_KEY="<copy the key from CiteGuild settings>"
citeguild config status
citeguild auth status
```

`config status` reports whether the key is set but never prints its value.
`auth status` verifies the key against CiteGuild. A rotation immediately
revokes the previous key, so restart or update every agent that still needs
access.

## Search for useful sources

Put options before the query. Use `--` before a query that begins with a
hyphen:

```bash
citeguild search --limit 5 --language en \
  --exclude-domain my-site.example \
  "How do Django transaction commit hooks work?"
```

For an agent or script, request JSON and parse stdout:

```bash
citeguild search --json --limit 5 "Django transaction hooks" | jq '.results'
```

The response contains the v1 contract version and public citation fields:
article ID, title, canonical URL, domain, excerpt, relevance, language, and
last-seen timestamp. Diagnostics use stderr, so they do not corrupt JSON. With
`--json`, a failure is one JSON object with `code`, `message`, optional
`request_id` and `retry_after_seconds`, `retryable`, and `exit_code`. Automated
callers should wait at least that many seconds before retrying.

## Recover from failures

The exit code identifies the next action:

- `2`: fix the command options or request validation error.
- `3`: export a current API key or check its account permissions.
- `4`: check the network, API URL, and timeout.
- `5`: retry only when appropriate; a rate limit or CiteGuild dependency may be
  unavailable. Keep any printed request ID for support.
- `130`: the request was interrupted.

Run `citeguild <command> --help` for all options. Override the production API
only for a trusted development or staging service with `--api-base` or
`CITEGUILD_API_BASE`. Set the total request budget with `--timeout` or
`CITEGUILD_TIMEOUT`, using values such as `5s` or `1m`.
