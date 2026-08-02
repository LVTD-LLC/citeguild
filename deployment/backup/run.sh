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
BACKUP_RUN_ONCE="${BACKUP_RUN_ONCE:-0}"

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
if [[ "$BACKUP_RUN_ONCE" != "0" && "$BACKUP_RUN_ONCE" != "1" ]]; then
  echo "BACKUP_RUN_ONCE must be 0 or 1." >&2
  exit 1
fi

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
  local dump_dir dump_file

  ping_healthchecks "/start"
  restic unlock >/dev/null 2>&1 || true
  ensure_repository || return

  dump_dir="$(mktemp -d)" || return
  dump_file="$dump_dir/citeguild.dump"
  if ! pg_dump --format=custom --no-owner --no-privileges --file="$dump_file"; then
    rm -rf "$dump_dir"
    return 1
  fi
  if [ ! -s "$dump_file" ]; then
    echo "PostgreSQL dump was empty; refusing to create a snapshot." >&2
    rm -rf "$dump_dir"
    return 1
  fi
  if ! (
    cd "$dump_dir" && restic backup \
      --host citeguild-production \
      --tag citeguild-postgres \
      citeguild.dump
  ); then
    rm -rf "$dump_dir"
    return 1
  fi
  rm -rf "$dump_dir"

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
    if [ "$BACKUP_RUN_ONCE" = "1" ]; then
      exit 0
    fi
    sleep "$BACKUP_INTERVAL_SECONDS"
  else
    status=$?
    echo "PostgreSQL backup failed; retrying after the configured delay." >&2
    ping_healthchecks "/fail"
    if [ "$BACKUP_RUN_ONCE" = "1" ]; then
      exit "$status"
    fi
    sleep "$BACKUP_RETRY_SECONDS"
  fi
done
