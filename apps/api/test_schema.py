import pytest
import schemathesis
from django.core.wsgi import get_wsgi_application
from hypothesis import HealthCheck, settings

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
def test_openapi_contract(case, api_key):
    """Generated requests never crash and successful responses match OpenAPI."""
    case.call_and_validate(headers={"X-API-Key": api_key})
