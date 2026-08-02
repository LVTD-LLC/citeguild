from datetime import UTC, datetime
from uuid import uuid4

import pytest
from django.core.cache import cache

from apps.core.sitemap_submission import SitemapDocumentKind, SitemapValidation
from apps.core.tests.test_article_ingestion import create_project
from apps.search.service import SearchError, SearchResponse, SearchResult


def test_v1_rate_limit_cache_key_does_not_store_credential_identifier(monkeypatch):
    from apps.api.rate_limits import consume_v1_rate_limit

    keys = []
    monkeypatch.setattr("apps.api.rate_limits.time.time", lambda: 1_786_000_000)
    monkeypatch.setattr(
        "apps.api.rate_limits.cache.add",
        lambda key, _value, *, timeout: keys.append((key, timeout)) or True,
    )

    result = consume_v1_rate_limit("ak_public_prefix")

    assert result.allowed is True
    assert result.remaining == result.limit - 1
    assert "ak_public_prefix" not in keys[0][0]
    assert keys[0][0].startswith("api:v1:key:")


@pytest.mark.django_db
def test_v1_account_and_project_status_are_owner_scoped(
    client,
    profile,
    django_user_model,
):
    own_project = create_project(profile, "owned.example")
    other_user = django_user_model.objects.create_user(
        username="other-api-user",
        email="other-api@example.com",
    )
    other_project = create_project(other_user.profile, "other.example")
    api_key = profile.rotate_api_key()

    account = client.get("/api/v1/account", HTTP_X_API_KEY=api_key)
    projects = client.get(
        "/api/v1/projects?limit=1&offset=0",
        HTTP_X_API_KEY=api_key,
    )
    detail = client.get(
        f"/api/v1/projects/{own_project.uuid}",
        HTTP_X_API_KEY=api_key,
    )
    forbidden_detail = client.get(
        f"/api/v1/projects/{other_project.uuid}",
        HTTP_X_API_KEY=api_key,
    )

    assert account.status_code == 200
    assert account.json()["profile"]["has_active_subscription"] is True
    assert projects.status_code == 200
    assert projects.json()["count"] == 1
    assert [item["id"] for item in projects.json()["results"]] == [str(own_project.uuid)]
    assert detail.status_code == 200
    assert detail.json() == {
        "id": str(own_project.uuid),
        "name": "owned.example",
        "sitemap_url": "https://owned.example/sitemap.xml",
        "normalized_host": "owned.example",
        "state": "active",
        "article_count": 0,
        "active_article_count": 0,
        "last_sync_at": None,
        "current_sync_started_at": None,
        "last_error_code": "",
    }
    assert forbidden_detail.status_code == 404
    assert forbidden_detail.json()["code"] == "project_not_found"
    assert "other.example" not in forbidden_detail.content.decode()


