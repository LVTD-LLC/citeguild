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
    recurring = price.get("recurring") or {}
    metadata = price.get("metadata") or {}
    product = price.get("product") or {}
    product_metadata = product.get("metadata") or {}
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
