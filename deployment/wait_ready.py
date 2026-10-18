"""Bounded, release-attempt-aware production readiness checks (stdlib only)."""

import argparse
import json
import os
import time
from http.client import HTTPException
from urllib.error import URLError
from urllib.request import Request, urlopen


def payload_ready(payload, release, deployment, require_worker):
    if not isinstance(payload, dict):
        return False
    checks = payload.get("checks", {})
    return bool(
        payload.get("release") == release
        and payload.get("deployment") == deployment
        and payload.get("healthy") is True
        and isinstance(checks, dict)
        and all(checks.get(name) is True for name in ("database", "redis", "qdrant"))
        and (not require_worker or payload.get("worker_ready") is True)
    )


def wait_until_ready(
    url, release, deployment, require_worker=False, *, timeout=600, interval=5, stable_checks=6
):
    deadline = time.monotonic() + timeout
    stable = 0
    request = Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "CiteGuild-Deploy"})
    while time.monotonic() < deadline:
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read(65536))
            ready = payload_ready(payload, release, deployment, require_worker)
        except (HTTPException, URLError, OSError, ValueError):
            ready = False
        stable = stable + 1 if ready else 0
        if stable >= stable_checks:
            print("Current deployment is stably ready.", flush=True)
            return
        print(
            f"Waiting for current deployment ({stable}/{stable_checks} stable checks).", flush=True
        )
        time.sleep(interval)
    raise TimeoutError("Current deployment did not become ready within the readiness window.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    wait_until_ready(
        os.environ["PRODUCTION_HEALTHCHECK_URL"],
        os.environ["EXPECTED_RELEASE"],
        os.environ["EXPECTED_DEPLOYMENT"],
        args.worker,
    )


if __name__ == "__main__":
    main()
