import logging
from typing import Annotated

from django.db import close_old_connections
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_request
from pydantic import Field

from apps.api.services import serialize_user_info
from apps.core.models import Profile
from apps.mcp_server.analytics import configure_mcp_analytics
from apps.mcp_server.auth import authenticate_mcp_headers
from apps.search.service import (
    MAX_EXCLUDED_DOMAINS,
    MAX_QUERY_CHARS,
    MAX_SEARCH_LIMIT,
    SearchError,
    SearchService,
)

logger = logging.getLogger(__name__)

SearchQuery = Annotated[
    str,
    Field(min_length=1, max_length=MAX_QUERY_CHARS, pattern=r"\S"),
]
SearchLimit = Annotated[int, Field(ge=1, le=MAX_SEARCH_LIMIT, strict=True)]
SearchLanguage = Annotated[
    str,
    Field(max_length=35, pattern=r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"),
]
ExcludedDomain = Annotated[
    str,
    Field(
        min_length=1,
        max_length=253,
        pattern=(
            r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
            r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.?$"
        ),
    ),
]
ExcludedDomains = Annotated[list[ExcludedDomain], Field(max_length=MAX_EXCLUDED_DOMAINS)]

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


def _search_payload(response) -> dict:
    return {
        "contract_version": response.contract_version,
        "results": [
            {
                "article_id": str(result.article_id),
                "title": result.title,
                "canonical_url": result.canonical_url,
                "domain": result.domain,
                "excerpt": result.excerpt,
                "relevance": result.relevance,
                "language": result.language,
                "last_seen_at": result.last_seen_at.isoformat().replace("+00:00", "Z"),
            }
            for result in response.results
        ],
    }


@mcp.tool(
    name="search_member_articles",
    description=(
        "Find relevant active member articles for a query or draft passage. "
        "Use results as candidate sources and verify them before citing; relevance is not "
        "an endorsement or a requirement to link."
    ),
    timeout=30,
)
def search_member_articles(
    query: SearchQuery,
    limit: SearchLimit = 10,
    language: SearchLanguage | None = None,
    excluded_domains: ExcludedDomains | None = None,
) -> dict:
    """Search the shared v1 member corpus with authenticated account access."""
    close_old_connections()
    try:
        profile = _authenticate_profile()
        response = SearchService().search(
            profile=profile,
            query=query,
            limit=limit,
            language=language,
            excluded_domains=excluded_domains or (),
        )
        return _search_payload(response)
    except SearchError as error:
        if error.code == "subscription_required":
            message = "An active subscription is required to search."
        elif error.code in {
            "invalid_query",
            "query_required",
            "query_too_long",
            "invalid_limit",
            "invalid_language",
            "invalid_excluded_domain",
            "too_many_excluded_domains",
        }:
            message = "The search request is invalid."
        else:
            message = "Search is temporarily unavailable."
        raise ToolError(f"{error.code}: {message}") from None
    except ToolError:
        raise
    except Exception as error:
        logger.error(
            "mcp.search.completed",
            extra={
                "event.name": "mcp.search.completed",
                "operation.status": "failed",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
        )
        raise ToolError("internal_error: Search is temporarily unavailable.") from None
    finally:
        close_old_connections()
