from functools import cache

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from qdrant_client import QdrantClient


@cache
def get_qdrant_client() -> QdrantClient:
    """Return the shared authenticated Qdrant client without reading or writing vectors."""
    if not settings.QDRANT_URL:
        raise ImproperlyConfigured("QDRANT_URL must be configured before using Qdrant.")
    if not settings.QDRANT_API_KEY:
        raise ImproperlyConfigured("QDRANT_API_KEY must be configured before using Qdrant.")

    return QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )
