from __future__ import annotations

import logging
import time
from collections.abc import Callable
from contextvars import ContextVar, Token
from typing import Any

from django.dispatch import receiver
from django_q.signals import post_execute_in_worker, pre_execute

from citeguild.logging_utils import bind_log_context, reset_log_context

logger = logging.getLogger(__name__)

_TASK_STARTED_AT: ContextVar[tuple[float, ...]] = ContextVar(
    "citeguild_task_started_at",
    default=(),
)
_TASK_CONTEXT_TOKENS: ContextVar[tuple[Token, ...]] = ContextVar(
    "citeguild_task_context_tokens",
    default=(),
)


def _job_context(
    func: Callable[..., Any] | str | None,
    task: dict[str, Any],
) -> dict[str, Any]:
    configured_function = task.get("func")
    if isinstance(configured_function, str):
        job_function = configured_function
    elif callable(func):
        job_function = f"{func.__module__}.{func.__qualname__}"
    else:
        job_function = "unknown"

    return {
        "job.id": str(task.get("id") or "unknown"),
        "job.function": job_function,
        "job.name": str(task.get("name") or ""),
        "job.group": str(task.get("group") or ""),
    }


@receiver(pre_execute, dispatch_uid="citeguild.bind_task_logging_context")
def bind_task_context(
    sender: str,
    func: Callable[..., Any] | str | None,
    task: dict[str, Any],
    **kwargs: Any,
) -> None:
    _TASK_STARTED_AT.set((*_TASK_STARTED_AT.get(), time.perf_counter()))
    token = bind_log_context(**_job_context(func, task))
    _TASK_CONTEXT_TOKENS.set((*_TASK_CONTEXT_TOKENS.get(), token))


@receiver(
    post_execute_in_worker,
    dispatch_uid="citeguild.log_task_completion",
)
def log_task_completion(
    sender: str,
    func: Callable[..., Any] | str | None,
    task: dict[str, Any],
    **kwargs: Any,
) -> None:
    started_at_stack = _TASK_STARTED_AT.get()
    started_at = started_at_stack[-1] if started_at_stack else None
    _TASK_STARTED_AT.set(started_at_stack[:-1])

    token_stack = _TASK_CONTEXT_TOKENS.get()
    context_token = token_stack[-1] if token_stack else None
    _TASK_CONTEXT_TOKENS.set(token_stack[:-1])

    job_context = _job_context(func, task)
    if context_token is None:
        context_token = bind_log_context(**job_context)

    success = bool(task.get("success", False))
    attributes: dict[str, Any] = {
        "event.name": "background_job.completed",
        **job_context,
        "job.success": success,
        "duration_ms": (
            round((time.perf_counter() - started_at) * 1_000, 2) if started_at is not None else 0.0
        ),
        "outcome": "success" if success else "failure",
    }
    if not success:
        attributes["error.type"] = "TaskExecutionError"

    try:
        log_method = logger.info if success else logger.error
        log_method("background_job.completed", extra=attributes)
    finally:
        reset_log_context(context_token)
