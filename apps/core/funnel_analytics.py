"""Canonical, privacy-minimized product funnel event contract."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from apps.core.models import Profile

EVENT_PREFIX = "citeguild"
SUBSCRIPTION_ACTIVATED = f"{EVENT_PREFIX}_subscription_activated"
SUBSCRIPTION_RETAINED = f"{EVENT_PREFIX}_subscription_retained"
SUBSCRIPTION_ENDED = f"{EVENT_PREFIX}_subscription_ended"
SITE_SUBMITTED = f"{EVENT_PREFIX}_site_submitted"
INITIAL_INDEX_COMPLETED = f"{EVENT_PREFIX}_initial_index_completed"
INITIAL_INDEX_FAILED = f"{EVENT_PREFIX}_initial_index_failed"
AGENT_CREDENTIAL_CREATED = f"{EVENT_PREFIX}_agent_credential_created"
SEARCH_COMPLETED = f"{EVENT_PREFIX}_search_completed"
CITATION_DETECTED = f"{EVENT_PREFIX}_citation_detected"
CITATION_REMOVED = f"{EVENT_PREFIX}_citation_removed"
EMBEDDING_COMPLETED = f"{EVENT_PREFIX}_embedding_completed"


@dataclass(frozen=True, slots=True)
class EventSpec:
    required: frozenset[str]
    optional: frozenset[str] = frozenset()
    durable: bool = False


_SUBSCRIPTION_PROPERTIES = frozenset(
    {"subscription_status", "previous_status", "cancel_at_period_end"}
)
_INDEX_PROPERTIES = frozenset(
    {
        "site_id",
        "status",
        "total_pages",
        "succeeded_pages",
        "failed_pages",
        "active_articles",
        "duration_ms",
    }
)
EVENT_SPECS = {
    SUBSCRIPTION_ACTIVATED: EventSpec(_SUBSCRIPTION_PROPERTIES, durable=True),
    SUBSCRIPTION_RETAINED: EventSpec(_SUBSCRIPTION_PROPERTIES, durable=True),
    SUBSCRIPTION_ENDED: EventSpec(_SUBSCRIPTION_PROPERTIES, durable=True),
    SITE_SUBMITTED: EventSpec(
        frozenset({"site_id", "sitemap_kind"}),
        durable=True,
    ),
    INITIAL_INDEX_COMPLETED: EventSpec(_INDEX_PROPERTIES, durable=True),
    INITIAL_INDEX_FAILED: EventSpec(
        _INDEX_PROPERTIES | {"error_code", "retryable"},
        durable=True,
    ),
    AGENT_CREDENTIAL_CREATED: EventSpec(
        frozenset({"credential_kind", "rotation"}),
        durable=True,
    ),
    SEARCH_COMPLETED: EventSpec(
        frozenset(
            {
                "transport",
                "status",
                "query_chars",
                "result_count",
                "limit",
                "language_filter",
                "excluded_domain_count",
                "duration_ms",
                "input_tokens",
            }
        ),
        frozenset({"error_code", "retryable"}),
    ),
    CITATION_DETECTED: EventSpec(
        frozenset({"direction", "site_id", "matched_page", "active"}),
        durable=True,
    ),
    CITATION_REMOVED: EventSpec(
        frozenset({"direction", "site_id", "matched_page", "active"}),
        durable=True,
    ),
    EMBEDDING_COMPLETED: EventSpec(
        frozenset(
            {
                "site_id",
                "status",
                "input_chars",
                "input_tokens",
                "duration_ms",
                "model",
            }
        ),
        frozenset({"error_code", "retryable"}),
    ),
}
DURABLE_FUNNEL_EVENTS = frozenset(
    event_name for event_name, spec in EVENT_SPECS.items() if spec.durable
)


class FunnelEventError(ValueError):
    """Raised before any unsafe or off-contract analytics value is queued."""


def _validate_properties(event_name: str, properties: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = EVENT_SPECS[event_name]
    except KeyError as error:
        raise FunnelEventError(f"Unknown funnel event: {event_name}") from error

    keys = set(properties)
    missing = spec.required - keys
    if missing:
        raise FunnelEventError(f"Missing required properties: {sorted(missing)}")
    unknown = keys - spec.required - spec.optional
    if unknown:
        raise FunnelEventError(f"Unknown properties: {sorted(unknown)}")

    for key, value in properties.items():
        is_scalar = type(value) in {bool, int, float} or isinstance(value, str)
        if not is_scalar or isinstance(value, str) and len(value) > 128:
            raise FunnelEventError(f"{key} must be a bounded scalar")
        if isinstance(value, str) and ("://" in value or "@" in value):
            raise FunnelEventError(f"{key} must not contain URL or email-like data")
        if isinstance(value, float) and not math.isfinite(value):
            raise FunnelEventError(f"{key} must be a bounded scalar")
    return dict(properties)


def _insert_id(profile_id: int, event_name: str, idempotency_key: str) -> str:
    material = f"{EVENT_PREFIX}:{profile_id}:{event_name}:{idempotency_key}".encode()
    return hashlib.sha256(material).hexdigest()


def track_funnel_event(
    profile: Profile,
    event_name: str,
    properties: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    source_function: str | None = None,
) -> str:
    """Queue one contract-checked server event without raw content, URLs, or PII."""
    from apps.core.analytics import track_event

    safe_properties = _validate_properties(event_name, properties)
    insert_id = None
    if idempotency_key:
        insert_id = _insert_id(profile.id, event_name, str(idempotency_key))
    return track_event(
        profile,
        event_name,
        safe_properties,
        insert_id=insert_id,
        source_function=source_function,
    )