@pytest.mark.django_db
def test_v1_project_creation_reuses_authenticated_submission_contract(
    client,
    profile,
    monkeypatch,
):
    profile.stripe_subscription_status = "active"
    profile.save(update_fields=["stripe_subscription_status", "updated_at"])
    api_key = profile.rotate_api_key()
    monkeypatch.setattr(
        "apps.core.sitemap_submission.validate_sitemap",
        lambda *_args, **_kwargs: SitemapValidation(SitemapDocumentKind.URL_SET),
    )

    response = client.post(
        "/api/v1/projects",
        data={"name": "Docs", "sitemap_url": "https://DOCS.example/sitemap.xml"},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 201
    assert response.json()["normalized_host"] == "docs.example"
    assert response.json()["sync_state"] == "queued"


@pytest.mark.django_db
def test_v1_search_uses_shared_service_contract(client, profile, monkeypatch):
    create_project(profile, "requester.example")
    api_key = profile.rotate_api_key()
    seen = []
    response = SearchResponse(
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

    class FakeSearchService:
        def search(self, **kwargs):
            seen.append(kwargs)
            return response

    monkeypatch.setattr("apps.api.views.SearchService", FakeSearchService)

    result = client.post(
        "/api/v1/search",
        data={
            "query": "  django commit hooks  ",
            "limit": 7,
            "language": "en",
            "excluded_domains": ["requester.example"],
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {api_key}",
    )

    assert result.status_code == 200
    assert result.json() == {
        "contract_version": "v1",
        "results": [
            {
                "article_id": str(response.results[0].article_id),
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
            "profile": profile,
            "query": "  django commit hooks  ",
            "limit": 7,
            "language": "en",
            "excluded_domains": ["requester.example"],
        }
    ]


@pytest.mark.django_db
def test_v1_rejects_revoked_keys_and_rate_limits_by_profile(
    client,
    profile,
    monkeypatch,
):
    cache.clear()
    monkeypatch.setattr("apps.api.rate_limits.API_V1_RATE_LIMIT", 2)
    revoked_key = profile.rotate_api_key()
    active_key = profile.rotate_api_key()

    revoked = client.get("/api/v1/account", HTTP_X_API_KEY=revoked_key)
    first = client.get("/api/v1/account", HTTP_X_API_KEY=active_key)
    second = client.get("/api/v1/account", HTTP_X_API_KEY=active_key)
    limited = client.get("/api/v1/account", HTTP_X_API_KEY=active_key)

    assert revoked.status_code == 401
    assert revoked.json()["code"] == "authentication_required"
    assert first.status_code == second.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["code"] == "rate_limited"
    assert limited.json()["retryable"] is True
    assert limited.json()["request_id"] == limited.headers["X-Request-ID"]
    assert int(limited.headers["Retry-After"]) >= 1

    def unavailable_rate_limit(_api_key_id):
        raise ConnectionError("cache unavailable")

    monkeypatch.setattr("apps.api.views.consume_v1_rate_limit", unavailable_rate_limit)
    unavailable = client.get("/api/v1/account", HTTP_X_API_KEY=active_key)
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "rate_limit_unavailable"
    assert unavailable.json()["retryable"] is True


@pytest.mark.django_db
def test_v1_search_schema_enforces_limits_before_service(client, profile, monkeypatch):
    api_key = profile.rotate_api_key()

    class UnexpectedSearchService:
        def search(self, **_kwargs):
            pytest.fail("invalid requests must not reach SearchService")

    monkeypatch.setattr("apps.api.views.SearchService", UnexpectedSearchService)
    query = "private bounded query"
    response = client.post(
        "/api/v1/search",
        data={"query": query, "limit": 51},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert query not in response.content.decode()

    boolean_limit = client.post(
        "/api/v1/search",
        data={"query": "valid query", "limit": True},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )
    assert boolean_limit.status_code == 422
    assert boolean_limit.json()["code"] == "validation_error"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [
        (SearchError("query_required"), 422, "query_required"),
        (
            SearchError("query_embedding_unavailable", retryable=True),
            503,
            "query_embedding_unavailable",
        ),
        (SearchError("query_embedding_invalid"), 503, "query_embedding_invalid"),
        (SearchError("search_index_invalid"), 503, "search_index_invalid"),
    ],
)
def test_v1_search_maps_service_errors_without_leaking_query(
    client,
    profile,
    monkeypatch,
    error,
    expected_status,
    expected_code,
):
    create_project(profile, "errors.example")
    api_key = profile.rotate_api_key()

    class FailingSearchService:
        def search(self, **_kwargs):
            raise error

    monkeypatch.setattr("apps.api.views.SearchService", FailingSearchService)
    query = "private draft text must stay private"

    response = client.post(
        "/api/v1/search",
        data={"query": query},
        content_type="application/json",
        HTTP_X_API_KEY=api_key,
    )

    assert response.status_code == expected_status
    assert response.json()["code"] == expected_code
    assert response.json()["retryable"] is error.retryable
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert query not in response.content.decode()


@pytest.mark.django_db
def test_openapi_publishes_versioned_search_and_status_examples(client):
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert {
        "/api/v1/account",
        "/api/v1/projects",
        "/api/v1/projects/{project_uuid}",
        "/api/v1/search",
    }.issubset(schema["paths"])
    search_schema = schema["components"]["schemas"]["SearchRequest"]
    assert search_schema["examples"] == [
        {
            "query": "How do Django transaction commit hooks work?",
            "limit": 10,
            "language": "en",
            "excluded_domains": ["my-site.example"],
        }
    ]
