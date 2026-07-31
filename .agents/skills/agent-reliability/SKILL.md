---
name: agent-reliability
description: "Use when planning, implementing, testing, reviewing, or evaluating agent-driven changes in this generated Django SaaS app, especially changes that cross Django apps, API surfaces, background jobs, frontend templates, docs, CI, or optional integrations."
---

# Agent Reliability

Use this workflow to make agent work reproducible, reviewable, and easy to
verify. The goal is not more prose. The goal is a short path from task framing
to executable checks.

## First Pass

1. Read `AGENTS.md`, `docs/quality.md`, and the files around the requested
   change.
2. If the change fits a task template, read `docs/agent-task-templates.md`.
3. If the change touches a known flow, read `docs/code-tours/README.md` and the
   relevant tour before editing.
4. Identify every public surface the behavior reaches: Django view, template,
   Django Ninja endpoint, background task, management command, docs page,
   optional MCP tool, or deployment workflow.
5. Choose the smallest verification set from `docs/quality.md` before writing
   code.

## Reliability Loop

For each behavior change:

1. Map the flow from entrypoint to persistence and side effects.
2. Name the behavior kernel. This is usually a service function, form, model
   method, task function, or schema boundary that several surfaces rely on.
3. Add or update tests at the lowest useful layer, then add one integration or
   parity test when multiple surfaces share the same kernel.
4. Run targeted checks while iterating.
5. Run broader checks before finishing.
6. Update docs, code tours, task templates, or eval seeds when the change
   changes how future agents should work.

## High-Risk Signals

Treat these as reasons to slow down and add guardrails:

- One change crosses API, templates, docs, background jobs, settings, or
  deployment files.
- REST, MCP, web views, or tasks share the same service behavior.
- A large file is both high-churn and behavior-heavy.
- Auth, permissions, billing, public sharing, or destructive actions are in the
  flow.
- A dependency, import path, package lock, Docker image, or runtime service is
  involved.
- Tests require broad setup or duplicate the same object creation repeatedly.
- Optional Cookiecutter features can remove files that another path imports.

## Tests

- Prefer real Django objects for local domain behavior.
- Use factories or shared fixtures for common users, profiles, API keys,
  projects, owned records, and request state.
- Split very large test modules by behavior area before adding more unrelated
  cases to them.
- Add characterization tests before extracting or reshaping a behavior kernel.
- For multiple surfaces that should agree, add parity tests. Examples: Django
  view and service, REST and service, MCP and REST, task and service.
- Mock only slow, external, nondeterministic, or hard-to-trigger boundaries.
  Use Django settings helpers, specific fakes, or interface-checked mocks.

## Coverage

Coverage is a map, not a quality score.

- Use `make coverage-high-risk` to see whether important files are being
  exercised.
- Raise `COVERAGE_FAIL_UNDER` only after the project has a known baseline.
- Prefer behavior tests around risky paths over chasing global percentage.
- If coverage highlights an undertested hot path, add a focused regression or
  characterization test.

## Mutation Testing

- Use `make mutation-high-risk -- '<module-or-function-pattern>'` after the
  focused pytest suite passes when you need evidence that assertions detect
  broken logic.
- Inspect survivors with `make mutation-results`.
- Add a behavior-focused test for a meaningful surviving mutant, then rerun the
  narrow mutation pattern.
- Do not couple tests to implementation details merely to kill equivalent or
  irrelevant mutants.
- Keep mutation testing opt-in; it is too slow for the default local and
  per-commit CI paths.

## Type Checking

- Run `make type-check` for type visibility.
- Keep typed scopes low-noise and expand them intentionally.
- Add typed boundaries where they clarify dictionaries, JSON-like data, schema
  inputs, service return values, or task payloads.
- Do not silence type errors broadly to make a gate pass.

## Agent Evals

Use `docs/agent-evals/seed-tasks.md` to keep a small set of repeatable tasks for
agent evaluation.

Good eval seeds include:

- Setup contract and starting assumptions.
- Expected files or surfaces to inspect.
- Fail-to-pass checks that prove the change.
- Pass-to-pass checks that protect existing behavior.
- Trace notes describing common mistakes to mine back into docs or tests.

When an agent fails a seed task, fix the durable gap: missing test, vague task
template, stale code tour, unclear command matrix, or weak runtime guardrail.

## Done Means

- The change is implemented in the right app or template layer.
- Relevant targeted tests pass.
- `docs/quality.md` commands selected for the touched area have run.
- Shared surfaces have parity or integration coverage when appropriate.
- New or changed workflows are reflected in docs or generated guidance.
- No secrets, machine-local paths, or vendor-specific agent assumptions were
  added.
