import logging

import stripe
from django.conf import settings

from apps.core.choices import ProfileStates
from apps.core.models import Profile

stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


def get_profile_for_customer(customer_id, metadata=None):
    profile = None
    if customer_id:
        profile = Profile.objects.filter(stripe_customer_id=customer_id).first()

    if not profile and metadata:
        user_id = metadata.get("user_id") or metadata.get("pk")
        if user_id:
            try:
                profile = Profile.objects.get(user_id=int(user_id))
            except (Profile.DoesNotExist, ValueError, TypeError):
                profile = None

    return profile


def update_profile_stripe_ids(profile, customer_id=None, subscription_id=None):
    update_fields = []
    if customer_id and profile.stripe_customer_id != customer_id:
        profile.stripe_customer_id = customer_id
        update_fields.append("stripe_customer_id")
    if subscription_id and profile.stripe_subscription_id != subscription_id:
        profile.stripe_subscription_id = subscription_id
        update_fields.append("stripe_subscription_id")
    if update_fields:
        profile.save(update_fields=update_fields)


def get_subscription_target_state(subscription_data, previous_status=None):
    status = subscription_data.get("status")
    cancel_at_period_end = subscription_data.get("cancel_at_period_end")
    cancel_at = subscription_data.get("cancel_at")
    cancellation_details = subscription_data.get("cancellation_details") or {}
    cancellation_reason = cancellation_details.get("reason") or cancellation_details.get("feedback")

    if status == "trialing":
        return ProfileStates.TRIAL_STARTED

    cancel_requested = bool(cancel_at_period_end) or bool(cancel_at) or bool(cancellation_reason)

    if cancel_requested and status in {"active", "past_due", "trialing"}:
        return ProfileStates.CANCELLED

    if status in {"active", "past_due"}:
        return ProfileStates.SUBSCRIBED

    if status in {"canceled", "unpaid", "incomplete_expired"}:
        if previous_status == "trialing":
            return ProfileStates.TRIAL_ENDED
        return ProfileStates.CHURNED

    return None


def handle_created_subscription(event):
    event_id = event.get("id")
    subscription_data = event["data"]["object"]
    customer_id = subscription_data.get("customer")
    subscription_id = subscription_data.get("id")

    profile = get_profile_for_customer(customer_id, subscription_data.get("metadata", {}))
    if not profile:
        logger.warning(
            "stripe.subscription.create.completed",
            extra={
                "event.name": "stripe.subscription.create.completed",
                "event_id": event_id,
                "customer_id": customer_id,
                "subscription_id": subscription_id,
                "operation.status": "profile_missing",
                "outcome": "failure",
            },
        )
        return

    update_profile_stripe_ids(profile, customer_id=customer_id, subscription_id=subscription_id)

    target_state = get_subscription_target_state(subscription_data)
    if target_state:
        profile.track_state_change(
            to_state=target_state,
            source_function="stripe_webhook handle_created_subscription",
            metadata={
                "event": "subscription_created",
                "subscription_id": subscription_id,
                "stripe_event_id": event_id,
                "status": subscription_data.get("status"),
                "cancel_at_period_end": subscription_data.get("cancel_at_period_end"),
                "trial_end": subscription_data.get("trial_end"),
            },
        )
    logger.info(
        "stripe.subscription.create.completed",
        extra={
            "event.name": "stripe.subscription.create.completed",
            "profile_id": profile.id,
            "subscription_id": subscription_id,
            "event_id": event_id,
            "subscription_status": subscription_data.get("status"),
            "target_state": target_state or "",
            "state_transition": bool(target_state),
            "outcome": "success",
        },
    )


def handle_updated_subscription(event):
    event_id = event.get("id")
    subscription_data = event["data"]["object"]
    customer_id = subscription_data.get("customer")
    subscription_id = subscription_data.get("id")

    profile = get_profile_for_customer(customer_id, subscription_data.get("metadata", {}))
    if not profile:
        logger.error(
            "stripe.subscription.update.completed",
            extra={
                "event.name": "stripe.subscription.update.completed",
                "event_id": event_id,
                "subscription_id": subscription_id,
                "customer_id": customer_id,
                "operation.status": "profile_missing",
                "outcome": "failure",
            },
        )
        return

    update_profile_stripe_ids(profile, customer_id=customer_id, subscription_id=subscription_id)

    previous_attributes = event.get("data", {}).get("previous_attributes", {}) or {}
    previous_status = previous_attributes.get("status")
    target_state = get_subscription_target_state(subscription_data, previous_status=previous_status)
    if target_state:
        profile.track_state_change(
            to_state=target_state,
            source_function="stripe_webhook handle_updated_subscription",
            metadata={
                "event": "subscription_updated",
                "subscription_id": subscription_id,
                "stripe_event_id": event_id,
                "status": subscription_data.get("status"),
                "previous_status": previous_status,
                "cancel_at_period_end": subscription_data.get("cancel_at_period_end"),
                "cancel_at": subscription_data.get("cancel_at"),
                "current_period_end": subscription_data.get("current_period_end"),
                "cancellation_details": subscription_data.get("cancellation_details"),
                "trial_end": subscription_data.get("trial_end"),
            },
        )

    logger.info(
        "stripe.subscription.update.completed",
        extra={
            "event.name": "stripe.subscription.update.completed",
            "event_id": event_id,
            "profile_id": profile.id,
            "subscription_id": subscription_id,
            "subscription_status": subscription_data.get("status"),
            "previous_status": previous_status or "",
            "target_state": target_state or "",
            "state_transition": bool(target_state),
            "outcome": "success",
        },
    )


