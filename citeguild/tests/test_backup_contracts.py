import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_backup_image_is_non_root_and_contains_postgres_restic_and_curl():
    dockerfile = (ROOT / "deployment/backup/Dockerfile").read_text()

    assert "FROM postgres:18-alpine" in dockerfile
    assert "bash curl restic" in dockerfile
    assert "USER postgres" in dockerfile


def test_backup_script_encrypts_retains_verifies_and_alerts():
    script = (ROOT / "deployment/backup/run.sh").read_text()

    assert 'pg_dump --format=custom --no-owner --no-privileges --file="$dump_file"' in script
    assert '[ ! -s "$dump_file" ]' in script
    assert "restic backup" in script
    assert "--stdin" not in script
    assert "citeguild.dump" in script
    assert "--keep-daily" in script
    assert "--keep-weekly" in script
    assert "--keep-monthly" in script
    assert "restic check" in script
    assert 'ping_healthchecks "/start"' in script
    assert 'ping_healthchecks "/fail"' in script
    assert "RESTIC_PASSWORD" in script


def test_pg_dump_failure_cannot_create_a_restic_snapshot(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    restic_log = tmp_path / "restic.log"
    commands = {
        "curl": "exit 0",
        "pg_dump": "exit 7",
        "restic": 'echo "$*" >> "$RESTIC_TEST_LOG"; exit 0',
    }
    for name, body in commands.items():
        executable = bin_dir / name
        executable.write_text(f"#!/bin/sh\n{body}\n")
        executable.chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "AWS_ACCESS_KEY_ID": "test-access",
        "AWS_SECRET_ACCESS_KEY": "test-secret",
        "BACKUP_RUN_ONCE": "1",
        "HEALTHCHECKS_PING_URL": "https://healthchecks.invalid/ping/test",
        "PGDATABASE": "citeguild",
        "PGHOST": "database.invalid",
        "PGPASSWORD": "test-password",
        "PGUSER": "citeguild",
        "RESTIC_PASSWORD": "test-restic-password",
        "RESTIC_REPOSITORY": "s3:https://storage.invalid/citeguild-backups",
        "RESTIC_TEST_LOG": str(restic_log),
    }

    result = subprocess.run(
        ["bash", str(ROOT / "deployment/backup/run.sh")],
        capture_output=True,
        check=False,
        env=env,
        text=True,
        timeout=10,
    )

    assert result.returncode != 0
    assert "backup" not in restic_log.read_text()
    assert "backup failed" in result.stderr.lower()


def test_minio_policy_is_scoped_to_the_backup_bucket():
    policy = json.loads((ROOT / "deployment/backup/minio-policy.json").read_text())
    serialized = json.dumps(policy)

    assert "arn:aws:s3:::citeguild-backups" in serialized
    assert "arn:aws:s3:::citeguild-backups/*" in serialized
    assert "arn:aws:s3:::*" not in serialized
    assert "s3:*" not in serialized


def test_backup_deploy_uses_an_immutable_image_and_pinned_action():
    workflow = yaml.safe_load((ROOT / ".github/workflows/deploy-backups.yml").read_text())
    steps = workflow["jobs"]["build-and-deploy"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build and push")
    deploy = next(step for step in steps if step.get("name") == "Deploy backups to CapRover")

    expected = "${{ steps.image.outputs.image_name }}:${{ github.sha }}"
    assert build["with"]["tags"] == expected
    assert build["with"]["push"] == "${{ github.event_name != 'pull_request' }}"
    assert deploy["with"]["image"] == expected
    assert deploy["uses"] != "caprover/deploy-from-github@main"
    assert deploy["if"] == "github.event_name != 'pull_request'"
