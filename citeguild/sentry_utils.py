import logging
from collections.abc import Callable, MutableMapping
from logging import LogRecord
from typing import Any

from sentry_sdk.integrations.logging import LoggingIntegration

_IGNORED_LOGGERS: set[str] = set()
_IGNORED_TRANSACTION_PATHS = {"/api/healthcheck", "/favicon.ico", "/robots.txt"}
_IGNORED_TRANSACTION_PREFIXES = ("/static/", "/media/")
_SENSITIVE_LOG_ATTRIBUTE_PARTS = (
    "authorization",
    "cookie",
    "email",
    "ip_address",
    "password",
    "secret",
)
_SENSITIVE_LOG_ATTRIBUTE_NAMES = (
    "apitoken",
    "api_token",
    "authtoken",
    "auth_token",
    "accesstoken",
    "access_token",
    "csrf_token",
    "idtoken",
    "id_token",
    "refreshtoken",
    "refresh_token",
    "sessiontoken",
    "session_token",
    "token",
)
_SENSITIVE_LOG_ATTRIBUTE_SUFFIXES = (
    ".token",
    "_token",
)


class CustomLoggingIntegration(LoggingIntegration):
    def _handle_record(self, record: LogRecord) -> None:
        # This matches upper logger names, e.g. "celery" will match "celery.worker"
        # or "celery.worker.job"
        if record.name in _IGNORED_LOGGERS or record.name.split(".")[0] in _IGNORED_LOGGERS:
            return
        super()._handle_record(record)


def before_send(event, hint):
    if "exc_info" in hint:
        _exc_type, exc_value, _tb = hint["exc_info"]

        if isinstance(exc_value, SystemExit):  # group all SystemExits together
            event["fingerprint"] = ["system-exit"]
    return event


def before_send_log(log, _hint):
    attributes = log.get("attributes")
    if not isinstance(attributes, MutableMapping):
        return log

    for key in list(attributes.keys()):
        normalized_key = str(key).lower().replace("-", "_")
        if (
            normalized_key in _SENSITIVE_LOG_ATTRIBUTE_NAMES
            or any(
                sensitive_part in normalized_key
                for sensitive_part in _SENSITIVE_LOG_ATTRIBUTE_PARTS
            )
            or any(normalized_key.endswith(suffix) for suffix in _SENSITIVE_LOG_ATTRIBUTE_SUFFIXES)
        ):
            attributes[key] = "[Filtered]"

    return log


def logging_level_from_env(value: str, default: int) -> int:
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)

    level = logging.getLevelName(stripped.upper())
    if isinstance(level, int):
        return level
    return default


def resolve_sentry_release(
    explicit_release: str,
    service_version: str,
    image_release: str,
) -> str:
    return explicit_release.strip() or service_version.strip() or image_release.strip()


def _transaction_path_from_sampling_context(sampling_context: dict[str, Any]) -> str:
    environ = sampling_context.get("wsgi_environ") or {}
    if environ.get("PATH_INFO"):
        return environ["PATH_INFO"]

    asgi_scope = sampling_context.get("asgi_scope") or {}
    if asgi_scope.get("path"):
        return asgi_scope["path"]

    transaction_context = sampling_context.get("transaction_context") or {}
    transaction_name = transaction_context.get("name") or ""
    if transaction_name.startswith("/"):
        return transaction_name

    return ""


def build_traces_sampler(
    *,
    http_sample_rate: float,
    background_sample_rate: float,
) -> Callable[[dict[str, Any]], float]:
    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        transaction_context = sampling_context.get("transaction_context") or {}
        transaction_name = transaction_context.get("name") or ""
        transaction_op = transaction_context.get("op") or ""
        transaction_path = _transaction_path_from_sampling_context(sampling_context)

        if transaction_path in _IGNORED_TRANSACTION_PATHS:
            return 0.0
        if any(transaction_path.startswith(prefix) for prefix in _IGNORED_TRANSACTION_PREFIXES):
            return 0.0

        parent_sampled = sampling_context.get("parent_sampled")
        if parent_sampled is not None:
            return 1.0 if parent_sampled else 0.0

        if (
            transaction_op.startswith("http")
            or transaction_path
            or transaction_name.startswith("/")
        ):
            return http_sample_rate

        return background_sample_rate

    return traces_sampler
