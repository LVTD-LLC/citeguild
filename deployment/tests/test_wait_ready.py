import io
import json
from http.client import IncompleteRead
from types import SimpleNamespace
from urllib.error import URLError

import pytest

from deployment import wait_ready


def payload():
    return {
        "release": "sha",
        "deployment": "attempt",
        "healthy": True,
        "checks": {"database": True, "redis": True, "qdrant": True},
        "worker_ready": True,
    }


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"release": "old"},
        {"deployment": "old-attempt"},
        {"healthy": False},
        {"checks": {"database": True}},
        {"worker_ready": False},
        {"worker_ready": "true"},
    ],
)
def test_current_attempt_and_dependencies_required(change):
    current = payload() | change
    assert wait_ready.payload_ready(current, "sha", "attempt", True) is (not change)
    if change == {"worker_ready": False}:
        assert wait_ready.payload_ready(current, "sha", "attempt", False) is True


@pytest.mark.parametrize(
    "failure", [URLError("private body"), IncompleteRead(b""), b"not json", b"[]"]
)
def test_poll_resets_stability_after_transport_or_payload_failure(monkeypatch, failure):
    good = json.dumps(payload()).encode()
    responses = iter([good, failure, good, good])
    requests = []

    def fetch(request, **_kwargs):
        requests.append(request)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return io.BytesIO(response)

    monkeypatch.setattr(wait_ready, "urlopen", fetch)
    monkeypatch.setattr(
        wait_ready, "time", SimpleNamespace(monotonic=lambda: 0, sleep=lambda _seconds: None)
    )
    wait_ready.wait_until_ready(
        "https://example.com/health",
        "sha",
        "attempt",
        True,
        stable_checks=2,
    )
    assert len(requests) == 4


def test_poll_is_bounded_and_never_accepts_old_attempt(monkeypatch):
    clock = iter([0, 0, 1, 2])
    monkeypatch.setattr(
        wait_ready,
        "time",
        SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _seconds: None),
    )
    monkeypatch.setattr(
        wait_ready,
        "urlopen",
        lambda *_args, **_kwargs: io.BytesIO(
            json.dumps(payload() | {"deployment": "old"}).encode()
        ),
    )
    with pytest.raises(TimeoutError, match="did not become ready"):
        wait_ready.wait_until_ready("https://example.com/health", "sha", "attempt", timeout=2)
