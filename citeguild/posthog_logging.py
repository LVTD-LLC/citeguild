from __future__ import annotations

import copy
import logging
import os
import socket
from collections.abc import Mapping
from enum import Enum
from math import isfinite
from typing import Any
from uuid import UUID

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from citeguild.logging_utils import (
    build_service_resource_attributes,
    get_log_record_extras,
    is_canonical_event_name,
)

Scalar = str | bool | int | float
MAX_ATTRIBUTE_STRING_LENGTH = 1_024

_ALLOWED_LOG_ATTRIBUTES = frozenset(
    {
        "amount_total",
        "api_key_id",
        "api_key_present",
        "attempt",
        "auth.method",
        "auth.reason",
        "cache.hit",
        "checkout_id",
        "context_size",
        "currency",
        "customer_id",
        "dependency",
        "duration_ms",
        "email.delivery.status",
        "email_sent_id",
        "email_type",
        "ended_at",
        "error.type",
        "event.name",
        "event_id",
        "event_type",
        "http.is_htmx",
        "http.request.method",
        "http.response.status_class",
        "http.response.status_code",
        "http.route",
        "htmx.boosted",
        "htmx.history_restore_request",
        "job.function",
        "job.group",
        "job.id",
        "job.success",
        "max_attempts",
        "metadata_count",
        "metric_name",
        "metric_value",
        "mode",
        "operation.status",
        "outcome",
        "payment_intent",
        "payment_status",
        "plan",
        "previous_status",
        "profile_id",
        "properties_count",
        "provider",
        "request.id",
        "request.interface",
        "source_function",
        "state_transition",
        "stripe_customer_id",
        "subscription_id",
        "subscription_status",
        "target_state",
        "transient",
        "user_id",
    }
)


def _normalize_scalar(value: Any) -> Scalar | None:
    if isinstance(value, Enum):
        return _normalize_scalar(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str):
        return value[:MAX_ATTRIBUTE_STRING_LENGTH]
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    return None


def sanitize_log_attributes(values: Mapping[str, Any]) -> dict[str, Scalar]:
    attributes: dict[str, Scalar] = {}
    event_name = _normalize_scalar(values.get("event.name"))
    if is_canonical_event_name(event_name):
        attributes["event.name"] = event_name

    for raw_key, value in values.items():
        key = str(raw_key)
        if key == "event.name" or key not in _ALLOWED_LOG_ATTRIBUTES:
            continue
        normalized = _normalize_scalar(value)
        if normalized is not None:
            attributes[key] = normalized

    return attributes


def _exception_type_name(record: logging.LogRecord) -> str | None:
    if record.exc_info and record.exc_info[0]:
        return getattr(record.exc_info[0], "__name__", None)
    return None


class PostHogLoggingHandler(logging.Handler):
    """Send a sanitized LogRecord clone to PostHog's batched OTLP endpoint."""

    def __init__(
        self,
        *,
        delegate: logging.Handler | None = None,
        endpoint: str = "",
        api_key: str = "",
        service_name: str = "citeguild-web",
        service_namespace: str = "citeguild",
        environment: str = "dev",
        service_version: str = "unknown",
    ) -> None:
        super().__init__()
        self._logger_provider: LoggerProvider | None = None

        if delegate is None:
            instance_id = f"{socket.gethostname()}:{os.getpid()}"
            resource = Resource.create(
                build_service_resource_attributes(
                    service_name=service_name,
                    service_namespace=service_namespace,
                    environment=environment,
                    service_version=service_version,
                    instance_id=instance_id,
                )
            )
            self._logger_provider = LoggerProvider(resource=resource)
            exporter = OTLPLogExporter(
                endpoint=endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            self._logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
            delegate = LoggingHandler(logger_provider=self._logger_provider)

        self._delegate = delegate

    def emit(self, record: logging.LogRecord) -> None:
        try:
            exported_record = self._translate_record(record)
            if exported_record is not None:
                self._delegate.emit(exported_record)
        except Exception:
            # Logging must fail open. Avoid logging this record again because that can
            # recurse and can expose the unsanitized record through diagnostic dumps.
            return

    def close(self) -> None:
        logger_provider = self._logger_provider
        self._logger_provider = None
        try:
            if logger_provider is not None:
                logger_provider.shutdown()
        except Exception:
            pass
        finally:
            super().close()

    def _translate_record(self, record: logging.LogRecord) -> logging.LogRecord | None:
        record_extras = get_log_record_extras(record)
        attributes = sanitize_log_attributes(record_extras)
        event_name = attributes.get("event.name")
        if not isinstance(event_name, str):
            return None

        exception_type = _exception_type_name(record)
        if exception_type:
            attributes.setdefault("error.type", exception_type)
        profile_id = attributes.get("profile_id")
        if profile_id is not None:
            attributes["posthogDistinctId"] = str(profile_id)

        exported_record = copy.copy(record)
        for key in record_extras:
            delattr(exported_record, key)
        exported_record.msg = event_name
        exported_record.args = ()
        exported_record.exc_info = None
        exported_record.exc_text = None
        exported_record.stack_info = None
        for key, value in attributes.items():
            setattr(exported_record, key, value)
        return exported_record
