# Agent Task Templates

Use these templates to frame agent work before editing. Delete sections that do
not apply in the final task prompt, but keep setup, expected files, and checks
explicit.

## Django Model or Service Change

Use for domain logic, model fields, forms, shared helpers, and behavior kernels.

```markdown
Goal:

Context:
- Read `AGENTS.md`, `docs/quality.md`, and `docs/code-tours/generated-app-flows.md`.
- Inspect:
  - `apps/core/models.py`
  - `apps/core/forms.py`
  - `apps/core/views.py`
  - `apps/core/tests/`
  - Any app that owns the changed behavior.

Implementation notes:
- Keep reusable business logic in services, forms, model methods, or utilities,
  not templates.
- If models change, run `uv run python manage.py makemigrations` without app
  labels and inspect the migration.
- Use factories or shared fixtures when repeated setup appears.

Checks:
- `make pytest-check -- <focused test path> -q`
- `make migrations-check` when models changed
- `make django-check`
- `make python-quality`
```

## Django Ninja API Change

Use for new endpoints, schemas, auth changes, routers, and API tests.

```markdown
Goal:

Context:
- Read `.agents/skills/django-ninja/SKILL.md`.
- Inspect:
  - `apps/api/views.py`
  - `apps/api/schemas.py`
  - `apps/api/services.py`
  - `apps/api/auth.py`
  - `apps/api/tests.py`

Implementation notes:
- Add explicit request and response schemas.
- Keep operation functions thin; put reusable behavior in services.
- Test success, validation errors, auth failures, and ownership/permission
  boundaries.
- If another surface uses the same behavior, add a parity test.

Checks:
- `make pytest-check -- apps/api -q`
- `make django-check`
- `make type-check`
```

## Template, HTMX, Alpine.js, or Tailwind Change

Use for frontend templates, partials, browser modules, styles, and UI states.

```markdown
Goal:

Context:
- Read `.agents/skills/frontend-ui-quality/SKILL.md`.
- Read `.agents/skills/django-htmx/SKILL.md` when HTMX is involved.
- Read `.agents/skills/alpinejs-django/SKILL.md` when Alpine.js is involved.
- Inspect:
  - `frontend/templates/`
  - `frontend/src/js/`
  - `frontend/src/styles/`
  - The Django view/form that renders the UI.

Implementation notes:
- Keep server validation as the source of truth.
- Use HTMX for server-rendered updates and Alpine.js for browser-local state.
- Check light and dark mode, empty states, errors, and responsive behavior.

Checks:
- `make frontend-check`
- `make pytest-check -- <view or form tests> -q`
- `make template-check`
```

## Background Task or Worker Change

Use for Django Q2 tasks, schedules, worker setup, retries, and broker behavior.

```markdown
Goal:

Context:
- Read `.agents/skills/django-q2/SKILL.md`.
- Inspect:
  - `apps/core/tasks.py`
  - `citeguild/settings.py`
  - Worker/deployment files if process behavior changes.

Implementation notes:
- Pass durable identifiers, not model instances.
- Enqueue after commit when task work depends on saved rows.
- Make task behavior idempotent.
- Test task logic directly and enqueueing separately.

Checks:
- `make pytest-check -- apps/core -q`
- `make django-check`
- Run a local worker only when behavior depends on real queue execution.
```

## MCP Tool Change

Use for hosted MCP tools, OAuth/API-key behavior, and REST/MCP parity.

```markdown
Goal:

Context:
- Inspect:
  - `apps/mcp_server/server.py`
  - `apps/mcp_server/auth.py`
  - `apps/mcp_server/tests/`
  - Shared API/service code used by the tool.

Implementation notes:
- Keep tool behavior on the same service layer as REST when possible.
- Never log or expose API keys or OAuth tokens.
- Add parity tests when REST and MCP should agree.

Checks:
- `make pytest-check -- apps/mcp_server apps/api -q`
- `make django-check`
```

## Docs, Skills, or Agent Guidance Change

Use for `AGENTS.md`, `docs/quality.md`, generated skills, code tours, and eval
seeds.

```markdown
Goal:

Context:
- Inspect:
  - `AGENTS.md`
  - `docs/quality.md`
  - `.agents/skills/`
  - `docs/code-tours/`
  - `docs/agent-task-templates.md`
  - `docs/agent-evals/seed-tasks.md`

Implementation notes:
- Keep durable guidance tool-neutral.
- Prefer exact files and commands over broad advice.
- Avoid machine-local paths, personal names, API keys, and vendor-specific
  setup.

Checks:
- Render or read the affected Markdown.
- Run tests only when docs rendering, navigation, or generated output changes.
```

## Dependency or Build Change

Use when adding packages, changing lockfiles, Docker images, imports, frontend
dependencies, or deployment build paths.

```markdown
Goal:

Context:
- Inspect:
  - `pyproject.toml`
  - `uv.lock`
  - `package.json`
  - `package-lock.json`
  - `deployment/`
  - `.github/workflows/`

Implementation notes:
- Add direct runtime dependencies for direct imports.
- Keep lockfiles in sync.
- Run import or build smoke checks that match production as closely as
  practical.

Checks:
- `uv sync --locked`
- `npm ci` when frontend dependencies changed
- `make django-check`
- `make frontend-check` when frontend assets changed
- Relevant Docker or deployment syntax/build check when deployment changed
```
