import json
import logging
from types import SimpleNamespace

import pytest
from django.http import HttpResponse
from django.test import RequestFactory
from django_htmx.middleware import HtmxDetails

from citeguild.logging_utils import JsonFormatter, RequestLogContextMiddleware


def _collecting_logger(handler) -> logging.Logger:
    logger = logging.Logger("request-test", level=logging.INFO)
    logger.addHandler(handler)
    return logger


def _request(path: str = "/settings/"):
    request = RequestFactory().get(path)
    request.user = SimpleNamespace(is_authenticated=False)
    request.resolver_match = SimpleNamespace(view_name="settings", route="settings/")
    return request


def test_json_formatter_emits_otel_resource_and_event_fields():
    formatter = JsonFormatter(
        service_name="example-web",
        service_namespace="example",
        service_version="release-123",
        environment="prod",
    )
    record = logging.LogRecord(
        "apps.core.views",
        logging.INFO,
        __file__,
        1,
        "account.deleted",
        (),
        None,
    )
    setattr(record, "event.name", "account.deleted")
    record.outcome = "success"

    payload = json.loads(formatter.format(record))

    assert payload["event.name"] == "account.deleted"
    assert payload["outcome"] == "success"
    assert payload["service.name"] == "example-web"
    assert payload["service.namespace"] == "example"
    assert payload["service.version"] == "release-123"
    assert payload["deployment.environment.name"] == "prod"


def test_request_middleware_emits_one_canonical_htmx_completion_event(collecting_log_handler):
    request = RequestFactory().get(
        "/settings/",
        HTTP_HX_REQUEST="true",
        HTTP_HX_BOOSTED="true",
        HTTP_HX_HISTORY_RESTORE_REQUEST="true",
    )
    request.user = SimpleNamespace(is_authenticated=False)
    request.htmx = HtmxDetails(request)
    request.resolver_match = SimpleNamespace(view_name="settings", route="settings/")
    logger = _collecting_logger(collecting_log_handler)
    middleware = RequestLogContextMiddleware(lambda _request: HttpResponse(status=200))
    middleware.logger = logger

    response = middleware(request)

    record = collecting_log_handler.buffer[0]
    assert record.getMessage() == "http.request.completed"
    assert getattr(record, "event.name") == "http.request.completed"
    assert getattr(record, "request.interface") == "htmx"
    assert getattr(record, "request.id") == response.headers["X-Request-ID"]
    assert getattr(record, "http.request.method") == "GET"
    assert getattr(record, "http.route") == "settings"
    assert getattr(record, "http.response.status_code") == 200
    assert getattr(record, "http.response.status_class") == "2xx"
    assert record.outcome == "success"
    assert record.duration_ms >= 0
    assert getattr(record, "http.is_htmx") is True
    assert getattr(record, "htmx.boosted") is True
    assert getattr(record, "htmx.history_restore_request") is True
    assert not hasattr(record, "request_ip")
    assert not hasattr(record, "request_path")


def test_request_middleware_replaces_unsafe_request_id_and_skips_healthcheck_log(
    collecting_log_handler,
):
    request = _request("/api/healthcheck")
    request.META["HTTP_X_REQUEST_ID"] = "unsafe\nrequest-id"
    request.resolver_match = SimpleNamespace(
        view_name="api-1.0.0:healthcheck",
        route="healthcheck",
    )
    logger = _collecting_logger(collecting_log_handler)
    middleware = RequestLogContextMiddleware(lambda _request: HttpResponse(status=200))
    middleware.logger = logger

    response = middleware(request)

    assert len(response.headers["X-Request-ID"]) == 32
    assert response.headers["X-Request-ID"] != "unsafe\nrequest-id"
    assert collecting_log_handler.buffer == []


def test_request_middleware_records_failure_without_exception_message(collecting_log_handler):
    request = _request("/broken/")
    request.resolver_match = SimpleNamespace(view_name="broken", route="broken/")
    logger = _collecting_logger(collecting_log_handler)

    def broken_response(_request):
        raise ValueError("private failure detail")

    middleware = RequestLogContextMiddleware(broken_response)
    middleware.logger = logger

    with pytest.raises(ValueError):
        middleware(request)

    record = collecting_log_handler.buffer[0]
    assert record.outcome == "failure"
    assert getattr(record, "error.type") == "ValueError"
    assert getattr(record, "http.response.status_code") == 500
    assert "private failure detail" not in str(
        {key: value for key, value in vars(record).items() if key not in {"exc_info", "exc_text"}}
    )
