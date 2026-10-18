import pytest
from django.http import HttpRequest
from django.test import override_settings

from apps.api.views import healthcheck


class _HealthyCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, _query):
        return None

    def fetchone(self):
        return (1,)


class _HealthyConnection:
    def cursor(self):
        return _HealthyCursor()


@override_settings(
    QDRANT_URL="http://qdrant:6333", CITEGUILD_RELEASE="abc123", CITEGUILD_DEPLOYMENT_ID="attempt"
)
@pytest.mark.parametrize("worker_is_ready", [False, True])
def test_healthcheck_reports_the_running_release(monkeypatch, worker_is_ready):
    monkeypatch.setattr("apps.api.views.connection", _HealthyConnection())
    monkeypatch.setattr("apps.api.views.cache.set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("apps.api.views.cache.get", lambda *_args, **_kwargs: "ok")
    monkeypatch.setattr("apps.search.qdrant.article_collection_healthy", lambda: True)
    monkeypatch.setattr("apps.core.worker_readiness.worker_ready", lambda: worker_is_ready)

    payload = healthcheck(HttpRequest())

    assert payload["healthy"] is True
    assert payload["release"] == "abc123"
    assert payload["deployment"] == "attempt"
    assert payload["worker_ready"] is worker_is_ready
