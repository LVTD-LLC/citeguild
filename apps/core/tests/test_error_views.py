from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.db import OperationalError
from django.test import RequestFactory
from django.urls import get_resolver

from citeguild.error_views import page_not_found


def test_404_renders_without_database_or_request_context():
    # No django_db marker: any database access also fails this test.
    request = RequestFactory().get("/missing/")
    with patch(
        "apps.core.context_processors.current_state",
        side_effect=OperationalError("closed database connection"),
    ) as context_processor:
        response = page_not_found(request, Exception("private details"))
    assert response.status_code == 404
    assert b"Page not found" in response.content
    assert b"private details" not in response.content
    context_processor.assert_not_called()
    assert get_resolver().resolve_error_handler(404) is page_not_found


def test_missing_route_is_404_under_asgi(async_client, settings):
    settings.DEBUG = False
    response = async_to_sync(async_client.get)("/missing-error-regression/")
    assert response.status_code == 404
    assert b"Page not found" in response.content
