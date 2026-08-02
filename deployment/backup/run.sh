#!/usr/bin/env bash
set -uo pipefail

required=(
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  HEALTHCHECKS_PING_URL
  PGDATABASE
  PGHOST
  PGPASSWORD
  PGUSER
  RESTIC_PASSWORD
  RESTIC_REPOSITORY
)

for name in "${required[@]}"; do
  if [ -z "${!name:-}" ]; then
    echo "Required backup configuration is missing: $name" >&2
    exit 1
  fi
done

BACKUP_INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"
BACKUP_RETRY_SECONDS="${BACKUP_RETRY_SECONDS:-900}"
RESTIC_KEEP_DAILY="${RESTIC_KEEP_DAILY:-7}"
RESTIC_KEEP_WEEKLY="${RESTIC_KEEP_WEEKLY:-4}"
RESTIC_KEEP_MONTHLY="${RESTIC_KEEP_MONTHLY:-6}"

for value in \
  "$BACKUP_INTERVAL_SECONDS" \
  "$BACKUP_RETRY_SECONDS" \
  "$RESTIC_KEEP_DAILY" \
  "$RESTIC_KEEP_WEEKLY" \
  "$RESTIC_KEEP_MONTHLY"; do
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "Backup intervals and retention values must be positive integers." >&2
    exit 1
  fi
done

ping_healthchecks() {
  local suffix="${1:-}"
  curl --fail --silent --show-error --max-time 10 --retry 3 \
    "${HEALTHCHECKS_PING_URL}${suffix}" >/dev/null || true
}

ensure_repository() {
  if restic cat config >/dev/null 2>&1; then
    return 0
  fi
  restic init
}

run_backup() {
  ping_healthchecks "/start"
  restic unlock >/dev/null 2>&1 || true
  ensure_repository || return

  pg_dump --format=custom --no-owner --no-privileges | \
    restic backup \
      --host citeguild-production \
      --stdin \
      --stdin-filename citeguild.dump \
      --tag citeguild-postgres || return

  restic forget \
    --tag citeguild-postgres \
    --keep-daily "$RESTIC_KEEP_DAILY" \
    --keep-weekly "$RESTIC_KEEP_WEEKLY" \
    --keep-monthly "$RESTIC_KEEP_MONTHLY" \
    --prune || return
  restic check || return
  ping_healthchecks
}

while true; do
  if run_backup; then
    echo "Encrypted PostgreSQL backup completed and verified."
    sleep "$BACKUP_INTERVAL_SECONDS"
  else
    echo "PostgreSQL backup failed; retrying after the configured delay." >&2
    ping_healthchecks "/fail"
    sleep "$BACKUP_RETRY_SECONDS"
  fi
done
