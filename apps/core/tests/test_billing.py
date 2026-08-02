from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import stripe
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import override_settings
from django.urls import reverse

from apps.core.access import subscription_required
from apps.core.billing import validate_monthly_price
from apps.core.models import StripeWebhookEvent
from apps.core.views import construct_stripe_event


def _price(**overrides):
    price = {
        "id": "price_monthly",
        "active": True,
        "unit_amount": 1000,
        "currency": "usd",
        "recurring": {"interval": "month", "interval_count": 1},
        "metadata": {"citeguild_plan": "single_monthly"},
        "product": {"metadata": {"citeguild": "true"}},
    }
    price.update(overrides)
    return price


@override_settings(STRIPE_PRICE_ID_MONTHLY="price_monthly")
def test_monthly_price_contract_accepts_exact_ten_dollar_price():
    validate_monthly_price(_price())


@override_settings(STRIPE_PRICE_ID_MONTHLY="price_monthly")
def test_monthly_price_contract_accepts_stripe_sdk_price():
    price = stripe.Price.construct_from(_price(), "sk_test_value")

    validate_monthly_price(price)


def test_monthly_price_contract_rejects_unsupported_response():
    with pytest.raises(ImproperlyConfigured, match="response is invalid"):
        validate_monthly_price(SimpleNamespace())


@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
@patch("apps.core.views.stripe.Webhook.construct_event")
def test_construct_stripe_event_normalizes_sdk_object(construct_event, rf):
    construct_event.return_value = stripe.Event.construct_from(
        {"id": "evt_sdk", "type": "test.event", "created": 123, "data": {"object": {}}},
        "sk_test_value",
    )
    request = rf.post("/stripe-webhook/", data=b"{}", content_type="application/json")
    request.META["HTTP_STRIPE_SIGNATURE"] = "t=123,v1=test"

    event, error = construct_stripe_event(request)

    assert error is None
    assert event["id"] == "evt_sdk"
    assert isinstance(event, dict)


@override_settings(STRIPE_PRICE_ID_MONTHLY="price_monthly")
@pytest.mark.parametrize(
    "field,value", [("unit_amount", 999), ("currency", "eur"), ("active", False)]
)
def test_monthly_price_contract_fails_closed_on_drift(field, value):
    with pytest.raises(ImproperlyConfigured):
        validate_monthly_price(_price(**{field: value}))


@pytest.mark.django_db
def test_subscription_required_redirects_inactive_user(rf, user):
    request = rf.get("/sites/new")
    request.user = user
    protected = subscription_required(lambda request: HttpResponse("ok"))

    response = protected(request)

    assert response.status_code == 302
    assert response.url == reverse("pricing")


@pytest.mark.django_db
@override_settings(
    STRIPE_PRICE_ID_MONTHLY="price_monthly",
    STRIPE_SECRET_KEY="sk_test_value",
    STRIPE_CONTEXT="acct_lvtd",
)
@patch("apps.core.views.stripe.checkout.Session.create")
@patch("apps.core.views.stripe.Customer.create")
@patch("apps.core.views.stripe.Price.retrieve")
def test_checkout_is_fixed_post_only_contract(
    retrieve, create_customer, create_session, auth_client
):
    retrieve.return_value = stripe.Price.construct_from(_price(), "sk_test_value")
    create_customer.return_value = SimpleNamespace(id="cus_test")
    create_session.return_value = SimpleNamespace(url="https://checkout.stripe.test/session")
    url = reverse("user_upgrade_checkout_session")

    assert auth_client.get(url).status_code == 405
    response = auth_client.post(url)

    assert response.status_code == 303
    params = create_session.call_args.kwargs
    assert params["mode"] == "subscription"
    assert params["line_items"] == [{"price": "price_monthly", "quantity": 1}]
    assert params["metadata"]["plan"] == "single_monthly"
    assert params["stripe_context"] == "acct_lvtd"
    assert "allow_promotion_codes" not in params
    assert params["idempotency_key"].startswith("citeguild-checkout-")


@pytest.mark.django_db
@override_settings(STRIPE_WEBHOOK_SECRET="whsec_test")
@patch("apps.core.views.construct_stripe_event")
def test_webhook_event_receipt_is_durable_and_duplicate_safe(construct_event, client):
    handler = Mock()
    event = {"id": "evt_durable", "type": "test.event", "created": 123, "data": {"object": {}}}
    construct_event.return_value = (event, None)

    with patch.dict("apps.core.views.EVENT_HANDLERS", {"test.event": handler}):
        assert client.post(reverse("stripe_webhook")).status_code == 200
        assert client.post(reverse("stripe_webhook")).status_code == 200

    assert handler.call_count == 1
    assert StripeWebhookEvent.objects.filter(event_id="evt_durable").count() == 1
