# Generated App Flows

Use this tour to orient before changing common generated-project flows.

## Quality Contract

Entrypoints:

- `docs/quality.md`
- `Makefile`
- `.github/workflows/ci.yml`
What to check:

- `make ci-local` should remain the broad local path.
- Touched-area commands in `docs/quality.md` should map to real Makefile
  targets.
- CI should call the same targets where practical.
- Optional checks should explain their baseline policy, especially coverage and
  type checking.

Common footguns:

- Adding a CI-only check with no local equivalent.
- Documenting a command that does not exist.
- Making a noisy type or coverage gate mandatory before a project has a useful
  baseline.

## Web Request to Template

Entrypoints:

- `citeguild/urls.py`
- `apps/pages/urls.py`
- `apps/core/urls.py`
- `frontend/templates/`

Flow:

1. Top-level URLs include app URL modules.
2. App views prepare context or handle forms.
3. Templates render the page or HTMX partial.
4. Browser modules in `frontend/src/js/` add shared DOM behavior.
5. Tailwind styles come from `frontend/src/styles/index.css`.

Checks:

- `make pytest-check -- apps/pages apps/core -q`
- `make frontend-check`
- `make template-check`

Common footguns:

- Putting business logic in templates.
- Adding HTMX behavior without server-side validation.
- Changing templates without checking dark mode, empty states, and errors.

## Auth, Profile, and Settings

Entrypoints:

- `citeguild/adapters.py`
- `apps/core/models.py`
- `apps/core/signals.py`
- `apps/core/forms.py`
- `apps/core/views.py`
- `frontend/templates/account/`
- `frontend/templates/pages/user-settings.html`
- `apps/core/tests/`

Flow:

1. django-allauth owns login, signup, email verification, passkeys, MFA, and
   password flows.
2. Core adapters, signals, forms, and views add project-specific behavior.
3. Profile state and settings-page actions live in `apps/core`.
4. Templates must preserve allauth-compatible form and redirect behavior.

Checks:

- `make pytest-check -- apps/core -q`
- `make django-check`
- `make frontend-check` when templates change

Common footguns:

- Breaking passkey or MFA templates while changing normal login/signup.
- Adding signup behavior that ignores `ALLOW_SIGNUPS`.
- Logging verification codes, reset tokens, or API keys.

## Django Ninja API

Entrypoints:

- `apps/api/urls.py`
- `apps/api/views.py`
- `apps/api/schemas.py`
- `apps/api/auth.py`
- `apps/api/services.py`
- `apps/api/tests.py`

Flow:

1. `apps/api/views.py` owns the central Ninja API object.
2. Schemas define request and response contracts.
3. Auth classes resolve the request subject.
4. Service functions own reusable behavior.
5. Tests should cover auth, validation, success, and error paths.

Checks:

- `make pytest-check -- apps/api -q`
- `make django-check`
- `make type-check`

Common footguns:

- Returning model fields that the response schema should hide.
- Letting operation functions grow instead of using services.
- Adding behavior to REST without updating another surface that shares the same
  service.

## Background Jobs

Entrypoints:

- `apps/core/tasks.py`
- `citeguild/settings.py`
- `Makefile`
- `deployment/entrypoint.sh`

Flow:

1. Web code enqueues importable task functions.
2. Django Q2 workers run `manage.py qcluster`.
3. Redis is the normal broker; tests can use the ORM broker fallback.
4. Deployment chooses server or worker behavior through `APP_PROCESS_TYPE`.

Checks:

- `make pytest-check -- apps/core -q`
- `make django-check`
- `make terminal-worker` only when testing real worker behavior locally

Common footguns:

- Passing model instances instead of durable IDs.
- Enqueueing before a transaction commits.
- Creating duplicate schedules without a stable name.
- Letting server and worker use different `Q_CLUSTER_NAME` values.

## Stripe Billing

Entrypoints:

- `apps/core/stripe_webhooks.py`
- `apps/core/models.py`
- `apps/core/tests/test_stripe_webhooks.py`
- `frontend/templates/pages/pricing.html`
- `apps/api/schemas.py`

Flow:

1. Stripe Checkout or billing portal sends users to Stripe.
2. Stripe webhooks update profile subscription state.
3. API and templates expose only safe billing state.

Checks:

- `make pytest-check -- apps/core/tests/test_stripe_webhooks.py apps/api -q`
- `make django-check`

Common footguns:

- Non-idempotent webhook handling.
- Trusting client-side billing state.
- Leaving Stripe imports or docs behind when a template option disables Stripe.

## Hosted MCP

Entrypoints:

- `apps/mcp_server/server.py`
- `apps/mcp_server/auth.py`
- `apps/mcp_server/oauth.py`
- `apps/mcp_server/tests/`
- `apps/api/services.py`

Flow:

1. MCP clients authenticate through OAuth or legacy API-key headers.
2. Tools should call shared services where behavior overlaps with REST.
3. REST and MCP should agree on response semantics for shared behavior.

Checks:

- `make pytest-check -- apps/mcp_server apps/api -q`
- `make django-check`

Common footguns:

- Duplicating behavior in MCP instead of using a shared service.
- Logging bearer tokens or API keys.
- Updating REST behavior without MCP parity coverage.

## User-Facing Docs

Entrypoints:

- `apps/pages/content/docs/`
- `apps/pages/content/docs/navigation.yaml`
- `apps/pages/views.py`
- `frontend/templates/pages/docs/`
- `apps/pages/test_docs.py`
- `apps/pages/content/AGENTS.md`

Flow:

1. Markdown content and navigation define docs pages.
2. Docs views render content through Django templates.
3. Templates provide page chrome, copy buttons, and noindex metadata.

Checks:

- `make pytest-check -- apps/pages/test_docs.py -q`
- `make frontend-check` when docs templates or JS change

Common footguns:

- Adding docs content without navigation.
- Rendering unsafe template syntax from docs content.
- Forgetting content-specific guidance in `apps/pages/content/AGENTS.md`.

## External Dependencies and Builds

Entrypoints:

- `pyproject.toml`
- `uv.lock`
- `package.json`
- `package-lock.json`
- `deployment/`
- `.github/workflows/ci.yml`
Flow:

1. Runtime imports require direct runtime dependencies.
2. Frontend imports require lockfile-backed npm installs.
3. Deployment images should use the same dependency graph as CI.

Checks:

- `uv sync --locked`
- `npm ci` when frontend dependencies changed
- `make django-check`
- `make frontend-check`
- Relevant Docker or deployment syntax/build check when deployment changed

Common footguns:

- Relying on transitive packages for direct imports.
- Updating `package.json` without `package-lock.json`.
- Testing only the host path when deployment imports a different module.
