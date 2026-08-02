import logging

import posthog
from django.conf import settings

from apps.core.analytics import ACCOUNT_DELETED, CHECKOUT_STARTED, SIGNUP_COMPLETED
from apps.core.funnel_analytics import DURABLE_FUNNEL_EVENTS

logger = logging.getLogger(__name__)

POSTHOG_DURABLE_EVENTS = frozenset(
    {ACCOUNT_DELETED, CHECKOUT_STARTED, SIGNUP_COMPLETED, *DURABLE_FUNNEL_EVENTS}
)


def track_event(
    profile_id: int,
    event_name: str,
    current_state: str,
    properties: dict | None = None,
    insert_id: str = None,
    source_function: str = None,
) -> str:
    if not settings.POSTHOG_API_KEY:
        return "PostHog API key not found."

    base_log_data = {
        "event.name": "posthog.event.completed",
        "profile_id": profile_id,
        "analytics_event_name": event_name,
        "properties_count": len(properties or {}),
        "source_function": source_function,
    }

    event_properties = {
        **(properties or {}),
        "event_version": 1,
        "environment": settings.ENVIRONMENT,
        "profile_id": profile_id,
        "current_state": current_state,
    }
    if insert_id:
        event_properties["$insert_id"] = insert_id

    posthog.capture(
        event_name,
        distinct_id=str(profile_id),
        properties=event_properties,
    )
    if event_name in POSTHOG_DURABLE_EVENTS:
        posthog.flush(timeout_seconds=5)

    logger.info(
        "posthog.event.completed",
        extra={
            **base_log_data,
            "event.name": "posthog.event.completed",
            "operation.status": "captured",
            "outcome": "success",
        },
    )

    return f"Tracked event {event_name} for profile {profile_id}"


def track_account_deleted_event(profile_id: int, current_state: str) -> str:
    """Capture deletion from values snapshotted before the profile was removed."""
    if not settings.POSTHOG_API_KEY:
        return "PostHog API key not found."

    posthog.capture(
        ACCOUNT_DELETED,
        distinct_id=str(profile_id),
        properties={
            "event_version": 1,
            "environment": settings.ENVIRONMENT,
            "profile_id": profile_id,
            "current_state": current_state,
        },
    )
    posthog.flush(timeout_seconds=5)
    logger.info(
        "posthog.account_deleted.completed",
        extra={
            "event.name": "posthog.account_deleted.completed",
            "profile_id": profile_id,
            "analytics_event_name": ACCOUNT_DELETED,
            "operation.status": "captured",
            "outcome": "success",
        },
    )
    return f"Tracked account deletion event for profile {profile_id}"


def track_state_change(
    profile_id: int,
    from_state: str,
    to_state: str,
    metadata: dict = None,
    source_function: str = None,
) -> None:
    from apps.core.models import Profile, ProfileStateTransition

    base_log_data = {
        "event.name": "profile.state_change.completed",
        "profile_id": profile_id,
        "from_state": from_state,
        "to_state": to_state,
        "metadata_count": len(metadata or {}),
        "source_function": source_function,
    }

    try:
        profile = Profile.objects.get(id=profile_id)
    except Profile.DoesNotExist:
        logger.error(
            "profile.state_change.completed",
            extra={
                **base_log_data,
                "event.name": "profile.state_change.completed",
                "operation.status": "profile_missing",
                "outcome": "failure",
                "error.type": "Profile.DoesNotExist",
            },
        )
        return f"Profile with id {profile_id} not found."

    if from_state != to_state:
        ProfileStateTransition.objects.create(
            profile=profile,
            from_state=from_state,
            to_state=to_state,
            backup_profile_id=profile_id,
            metadata=metadata,
        )
        profile.state = to_state
        profile.save(update_fields=["state"])

    logger.info(
        "profile.state_change.completed",
        extra={
            **base_log_data,
            "event.name": "profile.state_change.completed",
            "operation.status": "changed" if from_state != to_state else "unchanged",
            "outcome": "success",
        },
    )

    return f"Tracked state change from {from_state} to {to_state} for profile {profile_id}"
