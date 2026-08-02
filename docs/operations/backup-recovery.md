# Backup and Recovery

CiteGuild's PostgreSQL database is the durable source of truth. Production runs
one private `citeguild-backups` process that creates a custom-format `pg_dump`,
streams it into an encrypted restic repository in the private
`citeguild-backups` MinIO bucket, applies retention, and runs `restic check`.
Qdrant is a rebuildable projection and is not part of the database backup.

## Objectives and ownership

- RPO: 24 hours. The job runs daily and retries failures after 15 minutes.
- RTO: four hours for PostgreSQL restore, migrations, Qdrant rebuild, and smoke.
- Retention: 7 daily, 4 weekly, and 6 monthly snapshots.
- Owner: Forge for backup automation and recovery drills; Greg for alert routing
  and launch operations.
- Failure signal: the dedicated Healthchecks check receives start, success, and
  failure pings. Its timeout is 25 hours with a two-hour grace period.

Persistent CapRover volumes are not backups. The MinIO repository uses a
bucket-scoped credential, remains private, and is independently encrypted by
restic. The restic password, object-storage credential, and ping URL belong in
the approved secret store and CapRover environment only.

## Daily backup contract

`deployment/backup/run.sh` performs this sequence:

1. Send a start ping and remove stale restic locks left by interrupted jobs.
2. Initialize the encrypted repository only when it does not exist.
3. Stream `pg_dump --format=custom` into a restic snapshot named
   `citeguild.dump`; no plaintext dump is written to a persistent filesystem.
4. Retain 7 daily, 4 weekly, and 6 monthly snapshots and prune unreferenced data.
5. Run `restic check`, then send success. Any failed step sends `/fail` and
   retries after 15 minutes.

Never print the database password, restic password, object-storage secret, or
Healthchecks ping URL. Record only snapshot IDs, timestamps, sizes, and outcomes.

## Isolated PostgreSQL restore drill

Never restore into the production service or volume.

1. Create an unexposed temporary PostgreSQL 18 container with a unique name and
   random password. Do not attach it to the CapRover overlay network.
2. Stream the newest encrypted snapshot directly between containers:

   ```text
   restic dump latest citeguild.dump | pg_restore --clean --if-exists --no-owner --no-privileges
   ```

3. Verify `django_migrations` is present, expected application tables exist,
   and representative row counts can be queried.
4. Record elapsed time and snapshot identity. Remove only the temporary
   container; no plaintext dump should remain on the host.

## Isolated Qdrant rebuild drill

1. Start a uniquely named, authenticated Qdrant service with no published port
   and an empty temporary volume.
2. Point a one-off CiteGuild process at the restored PostgreSQL database and
   temporary Qdrant service.
3. Run `python manage.py rebuild_qdrant_articles --batch-size 100`.
4. Compare the reported indexed count with eligible PostgreSQL embeddings and
   confirm the temporary collection is healthy and searchable.
5. Remove only the temporary Qdrant service and volume.

## Production recovery order

1. Stop web and workers from accepting or producing new writes.
2. Restore the selected PostgreSQL snapshot into a fresh database volume.
3. Run migrations and verify subscription, project, article, crawl, and link
   graph invariants before switching application connections.
4. Bring up web, require exact-release aggregate health, then bring up workers.
5. Rebuild Qdrant from PostgreSQL embeddings and perform API/MCP search smoke.
6. Resume schedules, confirm Healthchecks, and retain the incident evidence.

Do not automatically reverse migrations or overwrite a suspect production
volume. Preserve it for investigation until the recovery is accepted.
