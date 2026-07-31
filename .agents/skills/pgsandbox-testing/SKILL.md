---
name: pgsandbox-testing
description: "Use when running Django checks, migrations, pytest, or database debugging against a disposable local Postgres database created by PGSandbox MCP."
---

# PGSandbox Testing

Use this skill when this project needs a real, disposable Postgres database for
tests, migration checks, SQL debugging, or reproducing database-specific bugs.

PGSandbox MCP is a local stdio MCP server for disposable Postgres databases. It
is installed outside this repository and is not a Python dependency of the app.
The project lives at <https://github.com/lvtd-llc/pgsandbox-mcp>.

Install it with Homebrew:

```bash
brew install lvtd-llc/tap/pgsandbox-mcp
```

Or use the GitHub install script:

```bash
curl -fsSL https://raw.githubusercontent.com/lvtd-llc/pgsandbox-mcp/main/scripts/install.sh | sh
```

After installation, run `pgsandbox-mcp setup` for the MCP client and restart the
client so the `pgsandbox` server is available.

## Agent Workflow

1. Verify that the MCP host exposes the `pgsandbox` server.
2. Create a sandbox database with the `create_database` MCP tool.
   - Use a short `nameHint`, for example `django-tests`.
   - Set a bounded `ttlMinutes`, for example `120`.
   - Include labels such as `project=<repository-name>` and `purpose=tests`
     when the MCP client supports labels.
3. Get the sandbox connection string from the `connectionString` field returned
   by `create_database`, or call `get_connection_string`.
4. Run the host-level test target with that URL in the environment:

```bash
DATABASE_URL="<pgsandbox connection string>" make test-local-postgres
```

5. Delete the sandbox with `delete_database` when the checks finish. If cleanup
   fails, report the `databaseId` or `databaseName` so a human can remove it.

The Make target runs migration drift checks, fakes the extension-only
`core.0001_enable_extensions` migration, applies the remaining migrations to
the disposable database, runs Django checks, and then loads the project's
guarded `conftest.py` database settings hook with `pytest --reuse-db` so
pytest-django uses the existing sandbox database instead of trying to create a
second `test_*` database.

The extension migration is faked only for this target because PGSandbox roles
are intentionally least-privilege and cannot create superuser-only extensions
such as `pg_stat_statements`. The Make target fails fast if the expected
extension migration file is missing; override `PGSANDBOX_EXTENSION_MIGRATION`
and `PGSANDBOX_EXTENSION_MIGRATION_FILE` if the migration is renamed. Use Docker
Compose or CI when you need to verify extension creation itself.

When `DJANGO_TEST_USE_EXISTING_DATABASE=1` is set, Django settings also switch
the default cache to local memory and Django Q2 to the ORM broker so this
database-focused target does not require Redis.

## Rules

- Do not commit sandbox connection strings, admin URLs, generated `.env` changes,
  or MCP client config files.
- Do not print full connection strings in summaries or logs; mask passwords.
- Do not use a shared development or production database for destructive tests.
- Prefer this workflow for migration and ORM behavior because it exercises the
  same Postgres backend the app uses in CI and production.
- Keep Docker Compose as the default full local stack. PGSandbox is for
  disposable database verification from an MCP-capable agent session.

## Useful Commands

Run only Django's system checks:

```bash
DATABASE_URL="<pgsandbox connection string>" \
ENVIRONMENT=test DEBUG=0 SECRET_KEY=test-secret-key SITE_URL=http://localhost:8000 \
uv run python manage.py check
```

Run only pytest:

```bash
DATABASE_URL="<pgsandbox connection string>" \
DJANGO_TEST_USE_EXISTING_DATABASE=1 \
PYTHONPATH=. \
uv run pytest --reuse-db -q
```

Inspect the configured database from Django:

```bash
DATABASE_URL="<pgsandbox connection string>" \
ENVIRONMENT=test DEBUG=0 SECRET_KEY=test-secret-key SITE_URL=http://localhost:8000 \
uv run python manage.py dbshell
```
