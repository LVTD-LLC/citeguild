import logging
from datetime import UTC, datetime

from django.db import transaction

from apps.core.choices import ProfileStates
from apps.core.models import Profile, ProfileStateTransition

logger = logging.getLogger(__name__)


def get_profile_for_customer(customer_id, metadata=None):
    profile = (
        Profile.objects.filter(stripe_customer_id=customer_id).first() if customer_id else None
    )
    if not profile and metadata:
        profile_id = metadata.get("profile_id")
        user_id = metadata.get("user_id") or metadata.get("pk")
        try:
            if profile_id:
                profile = Profile.objects.filter(id=int(profile_id)).first()
            elif user_id:
                profile = Profile.objects.filter(user_id=int(user_id)).first()
        except (ValueError, TypeError):
            profile = None
    return profile


def get_subscription_target_state(subscription_data):
    status = subscription_data.get("status")
    if status in {"active", "past_due"}:
        if subscription_data.get("cancel_at_period_end"):
            return ProfileStates.CANCELLED
        return ProfileStates.SUBSCRIBED
    if status in {"canceled", "unpaid", "incomplete_expired"}:
        return ProfileStates.CHURNED
    return None


def _record_state(profile, target_state, event):
    if not target_state or profile.state == target_state:
        return
    ProfileStateTransition.objects.create(
        profile=profile,
        backup_profile_id=profile.id,
        from_state=profile.state,
        to_state=target_state,
        metadata={"stripe_event_id": event.get("id"), "stripe_event_type": event.get("type")},
    )
    profile.state = target_state


@transaction.atomic
def apply_subscription_event(event, *, deleted=False):
    subscription = event["data"]["object"]
    profile = get_profile_for_customer(subscription.get("customer"), subscription.get("metadata"))
    if not profile:
        logger.warning("stripe.subscription.profile_missing", extra={"event_id": event.get("id")})
        return

    profile = Profile.objects.select_for_update().get(pk=profile.pk)
    event_created = int(event.get("created") or 0)
    if event_created < profile.stripe_last_event_created:
        logger.info("stripe.subscription.stale_event", extra={"event_id": event.get("id")})
        return

    status = "canceled" if deleted else (subscription.get("status") or "")
    terminal_statuses = {"canceled", "unpaid", "incomplete_expired"}
    if (
        event_created == profile.stripe_last_event_created
        and profile.stripe_subscription_status in terminal_statuses
        and status not in terminal_statuses
    ):
        logger.info("stripe.subscription.stale_event", extra={"event_id": event.get("id")})
        return
    target_state = get_subscription_target_state({**subscription, "status": status})
    _record_state(profile, target_state, event)
    profile.stripe_customer_id = subscription.get("customer") or profile.stripe_customer_id
    profile.stripe_subscription_id = "" if deleted else (subscription.get("id") or "")
    profile.stripe_subscription_status = status
    profile.stripe_cancel_at_period_end = bool(subscription.get("cancel_at_period_end"))
    period_end = subscription.get("current_period_end")
    profile.stripe_current_period_end = (
        datetime.fromtimestamp(period_end, tz=UTC) if period_end else None
    )
    profile.stripe_last_event_created = event_created
    profile.stripe_last_event_id = event.get("id") or ""
    profile.save()


def handle_created_subscription(event):
    apply_subscription_event(event)


def handle_updated_subscription(event):
    apply_subscription_event(event)


def handle_deleted_subscription(event):
    apply_subscription_event(event, deleted=True)


def handle_checkout_completed(event):
    """Associate Stripe IDs only; subscription webhooks exclusively grant access."""
    checkout = event["data"]["object"]
    if checkout.get("mode") != "subscription":
        return
    profile = get_profile_for_customer(checkout.get("customer"), checkout.get("metadata"))
    if not profile:
        return
    update_fields = []
    for field, value in (
        ("stripe_customer_id", checkout.get("customer")),
        ("stripe_subscription_id", checkout.get("subscription")),
    ):
        if value and getattr(profile, field) != value:
            setattr(profile, field, value)
            update_fields.append(field)
    if update_fields:
        profile.save(update_fields=[*update_fields, "updated_at"])


EVENT_HANDLERS = {
    "customer.subscription.created": handle_created_subscription,
    "customer.subscription.updated": handle_updated_subscription,
    "customer.subscription.deleted": handle_deleted_subscription,
    "checkout.session.completed": handle_checkout_completed,
}
