from collections.abc import Mapping
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class MonthlyPriceContract:
    amount: int = 1000
    currency: str = "usd"
    interval: str = "month"
    interval_count: int = 1
    plan: str = "single_monthly"


MONTHLY_PRICE = MonthlyPriceContract()


def validate_monthly_price(price) -> None:
    """Fail closed if Stripe configuration drifts from the public $10 contract."""
    if not isinstance(price, Mapping):
        to_dict = getattr(price, "to_dict", None)
        if not callable(to_dict):
            raise ImproperlyConfigured("Stripe monthly Price response is invalid.")
        price = to_dict()
    if not isinstance(price, Mapping):
        raise ImproperlyConfigured("Stripe monthly Price response is invalid.")

    recurring = price.get("recurring") or {}
    metadata = price.get("metadata") or {}
    product = price.get("product") or {}
    if not all(isinstance(value, Mapping) for value in (recurring, metadata, product)):
        raise ImproperlyConfigured("Stripe monthly Price response is invalid.")
    product_metadata = product.get("metadata") or {}
    if not isinstance(product_metadata, Mapping):
        raise ImproperlyConfigured("Stripe monthly Price response is invalid.")
    valid = (
        price.get("id") == settings.STRIPE_PRICE_ID_MONTHLY
        and price.get("active") is True
        and price.get("unit_amount") == MONTHLY_PRICE.amount
        and price.get("currency") == MONTHLY_PRICE.currency
        and recurring.get("interval") == MONTHLY_PRICE.interval
        and recurring.get("interval_count") == MONTHLY_PRICE.interval_count
        and metadata.get("citeguild_plan") == MONTHLY_PRICE.plan
        and product_metadata.get("citeguild") == "true"
    )
    if not valid:
        raise ImproperlyConfigured("Stripe monthly Price does not match CiteGuild's $10 contract.")
