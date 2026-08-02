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


@override_settings(QDRANT_URL="http://qdrant:6333", CITEGUILD_RELEASE="abc123")
def test_healthcheck_reports_the_running_release(monkeypatch):
    monkeypatch.setattr("apps.api.views.connection", _HealthyConnection())
    monkeypatch.setattr("apps.api.views.cache.set", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("apps.api.views.cache.get", lambda *_args, **_kwargs: "ok")
    monkeypatch.setattr("apps.search.qdrant.article_collection_healthy", lambda: True)

    payload = healthcheck(HttpRequest())

    assert payload["healthy"] is True
    assert payload["release"] == "abc123"
