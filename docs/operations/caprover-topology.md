# CapRover Production Topology

This is the CG-031 deployment contract for the CiteGuild MVP. PostgreSQL owns
durable application truth. Qdrant is a rebuildable search projection. Redis is
cache and queue delivery state, not a substitute for PostgreSQL.

## Service map

| CapRover app | Role and command | Internal port | Public | Persistence | Health contract |
| --- | --- | ---: | --- | --- | --- |
| `citeguild` | Shared SHA image, `APP_PROCESS_TYPE=server`; entrypoint migrates, validates Qdrant, then runs ASGI Gunicorn | 80 | HTTPS only | `citeguild-media:/app/media` | `GET /api/healthcheck` must return 200 with database, Redis, and Qdrant true |
| `citeguild-workers` | Same SHA image, `APP_PROCESS_TYPE=worker`; ensures named schedules, then runs Django Q2 | 80 unused | No | Shared media volume | CapRover task stays running and a controlled queued job is consumed during deployment smoke |
| `citeguild-postgres` | PostgreSQL 18 | 5432 | No | `citeguild-postgres-data:/var/lib/postgresql/data` | `pg_isready`; also covered by web aggregate health |
| `citeguild-redis` | Redis 8 with password and AOF | 6379 | No | `citeguild-redis-data:/data` | Authenticated `PING`; also covered by web aggregate health |
| `citeguild-qdrant` | Qdrant 1.18.3 with API key and telemetry disabled | 6333 | No | `citeguild-qdrant-data:/qdrant/storage` | Authenticated collection validation through web aggregate health |

Only `citeguild` is exposed through CapRover's proxy. Application connections
use `srv-captain--citeguild-postgres`, `srv-captain--citeguild-redis`, and
`srv-captain--citeguild-qdrant`; database, cache, queue, and vector ports never
need public routing.

The worker role owns the Django Q2 scheduler. There is no separate scheduler
container: named schedules and PostgreSQL uniqueness/claim constraints make
worker restarts idempotent.

## Image contract

GitHub Actions builds `deployment/Dockerfile` once and publishes only:

```text
ghcr.io/lvtd-llc/citeguild:<40-character-git-sha>
```

Web and workers must run the same SHA. A floating `latest` tag is neither
published nor accepted by `docker-compose-prod.yml`. Record the last-known-good
SHA and both CapRover deployment versions before every rollout.

## Local and production parity

`docker-compose-local.yml` mirrors the Postgres, authenticated Redis,
authenticated Qdrant, web, worker, internal ports, and persistent paths. It
publishes dependency ports to localhost only for development tools.

`docker-compose-prod.yml` publishes no Postgres, Redis, Qdrant, or worker port,
requires an immutable `APP_IMAGE`, waits for all dependencies to become healthy,
and gives the web process an aggregate health check.

## Capacity baseline

Start with one replica of every service. Web and worker can scale independently
after PostgreSQL connection count, Redis queue depth, Qdrant memory, crawl rate,
and embedding cost are measured. PostgreSQL and Qdrant remain single-writer
persistent services until a tested replication design exists. Do not scale
workers to compensate for a failing dependency or an unbounded queue.

## Release order

1. Confirm backups/rollback SHA and snapshot CapRover app definitions without
   printing secrets.
2. Build and publish the exact merge SHA.
3. Deploy web first. With one web replica, its entrypoint waits for PostgreSQL,
   runs forward-compatible migrations once, validates the Qdrant collection,
   and starts ASGI.
4. Require root and aggregate health 200. Stop if any dependency is false.
5. Deploy workers at the identical SHA. Confirm `APP_PROCESS_TYPE=worker`, a
   running Q2 cluster, named schedules, and one controlled job boundary.
6. Record deployed versions, image SHA, health output, and migration state.

The GitHub deployment validates all required CapRover secrets before building,
deploys web first, and waits up to two minutes for the public aggregate health
contract before updating workers. A failed web health gate leaves workers on
the previous image, which is the intentional safe stopping point. The CapRover
deployment action is pinned to a reviewed commit rather than a floating branch.

App-scoped deploy tokens must remain enabled for both web and workers. Rotate a
token in CapRover and update its matching GitHub Actions secret as one operation;
never put the token in logs or repository files. On CapRover versions whose app
definition update causes a service refresh, wait for aggregate health to recover
before rotating the second token or starting a release.

Schema changes must be expand/contract compatible with the previous image.
Destructive or long-running migrations require a separate reviewed maintenance
plan; do not hide them inside normal startup.

## Rollback order

1. Stop the rollout and preserve dependency volumes.
2. If workers are implicated, return workers to the last-known-good SHA first so
   no new-format jobs are produced.
3. Return web to the same last-known-good SHA and verify aggregate health.
4. Do not reverse migrations automatically. Restore or repair schema/data only
   from the task-specific, reviewed recovery plan.
5. If Qdrant is incompatible or corrupt, keep PostgreSQL authoritative and run
   the collection rebuild path after web/database health is restored.

CapRover deployment versions are convenience pointers; the immutable GHCR SHA
is the rollback identity.

## Persistence and recovery boundary

Redeploying web/workers must not modify the Postgres, Redis, Qdrant, or media
volume definitions. Persistent volumes are not backups. Backup retention,
restore drills, alerting, and Qdrant rebuild evidence are owned by CG-033.
