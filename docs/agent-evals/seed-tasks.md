# Agent Evaluation Seed Tasks

Use these seeds to evaluate whether coding agents can make common changes
safely. Each seed should be turned into a concrete task with a starting commit,
expected files, fail-to-pass checks, pass-to-pass checks, and trace notes.

Keep the set small. When an agent fails, improve the durable guardrail: test,
task template, code tour, command matrix, or runtime validation.

## Seed 1: Quality Contract Drift

Goal: add or rename a Makefile quality target and keep all guidance aligned.

Expected files:

- `Makefile`
- `docs/quality.md`
- `.github/workflows/ci.yml`
- `AGENTS.md`

Fail-to-pass checks:

- The new target exists and runs.
- `docs/quality.md` references the real target name.
- CI calls the same target when the check is mandatory.
Pass-to-pass checks:

- `make python-quality`
- `make django-check`

Trace notes:

- Watch for CI-only checks with no local path.
- Watch for stale command names in docs.

## Seed 2: New API Field

Goal: add a safe field to an API response without exposing private data.

Expected files:

- `apps/api/schemas.py`
- `apps/api/services.py`
- `apps/api/views.py`
- `apps/api/tests.py`

Fail-to-pass checks:

- API tests prove the new field appears for the right user.
- Auth failure and ownership boundaries still pass.

Pass-to-pass checks:

- `make pytest-check -- apps/api -q`
- `make django-check`

Trace notes:

- Watch for leaking password hashes, API-key hashes, billing IDs, or internal
  state.

## Seed 3: Shared Service Behavior

Goal: change a service function used by more than one surface and keep callers
aligned.

Expected files:

- Owning service module.
- All views, API endpoints, tasks, or optional tools that call the service.
- Tests for each public surface.

Fail-to-pass checks:

- Focused service tests prove the new behavior.
- One integration or parity test proves shared callers still agree.

Pass-to-pass checks:

- `make pytest-check -- <affected apps> -q`
- `make coverage-high-risk -- <affected apps> -q`

Trace notes:

- Watch for updating one surface while another still expects old semantics.

## Seed 4: HTMX Form Flow

Goal: add or change an HTMX-backed form while preserving normal Django
validation.

Expected files:

- `apps/*/forms.py`
- `apps/*/views.py`
- `frontend/templates/`
- Relevant tests.

Fail-to-pass checks:

- Valid submit updates state.
- Invalid submit returns form errors.
- Non-HTMX fallback still works if the route supports it.

Pass-to-pass checks:

- `make frontend-check`
- `make pytest-check -- <affected app> -q`

Trace notes:

- Watch for browser-only validation with no server-side check.

## Seed 5: Background Task Side Effect

Goal: add a task that runs after a model change and is safe to retry.

Expected files:

- `apps/core/tasks.py`
- Calling view/form/service.
- Tests for direct task behavior and enqueueing.

Fail-to-pass checks:

- Task function works when called directly with durable IDs.
- Enqueueing happens after commit when needed.
- Retry does not duplicate durable side effects.

Pass-to-pass checks:

- `make pytest-check -- apps/core -q`
- `make django-check`

Trace notes:

- Watch for passing model instances or creating schedules at import time.

## Seed 6: REST and MCP Parity

Goal: add a behavior that both REST and MCP expose.

Expected files:

- `apps/api/services.py`
- `apps/api/views.py`
- `apps/mcp_server/server.py`
- `apps/mcp_server/tests/`
- `apps/api/tests.py`

Fail-to-pass checks:

- REST test proves the behavior.
- MCP test proves the same semantics.
- Parity test compares key response fields or errors.

Pass-to-pass checks:

- `make pytest-check -- apps/api apps/mcp_server -q`

Trace notes:

- Watch for copying business logic into MCP instead of calling a shared service.

## Seed 7: Stripe Webhook Regression

Goal: adjust subscription behavior without making webhooks non-idempotent.

Expected files:

- `apps/core/stripe_webhooks.py`
- `apps/core/tests/test_stripe_webhooks.py`
- Any exposed API or template billing state.

Fail-to-pass checks:

- Replaying the same webhook does not duplicate state.
- Out-of-order or missing fields fail safely.

Pass-to-pass checks:

- `make pytest-check -- apps/core/tests/test_stripe_webhooks.py -q`
- `make django-check`

Trace notes:

- Watch for trusting client-side billing status.

## Seed 8: Dependency Import Smoke

Goal: add a runtime import and prove clean installs can import it.

Expected files:

- `pyproject.toml`
- `uv.lock`
- Importing module.
- `.github/workflows/ci.yml` when the check path changes.
Fail-to-pass checks:

- `uv sync --locked` succeeds.
- The importing module can be imported under test settings.

Pass-to-pass checks:

- `make django-check`
- Focused tests for the importing feature.

Trace notes:

- Watch for transitive dependencies used as direct imports.

## Seed 9: Docs Navigation

Goal: add a docs page and keep navigation, rendering, and scoped instructions
aligned.

Expected files:

- `apps/pages/content/docs/`
- `apps/pages/content/docs/navigation.yaml`
- `apps/pages/test_docs.py`
- `apps/pages/content/AGENTS.md` when guidance changes.

Fail-to-pass checks:

- The docs route renders.
- Navigation includes the new page.

Pass-to-pass checks:

- `make pytest-check -- apps/pages/test_docs.py -q`
- `make frontend-check` when docs templates or JS change.

Trace notes:

- Watch for docs content that assumes secrets, local paths, or one specific
  agent vendor.

## Seed 10: Agent Guidance Update

Goal: change project workflow guidance and keep it concise, tool-neutral, and
testable.

Expected files:

- `AGENTS.md`
- `.agents/skills/`
- `docs/quality.md`
- `docs/agent-task-templates.md`
- `docs/code-tours/`

Fail-to-pass checks:

- Guidance names exact files and commands.
- No vendor-specific instruction files are introduced.
- Optional feature guidance is gated by generated project structure.

Pass-to-pass checks:

- Rendered project contains the guidance files.
- `make python-quality` when Markdown or generated output checks are in scope.

Trace notes:

- Watch for broad "best practices" text that does not tell future agents what
  to inspect or run.
