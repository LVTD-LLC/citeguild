import json

import anyio
import pytest
from django.test import override_settings

from apps.mcp_server import analytics


def test_sanitize_mcp_event_keeps_usage_shape_without_private_contents():
    event = {
        "event": "$mcp_tool_call",
        "distinct_id": "anonymous-session",
        "properties": {
            "$mcp_parameters": {
                "request": {
                    "method": "tools/call",
                    "params": {
                        "name": "create_record",
                        "arguments": {
                            "record_id": "private-record-id",
                            "data": {
                                "email": "customer@example.com",
                                "plan": "enterprise",
                            },
                            "limit": 25,
                            "archived": False,
                        },
                    },
                }
            },
            "$mcp_response": {
                "content": [{"type": "text", "text": "customer@example.com"}],
            },
        },
    }

    sanitized = analytics.sanitize_mcp_event(event)

    assert sanitized is not None
    assert sanitized["properties"]["$mcp_parameters"] == {
        "argument_count": 4,
        "argument_names": ["archived", "data", "limit", "record_id"],
        "argument_types": {
            "archived": "boolean",
            "data": "object",
            "limit": "number",
            "record_id": "string",
        },
    }
    assert "$mcp_response" not in sanitized["properties"]
    serialized = json.dumps(sanitized)
    assert "private-record-id" not in serialized
    assert "customer@example.com" not in serialized
    assert "enterprise" not in serialized


def test_sanitize_mcp_event_drops_exception_payloads():
    event = {
        "event": "$exception",
        "properties": {"$exception_list": [{"value": "private record failed"}]},
    }

    assert analytics.sanitize_mcp_event(event) is None


@override_settings(POSTHOG_API_KEY="")
def test_configure_mcp_analytics_is_optional(monkeypatch):
    instrument_calls = []
    monkeypatch.setattr(
        analytics,
        "instrument",
        lambda *args, **kwargs: instrument_calls.append((args, kwargs)),
    )

    result = analytics.configure_mcp_analytics(object())

    assert result is None
    assert instrument_calls == []


@override_settings(
    POSTHOG_API_KEY="phc_test",
    POSTHOG_HOST="https://us.i.posthog.com",
)
def test_configure_mcp_analytics_uses_private_options(monkeypatch):
    sentinel_analytics = object()
    sentinel_client = object()
    instrument_calls = []
    client_calls = []

    def build_client(api_key, *, host):
        client_calls.append((api_key, host))
        return sentinel_client

    def instrument(server, client, options):
        instrument_calls.append((server, client, options))
        return sentinel_analytics

    monkeypatch.setattr(analytics, "Posthog", build_client)
    monkeypatch.setattr(analytics, "instrument", instrument)
    server = object()

    result = analytics.configure_mcp_analytics(server)

    assert result is not None
    assert result.analytics is sentinel_analytics
    assert result.client is sentinel_client
    assert client_calls == [("phc_test", "https://us.i.posthog.com")]
    assert len(instrument_calls) == 1
    configured_server, configured_client, options = instrument_calls[0]
    assert configured_server is server
    assert configured_client is sentinel_client
    assert options.context is False
    assert options.enable_exception_autocapture is False
    assert options.before_send is analytics.sanitize_mcp_event


def test_mcp_analytics_runtime_flushes_before_shutdown():
    calls = []

    class StubAnalytics:
        async def flush(self):
            calls.append("flush")

    class StubClient:
        def shutdown(self):
            calls.append("shutdown")

    runtime = analytics.MCPAnalyticsRuntime(
        analytics=StubAnalytics(),
        client=StubClient(),
    )

    anyio.run(runtime.shutdown)

    assert calls == ["flush", "shutdown"]


@pytest.mark.parametrize("failure_target", ["flush", "shutdown"])
def test_mcp_analytics_runtime_cleanup_failures_are_fail_open(failure_target):
    calls = []

    class StubAnalytics:
        async def flush(self):
            calls.append("flush")
            if failure_target == "flush":
                raise RuntimeError("flush failed")

    class StubClient:
        def shutdown(self):
            calls.append("shutdown")
            if failure_target == "shutdown":
                raise RuntimeError("shutdown failed")

    runtime = analytics.MCPAnalyticsRuntime(
        analytics=StubAnalytics(),
        client=StubClient(),
    )

    anyio.run(runtime.shutdown)

    assert calls == ["flush", "shutdown"]
