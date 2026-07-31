from __future__ import annotations

import contextvars
import json
import logging
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from django.utils.functional import LazyObject, empty

LOG_RECORD_FIELDS = frozenset(
    logging.LogRecord(
        name="reserved",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__
) | {"asctime", "message"}
_CANONICAL_EVENT_NAME = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+")
_SAFE_CORRELATION_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")
_HEALTHCHECK_PATHS = frozenset({"/api/healthcheck"})
_log_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "log_context",
    default=None,
)


def _safe_extra_key(key: Any) -> str:
    key = str(key)
    if key in LOG_RECORD_FIELDS:
        return f"extra_{key}"
    return key


def get_log_record_extras(record: logging.LogRecord) -> dict[str, Any]:
    return {key: value for key, value in vars(record).items() if key not in LOG_RECORD_FIELDS}


def is_canonical_event_name(value: Any) -> bool:
    return isinstance(value, str) and _CANONICAL_EVENT_NAME.fullmatch(value) is not None


def build_service_resource_attributes(
    *,
    service_name: str,
    service_namespace: str,
    environment: str,
    service_version: str,
    instance_id: str = "",
) -> dict[str, str]:
    return {
        key: value
        for key, value in {
            "service.name": service_name,
            "service.namespace": service_namespace,
            "service.version": service_version,
            "deployment.environment.name": environment,
            "service.instance.id": instance_id,
        }.items()
        if value
    }


def _normalise_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, Mapping):
        return {str(key): _normalise_value(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set | frozenset):
        return [_normalise_value(item) for item in value]

    if isinstance(value, Exception):
        return {
            "type": value.__class__.__name__,
            "message": str(value),
        }

    return str(value)


def _clean_extra(extra: Mapping[str, Any] | None) -> dict[str, Any]:
    if not extra:
        return {}

    return {_safe_extra_key(key): value for key, value in extra.items()}


def bind_log_context(**values: Any) -> contextvars.Token[dict[str, Any] | None]:
    context = (_log_context.get() or {}).copy()
    context.update({key: value for key, value in values.items() if value is not None})
    return _log_context.set(context)


def reset_log_context(token: contextvars.Token[dict[str, Any] | None]) -> None:
    _log_context.reset(token)


class RequestContextFilter(logging.Filter):
    """Attach request-scoped contextvars to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_request_context_attached", False):
            return True

        if not hasattr(record, "event.name") and is_canonical_event_name(record.msg):
            setattr(record, "event.name", record.msg)

        for key, value in _clean_extra(_log_context.get() or {}).items():
            if not hasattr(record, key):
                setattr(record, key, value)
        record._request_context_attached = True
        return True


class JsonFormatter(logging.Formatter):
    """Format LogRecord objects as newline-delimited JSON for log shippers."""

    def __init__(
        self,
        *args: Any,
        service_name: str = "",
        service_namespace: str = "",
        service_version: str = "",
        environment: str = "",
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self._resource_attributes = build_service_resource_attributes(
            service_name=service_name,
            service_namespace=service_namespace,
            service_version=service_version,
            environment=environment,
        )

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process": record.process,
            "thread": record.thread,
            "thread_name": record.threadName,
            **self._resource_attributes,
        }

        collisions: dict[str, Any] = {}
        for key, value in get_log_record_extras(record).items():
            if key.startswith("_"):
                continue

            normalised = _normalise_value(value)
            if key in payload:
                collisions[key] = normalised
            else:
                payload[key] = normalised

        if collisions:
            payload["attributes"] = collisions

        if record.exc_info:
            exc_type, exc_value, _tb = record.exc_info
            payload["exception"] = {
                "type": exc_type.__name__ if exc_type else None,
                "message": str(exc_value) if exc_value else "",
                "stacktrace": self.formatException(record.exc_info),
            }
        elif record.stack_info:
            payload["stacktrace"] = record.stack_info

        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Format local logs with visible structured extras."""

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("fmt", "%(levelname)s %(asctime)s %(name)s %(message)s")
        super().__init__(*args, **kwargs)

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = {
            key: _normalise_value(value)
            for key, value in get_log_record_extras(record).items()
            if not key.startswith("_")
        }
        if not extras:
            return message
        return f"{message} {json.dumps(extras, default=str, ensure_ascii=False)}"


def validate_correlation_id(value: str | None) -> str | None:
    candidate = (value or "").strip()
    return candidate if _SAFE_CORRELATION_ID.fullmatch(candidate) else None


def correlation_id_or_new(value: str | None) -> str:
    return validate_correlation_id(value) or uuid.uuid4().hex


def get_request_actor(request) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if isinstance(user, LazyObject) and user._wrapped is empty:
        return {}
    if user is None or not getattr(user, "is_authenticated", False):
        return {}

    actor = {"user_id": user.id}
    user_state = getattr(user, "_state", None)
    if user_state is not None:
        if "profile" not in user_state.fields_cache:
            return actor
        profile = user_state.fields_cache["profile"]
    else:
        profile = getattr(user, "profile", None)

    profile_id = getattr(profile, "id", None)
    if profile_id is not None:
        actor.update(
            {
                "profile_id": profile_id,
            }
        )
    return actor


def get_request_interface(request) -> str:
    if request.path.startswith("/api/"):
        return "rest"
    if bool(getattr(request, "htmx", False)):
        return "htmx"
    return "web"


def get_request_route(request) -> str:
    resolver_match = getattr(request, "resolver_match", None)
    if resolver_match is None:
        return "unresolved"
    return resolver_match.view_name or getattr(resolver_match, "route", "") or "unresolved"


def is_healthcheck_request(request) -> bool:
    return request.path.rstrip("/") in _HEALTHCHECK_PATHS


class RequestLogContextMiddleware:
    """Add correlation fields and emit one compact request-complete log."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger("citeguild.request")

    def __call__(self, request):
        request_id = correlation_id_or_new(request.headers.get("X-Request-ID"))
        request_interface = get_request_interface(request)
        request.request_id = request_id
        token = bind_log_context(
            **{
                "request.id": request_id,
                "request.interface": request_interface,
            }
        )
        started_at = time.perf_counter()
        response = None
        error = None

        try:
            response = self.get_response(request)
            return response
        except Exception as exc:
            error = exc
            raise
        finally:
            try:
                status_code = response.status_code if response is not None else 500
                if response is not None:
                    response["X-Request-ID"] = request_id

                actor = get_request_actor(request)
                if not is_healthcheck_request(request):
                    htmx = getattr(request, "htmx", None)
                    log_extra = {
                        "event.name": "http.request.completed",
                        "request.id": request_id,
                        "request.interface": request_interface,
                        "http.request.method": request.method,
                        "http.route": get_request_route(request),
                        "http.response.status_code": status_code,
                        "http.response.status_class": f"{status_code // 100}xx",
                        "http.is_htmx": bool(htmx),
                        "htmx.boosted": bool(getattr(htmx, "boosted", False)),
                        "htmx.history_restore_request": bool(
                            getattr(htmx, "history_restore_request", False)
                        ),
                        "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
                        "outcome": "failure" if status_code >= 400 else "success",
                        **actor,
                    }
                    if error is not None:
                        log_extra["error.type"] = error.__class__.__name__

                    self.logger.log(
                        logging.ERROR if status_code >= 500 else logging.INFO,
                        "http.request.completed",
                        extra=log_extra,
                        exc_info=error is not None,
                    )
            finally:
                reset_log_context(token)
