from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from posthog import Posthog
from posthog.mcp import instrument
from posthog.mcp.types import MCPAnalyticsOptions


def _parameter_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "other"


def sanitize_mcp_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Keep MCP usage shape without exporting request or response contents."""
    if event.get("event") == "$exception":
        return None

    properties = dict(event.get("properties") or {})
    parameters = properties.get("$mcp_parameters")
    arguments = None
    if isinstance(parameters, dict):
        request = parameters.get("request")
        if isinstance(request, dict):
            params = request.get("params")
            if isinstance(params, dict):
                arguments = params.get("arguments")

    if isinstance(arguments, dict):
        argument_names = sorted(str(name) for name in arguments)
        properties["$mcp_parameters"] = {
            "argument_count": len(argument_names),
            "argument_names": argument_names,
            "argument_types": {
                str(name): _parameter_type(value) for name, value in arguments.items()
            },
        }
    else:
        properties.pop("$mcp_parameters", None)

    properties.pop("$mcp_response", None)
    return {**event, "properties": properties}


@dataclass
class MCPAnalyticsRuntime:
    analytics: Any
    client: Posthog

    async def shutdown(self) -> None:
        """Best-effort drain MCP events before stopping the PostHog client."""
        try:
            await self.analytics.flush()
        except Exception:
            pass

        try:
            await asyncio.to_thread(self.client.shutdown)
        except Exception:
            pass


def configure_mcp_analytics(server: Any) -> MCPAnalyticsRuntime | None:
    if not settings.POSTHOG_API_KEY:
        return None

    client = Posthog(settings.POSTHOG_API_KEY, host=settings.POSTHOG_HOST)
    analytics = instrument(
        server,
        client,
        MCPAnalyticsOptions(
            context=False,
            enable_exception_autocapture=False,
            before_send=sanitize_mcp_event,
        ),
    )
    return MCPAnalyticsRuntime(analytics=analytics, client=client)
