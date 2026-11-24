# CiteGuild CLI

`citeguild` lets OpenClaw, Hermes, shell agents, and scripts search CiteGuild's
active member articles through the authenticated v1 API. Search results are
candidate sources, not endorsements: read a result before citing it and never
force a link.

## Install

With Go 1.25 or newer, install this pinned source revision in Bash:

```bash
mkdir -p "$HOME/.local/bin"
GOBIN="$HOME/.local/bin" go install github.com/LVTD-LLC/citeguild/cli/cmd/citeguild@v0.0.0-20260804142406-836452f5fbc0
export PATH="$HOME/.local/bin:$PATH"
export CITEGUILD_API_BASE=https://citeguild.com/api
citeguild config status
```

Check that the API base is `https://citeguild.com/api` before supplying a key.
This pinned build defaults to the former host. Keep the API base and PATH in
the environment that starts your agent.

## Authenticate

Create or rotate an API key from CiteGuild settings. The key is shown once.
Export it in the shell that runs the agent; do not pass it as a flag, put it in
a URL, or commit it to a config file.

Paste the key at the prompt and press Enter. The terminal will not echo it.

```bash
read -rsp "CiteGuild API key: " CITEGUILD_API_KEY
printf '\n'
export CITEGUILD_API_KEY
citeguild config status
citeguild auth status
```

The current source defaults to the production API. Override it for a trusted development or
staging service with `--api-base` or `CITEGUILD_API_BASE`. Explicit flags win
over environment values; environment values win over built-in defaults.

## Search

Flags must appear before the query. Quote a draft passage when it should remain
one shell argument. Use `--` before a query that begins with a hyphen.

```bash
citeguild search --limit 5 --language en \
  --exclude-domain my-site.example \
  "How do Django transaction commit hooks work?"
```

Human output is the default. Agents and scripts should request the stable v1
response on stdout:

```bash
citeguild search --json --limit 5 "Django transaction hooks" | jq '.results'
```

Diagnostics go to stderr, and structured mode never prompts or emits terminal
styling. With `--json`, failures emit one JSON object on stderr containing
`code`, `message`, optional `request_id` and `retry_after_seconds`, `retryable`, and `exit_code`, while
stdout remains empty. `CITEGUILD_TIMEOUT` or `--timeout` accepts Go durations such as `5s`
or `1m`; the default total request budget is 15 seconds.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success, requested help, or a normal closed output pipe |
| `1` | Unexpected internal CLI failure |
| `2` | Invalid CLI input or API validation failure |
| `3` | Missing, invalid, or unauthorized credential |
| `4` | Network or timeout failure |
| `5` | CiteGuild server, rate-limit, or response-protocol failure |
| `130` | Interrupted request |

Errors may include a safe request ID for support. The CLI never prints the API
key, Authorization header, search request body, or raw unexpected server body.

## Develop and release

From a source checkout, run `make cli-install-smoke` to test installation without changing your normal Go binary directory.

```bash
make cli-quality
```

The Go module is dependency-free and declares Go 1.25 compatibility. Tagged
releases use a pinned Go toolchain to build and smoke-test final Linux amd64 and macOS arm64
binaries on native GitHub-hosted runners, then package reproducible archives.
The release workflow accepts only `cli/vX.Y.Z` tags whose commit is on `main`,
builds each final binary once, and publishes checksums without overwriting an
existing release.
