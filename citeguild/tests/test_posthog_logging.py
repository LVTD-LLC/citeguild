import logging
import os
import subprocess
import sys
from logging.handlers import BufferingHandler
from math import inf, nan
from pathlib import Path
from uuid import UUID

from citeguild.logging_utils import build_service_resource_attributes
from citeguild.posthog_logging import (
    PostHogLoggingHandler,
    sanitize_log_attributes,
)


def test_sanitize_log_attributes_keeps_scalars_and_drops_sensitive_values():
    attributes = sanitize_log_attributes(
        {
            "event.name": "http.request.completed",
            "request.id": "req-1",
            "profile_id": 42,
            "duration_ms": 12.5,
            "cached": False,
            "event_id": UUID("12345678-1234-5678-1234-567812345678"),
            "email": "private@example.com",
            "customer_name": "Private Customer",
            "prompt": "private user content",
            "authorization": "Bearer private-token",
            "request_body": "private body",
            "metadata": {"private": "value"},
            "rows": ["private row"],
            "positive_infinity": inf,
            "not_a_number": nan,
        }
    )

    assert attributes == {
        "event.name": "http.request.completed",
        "request.id": "req-1",
        "profile_id": 42,
        "duration_ms": 12.5,
        "event_id": "12345678-1234-5678-1234-567812345678",
    }


def test_build_resource_attributes_uses_otel_service_fields():
    attributes = build_service_resource_attributes(
        service_name="example-worker",
        service_namespace="example",
        environment="prod",
        service_version="release-123",
        instance_id="worker-1",
    )

    assert attributes == {
        "service.name": "example-worker",
        "service.namespace": "example",
        "service.version": "release-123",
        "deployment.environment.name": "prod",
        "service.instance.id": "worker-1",
    }


def test_handler_translates_standard_logging_extra_without_mutating_original(
    collecting_log_handler,
):
    handler = PostHogLoggingHandler(delegate=collecting_log_handler)
    original_handler = BufferingHandler(capacity=10)
    logger = logging.Logger("apps.test", level=logging.INFO)
    logger.addHandler(handler)
    logger.addHandler(original_handler)

    logger.info(
        "private message argument: %s",
        "customer@example.com",
        extra={
            "event.name": "http.request.completed",
            "request.id": "req-1",
            "profile_id": 7,
            "email": "private@example.com",
            "metadata": {"private": "value"},
        },
    )

    exported = collecting_log_handler.buffer[0]
    original = original_handler.buffer[0]
    assert exported.getMessage() == "http.request.completed"
    assert getattr(exported, "event.name") == "http.request.completed"
    assert getattr(exported, "request.id") == "req-1"
    assert exported.profile_id == 7
    assert exported.posthogDistinctId == "7"
    assert not hasattr(exported, "email")
    assert not hasattr(exported, "metadata")
    assert "customer@example.com" not in str(vars(exported))
    assert original.getMessage() == "private message argument: customer@example.com"
    assert original.args == ("customer@example.com",)
    assert original.email == "private@example.com"
    assert original.metadata == {"private": "value"}


def test_handler_exports_exception_type_without_private_details(collecting_log_handler):
    handler = PostHogLoggingHandler(delegate=collecting_log_handler)
    logger = logging.Logger("apps.test", level=logging.ERROR)
    logger.addHandler(handler)

    try:
        raise ValueError("private dataset value")
    except ValueError:
        logger.exception(
            "operation.failed",
            extra={"event.name": "operation.failed"},
        )

    exported = collecting_log_handler.buffer[0]
    assert exported.exc_info is None
    assert exported.stack_info is None
    assert getattr(exported, "error.type") == "ValueError"
    assert "private dataset value" not in str(vars(exported))


def test_handler_drops_records_without_a_canonical_event(collecting_log_handler):
    handler = PostHogLoggingHandler(delegate=collecting_log_handler)
    logger = logging.Logger("apps.test", level=logging.INFO)
    logger.addHandler(handler)

    logger.info(
        "private ad hoc message",
        extra={
            "event.name": "Not Canonical",
            "profile_id": 7,
        },
    )

    assert collecting_log_handler.buffer == []


def test_handler_failure_never_interrupts_application_logging():
    class FailingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            raise RuntimeError("export failed")

    handler = PostHogLoggingHandler(delegate=FailingHandler())
    record = logging.LogRecord(
        "apps.test",
        logging.INFO,
        __file__,
        1,
        "operation.completed",
        (),
        None,
    )

    handler.emit(record)


def test_handler_closes_owned_logger_provider_once(collecting_log_handler):
    class StubProvider:
        shutdown_calls = 0

        def shutdown(self) -> None:
            self.shutdown_calls += 1

    provider = StubProvider()
    handler = PostHogLoggingHandler(delegate=collecting_log_handler)
    handler._logger_provider = provider

    handler.close()
    handler.close()

    assert provider.shutdown_calls == 1


def test_production_settings_attach_posthog_handler():
    environment = os.environ.copy()
    environment.update(
        {
            "ENVIRONMENT": "prod",
            "POSTHOG_API_KEY": "phc_test_project_token",
        }
    )
    environment.pop("POSTHOG_LOGS_ENABLED", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import logging
import logging.config

from citeguild import settings
from citeguild.posthog_logging import PostHogLoggingHandler

assert settings.POSTHOG_LOGS_ACTIVE is True
assert "posthog" in settings.LOGGING["handlers"]
assert "posthog" in settings.LOGGING["loggers"]["apps"]["handlers"]
assert "posthog" in settings.LOGGING["loggers"]["citeguild"]["handlers"]
logging.config.dictConfig(settings.LOGGING)
assert any(
    isinstance(handler, PostHogLoggingHandler)
    for handler in logging.getLogger("apps").handlers
)
logging.shutdown()
""",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
