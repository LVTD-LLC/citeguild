import socket
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import anyio
import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
from uvicorn import Config, Server

from apps.mcp_server.server import mcp
from apps.search.service import SearchError, SearchResponse, SearchResult


def _profile():
    user = SimpleNamespace(
        id=7,
        email="ada@example.com",
        username="ada",
        first_name="Ada",
        last_name="Lovelace",
        date_joined="2026-05-14T00:00:00Z",
        is_staff=False,
        is_superuser=False,
        get_full_name=lambda: "Ada Lovelace",
    )
    return SimpleNamespace(
        id=11,
        user=user,
        state="signed_up",
        has_active_subscription=False,
    )


def test_get_user_info_mcp_tool_returns_safe_user_data(monkeypatch):
    async def run():
        monkeypatch.setattr(
            "apps.mcp_server.server._authenticate_profile",
            lambda: _profile(),
        )

        async with Client(mcp) as client:
            result = await client.call_tool("get_user_info", {})

        payload = result.data
        assert payload["email"] == "ada@example.com"
        assert payload["profile"]["id"] == 11
        assert "key" not in payload

    anyio.run(run)


def test_get_user_info_mcp_tool_rejects_missing_auth(monkeypatch):
    def reject():
        raise PermissionError("Missing or invalid CiteGuild MCP credentials")

    async def run():
        monkeypatch.setattr("apps.mcp_server.server._authenticate_profile", reject)

        async with Client(mcp) as client:
            with pytest.raises(
                Exception,
                match="Missing or invalid CiteGuild MCP credentials",
            ):
                await client.call_tool("get_user_info", {})

    anyio.run(run)


def _search_response():
    return SearchResponse(
        contract_version="v1",
        results=(
            SearchResult(
                article_id=uuid4(),
                title="Commit hooks",
                canonical_url="https://member.example/commit-hooks",
                domain="member.example",
                excerpt="Use transaction.on_commit for post-commit work.",
                relevance=0.987654,
                language="en",
                last_seen_at=datetime(2026, 8, 2, 6, 0, tzinfo=UTC),
            ),
        ),
    )


def test_mcp_protocol_discovers_and_calls_search_tool_with_shared_contract(monkeypatch):
    expected = _search_response()
    authenticated_profile = _profile()
    seen = []

    class FakeSearchService:
        def search(self, **kwargs):
            seen.append(kwargs)
            return expected

    async def run():
        monkeypatch.setattr(
            "apps.mcp_server.server._authenticate_profile",
            lambda: authenticated_profile,
        )
        monkeypatch.setattr("apps.mcp_server.server.SearchService", FakeSearchService)

        async with Client(mcp) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "search_member_articles",
                {
                    "query": "  django commit hooks  ",
                    "limit": 7,
                    "language": "en",
                    "excluded_domains": ["requester.example"],
                },
            )

        search_tool = next(tool for tool in tools if tool.name == "search_member_articles")
        assert search_tool.description.startswith("Find relevant active member articles")
        assert search_tool.inputSchema["properties"]["query"]["maxLength"] == 8_000
        assert search_tool.inputSchema["properties"]["limit"]["maximum"] == 50
        excluded_domains_schema = search_tool.inputSchema["properties"]["excluded_domains"]
        array_schema = next(
            schema for schema in excluded_domains_schema["anyOf"] if schema.get("type") == "array"
        )
        assert array_schema["maxItems"] == 20
        assert result.data == {
            "contract_version": "v1",
            "results": [
                {
                    "article_id": str(expected.results[0].article_id),
                    "title": "Commit hooks",
                    "canonical_url": "https://member.example/commit-hooks",
                    "domain": "member.example",
                    "excerpt": "Use transaction.on_commit for post-commit work.",
                    "relevance": 0.987654,
                    "language": "en",
                    "last_seen_at": "2026-08-02T06:00:00Z",
                }
            ],
        }
        assert seen == [
            {
                "profile": authenticated_profile,
                "query": "  django commit hooks  ",
                "limit": 7,
                "language": "en",
                "excluded_domains": ["requester.example"],
                "transport": "mcp",
            }
        ]

    anyio.run(run)


def test_mcp_search_maps_service_errors_without_leaking_query(monkeypatch):
    query = "private draft passage must not enter MCP errors"

    class FailingSearchService:
        def search(self, **_kwargs):
            raise SearchError("search_index_unavailable", retryable=True)

    async def run():
        monkeypatch.setattr("apps.mcp_server.server._authenticate_profile", _profile)
        monkeypatch.setattr("apps.mcp_server.server.SearchService", FailingSearchService)

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_member_articles",
                {"query": query},
                raise_on_error=False,
            )

        assert result.is_error is True
        error_text = result.content[0].text
        assert error_text == "search_index_unavailable: Search is temporarily unavailable."
        assert query not in error_text

    anyio.run(run)


def test_mcp_search_rejects_oversized_input_before_service(monkeypatch):
    query = "x" * 8_001

    class UnexpectedSearchService:
        def search(self, **_kwargs):
            pytest.fail("invalid requests must not reach SearchService")

    async def run():
        monkeypatch.setattr("apps.mcp_server.server._authenticate_profile", _profile)
        monkeypatch.setattr("apps.mcp_server.server.SearchService", UnexpectedSearchService)

        async with Client(mcp) as client:
            result = await client.call_tool(
                "search_member_articles",
                {"query": query},
                raise_on_error=False,
            )

        assert result.is_error is True
        assert query not in result.content[0].text

    anyio.run(run)


@pytest.mark.django_db(transaction=True)
def test_streamable_http_initializes_lists_and_calls_search_with_bearer_auth(
    profile,
    monkeypatch,
):
    from citeguild.asgi import application

    expected = _search_response()
    api_key = profile.rotate_api_key()

    class FakeSearchService:
        def search(self, **_kwargs):
            return expected

    monkeypatch.setattr("apps.mcp_server.server.SearchService", FakeSearchService)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = Server(Config(application, log_level="warning", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started is True

    async def run():
        async with httpx.AsyncClient() as unauthorized_client:
            unauthorized = await unauthorized_client.post(
                f"http://127.0.0.1:{port}/mcp/",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "1"},
                    },
                },
            )
        assert unauthorized.status_code == 401
        assert unauthorized.json() == {"detail": "MCP authentication required."}
        assert "resource_metadata=" in unauthorized.headers["WWW-Authenticate"]

        transport = StreamableHttpTransport(
            url=f"http://127.0.0.1:{port}/mcp/",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        async with Client(transport) as client:
            tools = await client.list_tools()
            user_info = await client.call_tool("get_user_info", {})
            result = await client.call_tool(
                "search_member_articles",
                {"query": "Django commit hooks", "limit": 3},
            )

        assert "search_member_articles" in {tool.name for tool in tools}
        assert user_info.data["email"] == profile.user.email
        assert result.data["contract_version"] == "v1"
        assert result.data["results"][0]["article_id"] == str(expected.results[0].article_id)

    try:
        anyio.run(run)
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
    assert thread.is_alive() is False
