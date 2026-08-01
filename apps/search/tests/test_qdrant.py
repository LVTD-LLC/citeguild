from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings


@pytest.fixture(autouse=True)
def clear_qdrant_client_cache():
    from apps.search.qdrant import get_qdrant_client

    get_qdrant_client.cache_clear()
    yield
    get_qdrant_client.cache_clear()


@override_settings(
    QDRANT_URL="http://qdrant:6333",
    QDRANT_API_KEY="test-api-key",
    QDRANT_TIMEOUT_SECONDS=7.5,
)
def test_get_qdrant_client_uses_configured_connection():
    from apps.search.qdrant import get_qdrant_client

    with patch("apps.search.qdrant.QdrantClient") as client_class:
        client = get_qdrant_client()

    assert client is client_class.return_value
    client_class.assert_called_once_with(
        url="http://qdrant:6333",
        api_key="test-api-key",
        timeout=7.5,
    )


@override_settings(QDRANT_URL="", QDRANT_API_KEY="test-api-key")
def test_get_qdrant_client_requires_url():
    from apps.search.qdrant import get_qdrant_client

    with pytest.raises(ImproperlyConfigured, match="QDRANT_URL"):
        get_qdrant_client()


@override_settings(QDRANT_URL="http://qdrant:6333", QDRANT_API_KEY="")
def test_get_qdrant_client_requires_api_key():
    from apps.search.qdrant import get_qdrant_client

    with pytest.raises(ImproperlyConfigured, match="QDRANT_API_KEY"):
        get_qdrant_client()


@override_settings(
    QDRANT_URL="http://qdrant:6333",
    QDRANT_API_KEY="test-api-key",
    QDRANT_TIMEOUT_SECONDS=5.0,
)
def test_get_qdrant_client_reuses_client():
    from apps.search.qdrant import get_qdrant_client

    with patch("apps.search.qdrant.QdrantClient") as client_class:
        first_client = get_qdrant_client()
        second_client = get_qdrant_client()

    assert first_client is second_client
    client_class.assert_called_once()