def handle_deleted_subscription(event):
    event_id = event.get("id")
    subscription_data = event["data"]["object"]
    customer_id = subscription_data.get("customer")
    subscription_id = subscription_data.get("id")

    profile = get_profile_for_customer(customer_id, subscription_data.get("metadata", {}))
    if not profile:
        logger.error(
            "stripe.subscription.delete.completed",
            extra={
                "event.name": "stripe.subscription.delete.completed",
                "event_id": event_id,
                "subscription_id": subscription_id,
                "customer_id": customer_id,
                "operation.status": "profile_missing",
                "outcome": "failure",
            },
        )
        return

    profile.track_state_change(
        to_state=ProfileStates.CHURNED,
        source_function="stripe_webhook handle_deleted_subscription",
        metadata={
            "event": "subscription_deleted",
            "subscription_id": subscription_id,
            "ended_at": subscription_data.get("ended_at"),
        },
    )

    profile.stripe_subscription_id = ""
    profile.save(update_fields=["stripe_subscription_id"])

    logger.info(
        "stripe.subscription.delete.completed",
        extra={
            "event.name": "stripe.subscription.delete.completed",
            "event_id": event_id,
            "profile_id": profile.id,
            "subscription_id": subscription_id,
            "ended_at": subscription_data.get("ended_at"),
            "target_state": ProfileStates.CHURNED,
            "outcome": "success",
        },
    )


def handle_checkout_completed(event):
    event_id = event.get("id")
    checkout_data = event["data"]["object"]
    customer_id = checkout_data.get("customer")
    checkout_id = checkout_data.get("id")
    subscription_id = checkout_data.get("subscription")
    payment_status = checkout_data.get("payment_status")
    mode = checkout_data.get("mode")

    metadata = checkout_data.get("metadata", {})
    price_id = metadata.get("price_id")

    if payment_status != "paid":
        logger.warning(
            "stripe.checkout.completed",
            extra={
                "event.name": "stripe.checkout.completed",
                "event_id": event_id,
                "checkout_id": checkout_id,
                "payment_status": payment_status,
                "mode": mode,
                "metadata_count": len(metadata),
                "operation.status": "payment_incomplete",
                "outcome": "failure",
            },
        )
        return

    profile = get_profile_for_customer(customer_id, metadata)
    if not profile:
        logger.error(
            "stripe.checkout.completed",
            extra={
                "event.name": "stripe.checkout.completed",
                "event_id": event_id,
                "checkout_id": checkout_id,
                "customer_id": customer_id,
                "mode": mode,
                "metadata_count": len(metadata),
                "operation.status": "profile_missing",
                "outcome": "failure",
            },
        )
        return

    update_profile_stripe_ids(profile, customer_id=customer_id, subscription_id=subscription_id)

    if mode == "payment":
        amount_total = checkout_data.get("amount_total")
        currency = checkout_data.get("currency")
        payment_intent = checkout_data.get("payment_intent")

        profile.track_state_change(
            to_state=ProfileStates.SUBSCRIBED,
            source_function="stripe_webhook handle_checkout_completed",
            metadata={
                "event": "checkout_payment_completed",
                "payment_intent": payment_intent,
                "checkout_id": checkout_id,
                "amount": amount_total,
                "currency": currency,
                "price_id": price_id,
                "stripe_event_id": event_id,
            },
        )

        logger.info(
            "stripe.checkout.completed",
            extra={
                "event.name": "stripe.checkout.completed",
                "event_id": event_id,
                "profile_id": profile.id,
                "payment_intent": payment_intent,
                "checkout_id": checkout_id,
                "amount_total": amount_total,
                "currency": currency,
                "mode": mode,
                "payment_status": payment_status,
                "metadata_count": len(metadata),
                "outcome": "success",
            },
        )
    else:
        logger.info(
            "stripe.checkout.completed",
            extra={
                "event.name": "stripe.checkout.completed",
                "event_id": event_id,
                "checkout_id": checkout_id,
                "mode": mode,
                "payment_status": payment_status,
                "profile_id": profile.id,
                "metadata_count": len(metadata),
                "outcome": "success",
            },
        )


EVENT_HANDLERS = {
    "customer.subscription.created": handle_created_subscription,
    "customer.subscription.updated": handle_updated_subscription,
    "customer.subscription.deleted": handle_deleted_subscription,
    "checkout.session.completed": handle_checkout_completed,
}
