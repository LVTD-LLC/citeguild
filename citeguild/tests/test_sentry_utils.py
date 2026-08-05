import logging
from types import MappingProxyType

from citeguild.sentry_utils import (
    before_send_log,
    build_traces_sampler,
    logging_level_from_env,
    resolve_sentry_release,
)


def test_logging_level_from_env_accepts_known_names():
    assert logging_level_from_env("warning", logging.INFO) == logging.WARNING
    assert logging_level_from_env(" ERROR ", logging.INFO) == logging.ERROR


def test_logging_level_from_env_accepts_numeric_strings():
    assert logging_level_from_env("30", logging.INFO) == 30


def test_logging_level_from_env_falls_back_for_unknown_names():
    assert logging_level_from_env("not-a-level", logging.INFO) == logging.INFO


def test_sentry_release_prefers_explicit_then_service_then_image_release():
    assert resolve_sentry_release(" sentry-1 ", "service-1", "image-1") == "sentry-1"
    assert resolve_sentry_release("", " service-1 ", "image-1") == "service-1"
    assert resolve_sentry_release("", "", " image-1 ") == "image-1"


def test_before_send_log_filters_sensitive_attributes_without_filtering_token_counts():
    log = {
        "attributes": {
            "access_token": "secret-token",
            "authorization": "Bearer secret-token",
            "input_tokens": 25,
            "token_count": 35,
            "user_email": "user@example.com",
        }
    }

    result = before_send_log(log, {})

    assert result["attributes"]["access_token"] == "[Filtered]"
    assert result["attributes"]["authorization"] == "[Filtered]"
    assert result["attributes"]["user_email"] == "[Filtered]"
    assert result["attributes"]["input_tokens"] == 25
    assert result["attributes"]["token_count"] == 35


def test_before_send_log_ignores_immutable_attributes():
    attributes = MappingProxyType({"access_token": "secret-token"})
    log = {"attributes": attributes}

    assert before_send_log(log, {}) == log


def test_sentry_traces_sampler_respects_parent_sampling_decision():
    sampler = build_traces_sampler(http_sample_rate=0.5, background_sample_rate=0.1)

    assert sampler({"parent_sampled": True}) == 1.0
    assert sampler({"parent_sampled": False}) == 0.0


def test_sentry_traces_sampler_drops_ignored_paths_before_parent_sampling():
    sampler = build_traces_sampler(http_sample_rate=0.5, background_sample_rate=0.1)

    assert (
        sampler(
            {
                "parent_sampled": True,
                "transaction_context": {"name": "/api/healthcheck", "op": "http.server"},
                "wsgi_environ": {"PATH_INFO": "/api/healthcheck"},
            }
        )
        == 0.0
    )


def test_sentry_traces_sampler_drops_healthcheck_and_static_paths():
    sampler = build_traces_sampler(http_sample_rate=0.5, background_sample_rate=0.1)

    assert (
        sampler(
            {
                "transaction_context": {"name": "/api/healthcheck", "op": "http.server"},
                "wsgi_environ": {"PATH_INFO": "/api/healthcheck"},
            }
        )
        == 0.0
    )
    assert (
        sampler(
            {
                "transaction_context": {"name": "/static/app.css", "op": "http.server"},
                "wsgi_environ": {"PATH_INFO": "/static/app.css"},
            }
        )
        == 0.0
    )
    assert (
        sampler(
            {
                "transaction_context": {"name": "/media/photo.jpg", "op": "http.server"},
                "asgi_scope": {"path": "/media/photo.jpg"},
            }
        )
        == 0.0
    )


def test_sentry_traces_sampler_uses_route_specific_rates():
    sampler = build_traces_sampler(http_sample_rate=0.5, background_sample_rate=0.1)

    assert sampler({"transaction_context": {"name": "/", "op": "http.server"}}) == 0.5
    assert (
        sampler({"transaction_context": {"name": "apps.core.tasks.refresh", "op": "queue.task"}})
        == 0.1
    )
