# Quality Commands

This is the command contract for local verification, CI mapping, and
touched-area checks. Use it before adding new quality gates so humans and coding
agents run the same commands.

## Full Local CI Path

For a host-level run that mirrors the generated CI gates, prepare the terminal
environment once, then run the local quality path:

```bash
cp .env.terminal.example .env  # first local run only; edit database values as needed
make terminal-setup
make ci-local
```

`make ci-local` runs, in order:

1. `make python-quality`
2. `make type-check`
3. `make frontend-check`
4. `make cli-quality`
5. `make security-check`
6. `make migrations-check`
7. `make django-check`
8. `make coverage-high-risk -- -q`

This path expects the same host prerequisites as terminal development: uv,
Node.js, Go 1.25 or newer, a reachable PostgreSQL database, and Redis when
runtime settings need it. Use `make test` when you want Docker Compose to manage the full local stack,
or `make test-local-postgres` when an MCP-capable agent has created a disposable
PGSandbox database.

## Targeted Command Matrix

| Touched area | Run this first | Add when relevant |
| --- | --- | --- |
| Python imports, style, generated templates, static analysis | `make python-quality` | `make lint-python`, `make format-check`, `make template-check`, or `make pyscn-analyze` while iterating |
| Models or migrations | `make migrations-check` | `make terminal-makemigrations` or `make makemigrations` only when model changes are intentional, then inspect the generated migration |
| Django views, forms, services, auth, profiles, background jobs | `make pytest-check -- <pytest path or -k filter>` | `make django-check` and `make migrations-check` before PR |
| API schemas, auth, services, or routers | `make pytest-check -- apps/api -q` | Run `make api-fuzz` for the OpenAPI-derived contract test; read `.agents/skills/django-ninja/SKILL.md` before larger API changes |
| Django Q2 tasks, schedules, workers, or broker behavior | `make pytest-check -- apps/core -q` | Read `.agents/skills/django-q2/SKILL.md`; run a worker locally when behavior depends on the queue |
| HTMX, Alpine.js, templates, Tailwind, or browser modules | `make frontend-check` | Read the matching frontend skill; run targeted Django tests for changed views or forms |
| Go CLI commands, API client, output, or release packaging | `make cli-quality` | Run a built binary against an isolated `httptest` fixture while iterating; tagged artifacts are smoke-tested natively by `.github/workflows/cli-release.yml` |
| Shared services or high-risk behavior kernels | `make coverage-high-risk -- <affected pytest args>` | After tests pass, run `make mutation-high-risk -- '<module-or-function-pattern>'` when test strength matters |
| Cross-component MVP acceptance | `make acceptance-test -- -q` with PostgreSQL, Redis, and Qdrant configured | See `docs/quality/mvp-acceptance.md` for the matrix and budgets |
| Locked dependency security | `make security-check` | High-severity npm runtime findings or any known Python vulnerability fail the command |
| Docs, README, or agent instructions | Review the rendered Markdown path | Run focused tests only when docs rendering, routes, or navigation changed |
| Deployment, Docker, CapRover, Fly.io, or DigitalOcean config | Run the smallest changed deploy command or syntax check available | Read the relevant deployment skill/docs and run `make ci-local` before PR |
| Disposable Postgres verification | `DATABASE_URL="<pgsandbox connection string>" make test-local-postgres` | Delete the sandbox after checks and never commit sandbox URLs |
| Typed baseline | `make type-check` | Expand `TYPE_CHECK_PATHS` deliberately as a module becomes low-noise |

## Property-based tests

Hypothesis runs as part of the normal pytest suite. Use it when behavior can be
expressed as an invariant, round trip, parser contract, normalization rule, or
state transition across a broad input space. Keep named example tests for
specific business rules and regressions.

Start with the generated API-key property test:

```bash
make pytest-check -- apps/core/tests/test_api_keys.py -q
```

To reproduce a failure from its reported seed:

```bash
make pytest-check -- --hypothesis-seed=<seed> path/to/test_file.py -q
```

Read `.agents/skills/property-based-testing/SKILL.md` before adding
database-backed properties; they require Hypothesis's Django test classes
rather than a plain `@pytest.mark.django_db` test.

## Command Reference

