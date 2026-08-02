import logging
from typing import Any

from django.conf import settings
from django.db import transaction
from django_q.tasks import async_task

from apps.core.models import Profile

logger = logging.getLogger(__name__)

ANALYTICS_CONSENT_COOKIE = "analytics_consent"
EVENT_PREFIX = "citeguild"
SIGNUP_COMPLETED = f"{EVENT_PREFIX}_signup_completed"
USER_LOGGED_IN = f"{EVENT_PREFIX}_user_logged_in"
ACCOUNT_DELETED = f"{EVENT_PREFIX}_account_deleted"
CHECKOUT_STARTED = f"{EVENT_PREFIX}_checkout_started"


def has_analytics_consent(request) -> bool:
    """Return whether this browser explicitly opted in to product analytics."""
    return bool(request and request.COOKIES.get(ANALYTICS_CONSENT_COOKIE) == "granted")


def track_event(
    profile: Profile,
    event_name: str,
    properties: dict[str, Any] | None = None,
    *,
    current_state: str | None = None,
    insert_id: str | None = None,
    source_function: str | None = None,
) -> str:
    """Queue a privacy-safe profile event after the surrounding transaction commits."""
    if not settings.POSTHOG_API_KEY:
        return "PostHog API key not found."

    profile_id = profile.id
    state_snapshot = current_state if current_state is not None else profile.state
    event_properties = properties or {}

    def enqueue_event() -> None:
        try:
            async_task(
                "apps.core.tasks.track_event",
                profile_id=profile_id,
                event_name=event_name,
                current_state=state_snapshot,
                properties=event_properties,
                insert_id=insert_id,
                source_function=source_function,
                group="Track PostHog Event",
            )
        except Exception as error:
            logger.warning(
                "posthog.event.enqueue_failed",
                extra={
                    "event.name": "posthog.event.enqueue_failed",
                    "profile_id": profile_id,
                    "analytics_event_name": event_name,
                    "error.type": type(error).__name__,
                    "outcome": "failure",
                },
            )

    connection = transaction.get_connection()
    if connection.in_atomic_block:
        transaction.on_commit(enqueue_event)
    else:
        enqueue_event()

    return f"Queued event {event_name} for profile {profile_id}"


def track_account_deleted_event(profile: Profile) -> str:
    """Queue deletion without requiring the profile to exist when the task runs."""
    if not settings.POSTHOG_API_KEY:
        return "PostHog API key not found."

    profile_id = profile.id
    current_state = profile.state

    def enqueue_event() -> None:
        async_task(
            "apps.core.tasks.track_account_deleted_event",
            profile_id=profile_id,
            current_state=current_state,
            group="Track PostHog Event",
        )

    connection = transaction.get_connection()
    if connection.in_atomic_block:
        transaction.on_commit(enqueue_event)
    else:
        enqueue_event()

    return f"Queued account deletion event for profile {profile_id}"
