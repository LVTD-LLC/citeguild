import pytest
from django.urls import reverse

from apps.pages.views import get_docs_navigation


@pytest.mark.django_db
def test_docs_require_login(client):
    response = client.get(reverse("docs_home"))
    assert response.status_code == 302
    assert "/accounts/login/" in response["Location"]


@pytest.mark.django_db
def test_docs_render_in_authenticated_app_shell(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="password123",
    )
    client.force_login(user)
    response = client.get(
        reverse("docs_page", kwargs={"category": "api-reference", "page": "introduction"})
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "API Reference" in content
    assert "noindex, nofollow" in content
    assert "docs-code-blocks" in content
    assert "data-docs-page" in content
    assert "CITEGUILD_API_KEY" in content
    assert "?api_key=" not in content
    assert "Work in Progress" not in content


def test_docs_navigation_uses_frontmatter_titles():
    navigation = get_docs_navigation()
    api_reference = next(
        section for section in navigation if section["category_slug"] == "api-reference"
    )

    assert api_reference["category"] == "API Reference"
    assert [page["title"] for page in api_reference["pages"]][:2] == ["Introduction", "User API"]


@pytest.mark.django_db
def test_mcp_docs_cover_safe_agent_onboarding(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="agentdocs",
        email="agentdocs@example.com",
        password="password123",
    )
    client.force_login(user)

    response = client.get(reverse("docs_page", kwargs={"category": "features", "page": "mcp"}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Provider-neutral setup" in content
    assert "search_member_articles" in content
    assert "CITEGUILD_API_KEY" in content
    assert "immediately revokes the previous value" in content
    assert "candidate ranking only" in content
    assert "never an API key" in content
    assert "?api_key=" not in content
