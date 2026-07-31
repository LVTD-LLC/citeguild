import logging

from django_q.signals import post_execute_in_worker, pre_execute

from citeguild.logging_utils import (
    RequestContextFilter,
    bind_log_context,
    reset_log_context,
)


def test_task_completion_logs_safe_canonical_job_boundary(monkeypatch, collecting_log_handler):
    times = iter([10.0, 10.125])
    monkeypatch.setattr("apps.core.task_logging.time.perf_counter", lambda: next(times))
    logger = logging.Logger("task-test", level=logging.INFO)
    logger.addHandler(collecting_log_handler)
    monkeypatch.setattr("apps.core.task_logging.logger", logger)
    task = {
        "id": "task-1",
        "name": "Send email",
        "func": "apps.core.tasks.send_email",
        "group": "email",
        "args": ["private@example.com"],
        "kwargs": {"token": "private-token"},
    }

    pre_execute.send(sender="django_q", func=lambda: None, task=task)
    task.update({"success": True, "result": {"private": "result"}})
    post_execute_in_worker.send(sender="django_q", func=lambda: None, task=task)

    record = collecting_log_handler.buffer[0]
    assert record.getMessage() == "background_job.completed"
    assert getattr(record, "event.name") == "background_job.completed"
    assert getattr(record, "job.id") == "task-1"
    assert getattr(record, "job.name") == "Send email"
    assert getattr(record, "job.function") == "apps.core.tasks.send_email"
    assert getattr(record, "job.group") == "email"
    assert getattr(record, "job.success") is True
    assert record.outcome == "success"
    assert record.duration_ms == 125.0
    assert record.args == ()
    assert "task_args" not in vars(record)
    assert "task_kwargs" not in vars(record)
    assert "task_result" not in vars(record)
    assert "private@example.com" not in str(vars(record))
    assert "private-token" not in str(vars(record))


def test_failed_task_uses_stable_error_type_without_result(monkeypatch, collecting_log_handler):
    times = iter([20.0, 20.25])
    monkeypatch.setattr("apps.core.task_logging.time.perf_counter", lambda: next(times))
    logger = logging.Logger("task-test", level=logging.INFO)
    logger.addHandler(collecting_log_handler)
    monkeypatch.setattr("apps.core.task_logging.logger", logger)
    task = {
        "id": "task-2",
        "func": "apps.core.tasks.send_email",
        "success": False,
        "result": "ValueError: private provider response",
    }

    pre_execute.send(sender="django_q", func=lambda: None, task=task)
    post_execute_in_worker.send(sender="django_q", func=lambda: None, task=task)

    record = collecting_log_handler.buffer[0]
    assert getattr(record, "job.success") is False
    assert record.outcome == "failure"
    assert getattr(record, "error.type") == "TaskExecutionError"
    assert "private provider response" not in str(vars(record))
    assert record.duration_ms == 250.0


def test_synchronous_task_restores_ambient_request_context(monkeypatch, collecting_log_handler):
    times = iter([30.0, 30.1])
    monkeypatch.setattr("apps.core.task_logging.time.perf_counter", lambda: next(times))
    collecting_log_handler.addFilter(RequestContextFilter())
    logger = logging.Logger("task-test", level=logging.INFO)
    logger.addHandler(collecting_log_handler)
    monkeypatch.setattr("apps.core.task_logging.logger", logger)
    request_token = bind_log_context(**{"request.id": "request-1"})
    task = {
        "id": "task-sync",
        "func": "apps.core.tasks.send_email",
        "success": True,
    }

    try:
        pre_execute.send(sender="django_q", func=lambda: None, task=task)
        post_execute_in_worker.send(sender="django_q", func=lambda: None, task=task)
        logger.info(
            "request.follow_up.completed",
            extra={
                "event.name": "request.follow_up.completed",
                "outcome": "success",
            },
        )
    finally:
        reset_log_context(request_token)

    task_record, follow_up_record = collecting_log_handler.buffer
    assert getattr(task_record, "request.id") == "request-1"
    assert getattr(task_record, "job.id") == "task-sync"
    assert getattr(follow_up_record, "request.id") == "request-1"
    assert not hasattr(follow_up_record, "job.id")
