import pytest
import schemathesis
from django.core.wsgi import get_wsgi_application
from hypothesis import HealthCheck, settings
from schemathesis.specs.openapi.checks import positive_data_acceptance

application = get_wsgi_application()
config = schemathesis.Config.from_dict({"generation": {"mode": "positive"}})
schema = schemathesis.openapi.from_wsgi("/api/openapi.json", application, config=config)


@pytest.fixture
def api_key(profile):
    return profile.rotate_api_key()


@pytest.mark.django_db(transaction=True)
@schema.parametrize()
@settings(
    max_examples=25,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_openapi_contract(case, api_key, monkeypatch):
    """Generated requests never crash and successful responses match OpenAPI."""
    from apps.core.sitemap_submission import SitemapDocumentKind, SitemapValidation

    # Free members now reach URL validation. Mock network I/O, not membership.
    monkeypatch.setattr(
        "apps.core.sitemap_submission.validate_sitemap",
        lambda *args, **kwargs: SitemapValidation(SitemapDocumentKind.URL_SET),
    )
    # Schema-valid strings can still violate sitemap/DNS safety or domain rules.
    # Keep response-shape, status declaration, and server-error checks enabled.
    excluded = []
    if case.method.upper() == "POST" and case.path in {"/api/projects", "/api/v1/projects"}:
        excluded = [positive_data_acceptance]
    case.call_and_validate(headers={"X-API-Key": api_key}, excluded_checks=excluded)