| Command | Purpose |
| --- | --- |
| `make python-quality` | Runs pre-commit across the repo, including Ruff's explicit cyclomatic-complexity limit of 10, then `make pyscn-check`. |
| `make frontend-check` | Runs `npm run lint` and `npm run build`. |
| `make cli-quality` | Runs Go formatting, vet, unit tests, race tests, build, and isolated install smoke for the CLI. |
| `make migrations-check` | Runs `manage.py makemigrations --check --dry-run`. |
| `make django-check` | Runs Django system checks. |
| `make pytest-check -- <args>` | Runs pytest on the host with optional pytest args. |
| `make api-fuzz` | Runs Schemathesis property tests directly against the Django WSGI app using the generated OpenAPI schema and test-owned authentication. |
| `make acceptance-test` | Runs the opt-in paid-site scenario and Redis check against real PostgreSQL, Redis, and Qdrant services. |
| `make security-check` | Audits the locked Python runtime graph and npm runtime dependencies without live provider calls. |
| `make coverage` | Runs pytest through coverage and reports overall coverage. |
| `make coverage-high-risk` | Runs pytest through coverage and reports selected high-risk files. Defaults to `COVERAGE_FAIL_UNDER=0` until the project sets a baseline. |
| `make mutation-high-risk` | Runs mutmut against the configured high-risk Python files, optionally narrowed by a module or function pattern. |
| `make mutation-results` | Lists mutation outcomes, including surviving mutants that may reveal weak assertions. |
| `make test -- <args>` | Runs pytest through Docker Compose. |
| `make test-local-postgres -- <args>` | Runs migration, Django, and pytest checks against a disposable PGSandbox database. |
| `make lint-python` | Runs Ruff lint checks without applying fixes. |
| `make format-check` | Runs Ruff format check without rewriting files. |
| `make template-check` | Runs djLint in check mode for Django templates. |
| `make type-check` | Runs ty inside the locked project environment over the low-noise typed baseline. |

## Coverage Baseline Policy

`make coverage-high-risk` reports coverage for files that tend to concentrate
important behavior in a fresh generated project:

- `apps/api/services.py`
- `apps/api/views.py`
- `apps/core/models.py`
- `apps/core/utils.py`
- `apps/core/views.py`

Coverage is a visibility tool, not a global quality score. The generated
default is `COVERAGE_FAIL_UNDER=0` so fresh projects get a report without a
fake threshold. Once the project has meaningful tests around its own high-risk
paths, set a real floor in CI or on a branch:

```bash
make coverage-high-risk COVERAGE_FAIL_UNDER=75
```

Prefer adding behavior, parity, and regression tests around risky flows over
chasing percentage for its own sake.

## Mutation Testing Workflow

Mutation testing changes covered production expressions and checks that the
test suite fails. It answers a different question from coverage: not only
"did a test execute this line?" but "would a test notice broken logic here?"

The generated mutmut configuration starts with two compact behavior-kernel
modules: `apps/api/services.py` and `apps/core/utils.py`. Expand
`tool.mutmut.only_mutate` deliberately as the project develops more
well-isolated service code. The helper plugin in `mutmut_config.py` makes
mutmut's copied modules win over modules Django imports during pytest startup.
The tool copies the pytest configuration, root fixtures, and frontend resources
into the ignored `mutants/` workspace while inheriting the current process
environment. Run it only from a trusted project checkout and never commit the
generated workspace.

Start with a focused behavior kernel:

```bash
make mutation-high-risk -- 'apps.core.utils.*'
make mutation-results
```

Run `make mutation-high-risk` without a pattern when you want the full
configured high-risk set. A surviving mutant is a prompt to inspect the
behavior and strengthen a focused test when the mutation represents a real
defect. Equivalent or irrelevant mutants should be documented or excluded
narrowly; do not add assertions that merely mirror implementation details.

Mutation testing is intentionally not part of `make ci-local` or the generated
per-commit CI workflow because it is much slower than pytest. Use it before
risky refactors, after changing shared behavior kernels, or as a scheduled
quality exercise. Mutmut requires fork support, so Windows contributors should
run it in WSL.

## API Property Tests

`apps/api/test_schema.py` is the API contract layer: Schemathesis derives
requests from Django Ninja's OpenAPI schema, sends them directly through the
Django WSGI app, and validates that responses do not fail with server errors
and that successful responses conform to the documented schema. The test uses
a database-backed profile fixture and a test-owned API key, so it can exercise
authenticated endpoints without external credentials or a live server.
Generation is intentionally limited to schema-valid requests because the
starter advertises two alternative authentication schemes; malformed and
missing credential cases stay in focused authentication tests where each
alternative can be asserted precisely.

The default 25 examples per operation keep this integration check suitable for
the normal pytest and CI feedback loop. Run it alone while changing API schemas,
authentication, services, or routers:

```bash
make api-fuzz
```

Keep focused Django tests for exact business rules and permission cases.
Schemathesis complements those tests by exploring the wider OpenAPI input
space; it does not replace endpoint-specific assertions.

## Complexity Policy

Ruff fails `make python-quality` with `C901` when a function's cyclomatic
complexity exceeds 10. Prefer extracting cohesive helpers or simplifying the
control flow over adding a `noqa` suppression. Pyscn remains a complementary
structural check with its own complexity metric and a limit of 15.

## CI Mapping

The generated GitHub Actions workflow at `.github/workflows/ci.yml` calls the
same Makefile targets:

```bash
make python-quality
make type-check
make frontend-check
make cli-quality
make security-check
make migrations-check
make django-check
make coverage-high-risk COVERAGE_FAIL_UNDER=0 -- -q
```

CI exports test environment variables and runs against the PostgreSQL service
defined in the workflow. Local development reads `.env`, so use
`.env.terminal.example` for host-level checks or Docker Compose commands when
you want Compose-managed services.
