from django.db import close_old_connections
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_request

from apps.api.services import serialize_user_info
from apps.core.models import Profile
from apps.mcp_server.analytics import configure_mcp_analytics
from apps.mcp_server.auth import authenticate_mcp_headers

mcp = FastMCP(
    name="CiteGuild",
    instructions=(
        "AI-native editorial source network for relevant agent-discovered citations "
        "Authenticate hosted MCP requests with OAuth. Legacy clients may send an API key "
        "with X-API-Key or Authorization: Bearer <api_key>."
    ),
)

mcp_analytics = configure_mcp_analytics(mcp)


def _get_request_profile() -> Profile | None:
    try:
        request = get_http_request()
    except RuntimeError:
        return None

    return authenticate_mcp_headers(request.headers)


def _authenticate_profile() -> Profile:
    profile = _get_request_profile()
    if profile is None:
        raise PermissionError(
            "Missing or invalid CiteGuild MCP credentials. "
            "Use OAuth, X-API-Key, or Authorization: Bearer <api_key>."
        )
    return profile


@mcp.tool(
    name="get_user_info",
    description=("Return safe account and profile details for the authenticated CiteGuild user."),
)
def get_user_info() -> dict:
    """Return safe user/profile details for the authenticated MCP user."""
    close_old_connections()
    profile = _authenticate_profile()
    return serialize_user_info(profile)
