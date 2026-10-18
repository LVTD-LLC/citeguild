from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils import timezone
from django_q.conf import Conf

from apps.core.worker_readiness import WORKER_READINESS_KEY, worker_ready


@pytest.fixture
def ready_worker(monkeypatch):
    with override_settings(CITEGUILD_RELEASE="release", CITEGUILD_DEPLOYMENT_ID="attempt"):
        cache.clear()
        cache.set(
            WORKER_READINESS_KEY,
            {
                "release": "release",
                "deployment": "attempt",
                "configuration_fingerprint": settings.CITEGUILD_CONFIG_FINGERPRINT,
                "pid": 1,
                "cluster_id": "cluster",
            },
            timeout=None,
        )
        status = SimpleNamespace(
            status=Conf.IDLE,
            timestamp=timezone.now(),
            workers=list(range(Conf.WORKERS)),
            monitor=2,
            pusher=3,
        )
        monkeypatch.setattr("apps.core.worker_readiness.Stat.get", lambda **_kwargs: status)
        yield status
        cache.clear()


@pytest.mark.parametrize(
    "field,value",
    [
        (None, None),
        ("release", "old"),
        ("deployment", "old-attempt"),
        ("configuration_fingerprint", "different"),
        ("cluster_id", None),
    ],
)
def test_readiness_requires_matching_registered_worker(ready_worker, field, value):
    assert worker_ready() is True
    if field:
        registration = cache.get(WORKER_READINESS_KEY)
        registration[field] = value
        cache.set(WORKER_READINESS_KEY, registration)
    else:
        cache.delete(WORKER_READINESS_KEY)
    assert worker_ready() is False


@pytest.mark.parametrize(
    "change",
    ["working", "stopped", "stale", "future", "no-workers", "no-monitor", "no-pusher"],
)
def test_readiness_requires_fresh_running_cluster(ready_worker, change):
    if change == "working":
        ready_worker.status = Conf.WORKING
    elif change == "stopped":
        ready_worker.status = Conf.STOPPED
    elif change in {"stale", "future"}:
        seconds = 30 if change == "stale" else -30
        ready_worker.timestamp -= timedelta(seconds=seconds)
    elif change == "no-workers":
        ready_worker.workers = []
    elif change == "no-monitor":
        ready_worker.monitor = 0
    else:
        ready_worker.pusher = 0
    assert worker_ready() is (change == "working")


def test_readiness_fails_closed_on_broker_error(ready_worker, monkeypatch):
    def unavailable(**_kwargs):
        raise OSError("not public")

    monkeypatch.setattr("apps.core.worker_readiness.Stat.get", unavailable)
    assert worker_ready() is False


@override_settings(CITEGUILD_RELEASE="release", CITEGUILD_DEPLOYMENT_ID="attempt")
@pytest.mark.parametrize("registration_fails", [False, True])
def test_worker_command_registers_started_cluster_or_stops_it(monkeypatch, registration_fails):
    cluster = SimpleNamespace(pid=10, cluster_id="started-cluster", started=False, stopped=False)

    def start():
        cluster.started = True

    def stop():
        cluster.stopped = True

    cluster.start = start
    cluster.stop = stop
    monkeypatch.setattr("apps.core.management.commands.run_worker.Cluster", lambda: cluster)
    cache.clear()
    if registration_fails:

        def unavailable(*_args, **_kwargs):
            raise OSError("not public")

        monkeypatch.setattr("apps.core.management.commands.run_worker.cache.set", unavailable)
        with pytest.raises(CommandError, match="readiness registration failed"):
            call_command("run_worker")
        assert cluster.stopped is True
    else:
        call_command("run_worker")
        assert cache.get(WORKER_READINESS_KEY) == {
            "release": "release",
            "deployment": "attempt",
            "configuration_fingerprint": settings.CITEGUILD_CONFIG_FINGERPRINT,
            "pid": 10,
            "cluster_id": "started-cluster",
        }
    assert cluster.started is True
    cache.clear()
