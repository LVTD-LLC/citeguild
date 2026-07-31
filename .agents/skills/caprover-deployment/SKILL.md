---
name: caprover-deployment
description: "Deploy generated Django SaaS Starter apps to CapRover with split server/worker apps."
---

# CapRover deployment

Use when deploying this generated Django SaaS Starter repo to CapRover, or when fixing the generated CapRover deploy workflow.

## Hard rules

- Use CapRover API, CapRover CLI, SSH, or GitHub/GH CLI only. Do not use the CapRover browser dashboard.
- GitHub Actions deploys must use per-app CapRover deploy tokens:
  - `APP_TOKEN` for the server app.
  - `WORKERS_APP_TOKEN` for the workers app.
  - Keep the CapRover API password/token for one-time admin provisioning only.
- The generated server and workers apps run the same Docker image. Process type is selected by `APP_PROCESS_TYPE`.
- Do not set `forceSsl` until the app has at least one SSL-enabled domain; CapRover rejects force SSL before SSL exists.
- Never print or commit deploy tokens, API passwords, `SECRET_KEY`, database passwords, OAuth secrets, or provider keys.

## Target app layout

Create or verify these CapRover apps. Use the `CAPROVER_APP_NAME` value from `.github/workflows/deploy.yml` for `citeguild`.

- `citeguild` — Django web server, `APP_PROCESS_TYPE=server`.
- `citeguild-workers` — Django Q/background worker, `APP_PROCESS_TYPE=worker`.
- `citeguild-postgres` — Postgres service.
- `citeguild-redis` — Redis service.

The GitHub workflow builds one GHCR image from `deployment/Dockerfile`, deploys it to the server app with `APP_TOKEN`, then deploys the same image to the workers app with `WORKERS_APP_TOKEN`.

## Provisioning checklist

1. Confirm the repo has `uv.lock`, `deployment/Dockerfile`, `deployment/entrypoint.sh`, and `.github/workflows/deploy.yml`.
2. Create the four CapRover apps/services above.
3. Configure persistent storage through CapRover app definitions for Postgres/Redis and any user-upload/media volume. Avoid one-off `docker service update --mount-add`; CapRover can overwrite it on redeploy.
4. Set server env vars:
   - `APP_PROCESS_TYPE=server`
   - `DJANGO_SETTINGS_MODULE=citeguild.settings` using the generated Python package slug.
   - `SECRET_KEY`, `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
   - `DATABASE_URL` pointing at `srv-captain--citeguild-postgres`
   - `REDIS_URL` pointing at `srv-captain--citeguild-redis`
   - project-specific provider keys from `.env.example`
5. Set workers env vars to match server, but with `APP_PROCESS_TYPE=worker`.
6. Create one deploy token for the server app and one for the workers app.
7. Set GitHub repository secrets/variables:
   - secret `CAPROVER_SERVER` — CapRover server URL.
   - secret `APP_TOKEN` — server app deploy token.
   - secret `WORKERS_APP_TOKEN` — workers app deploy token.
   - variable `WORKERS_APP_PROCESS_TYPE=worker` — safety guard for the workflow.
8. Push to `main` and verify the `Deploy Prod` workflow.
9. After the first successful deploy, enable HTTPS for the public domain, then enable force SSL.
10. Verify:
    - `https://<domain>/api/healthcheck` reports database and Redis healthy.
    - Server logs show migrations/static collection completed.
    - Workers logs show the worker process booted, not Gunicorn.

## Common fixes

- If the workers deploy fails at the guard step, set GitHub repo variable `WORKERS_APP_PROCESS_TYPE=worker` and ensure the workers CapRover app env has `APP_PROCESS_TYPE=worker`.
- If tasks never schedule after adding a bind volume through raw API, ensure the host path exists on the CapRover node or switch to a CapRover-managed persistent volume in the app definition.
- If the app starts before Postgres is ready, inspect `deployment/entrypoint.sh`; it should run the database wait before migrations/server/worker startup.
- If signup email rendering fails with a relative MJML URL, set a real `MJML_URL` reachable from the container or disable MJML until a renderer is provisioned.
- If a generated app lacks initial migrations, regenerate from the current starter or add and commit migrations before deploying.

## Verification commands

Use equivalent API/CLI calls when your environment differs.

```bash
gh run list --workflow "Deploy Prod" --limit 3
gh run view <run-id> --log-failed
curl -fsS https://<domain>/api/healthcheck
```
