import pytest

from apps.core.choices import ProfileStates
from apps.core.models import Profile
from apps.core.stripe_webhooks import (
    handle_created_subscription,
    handle_deleted_subscription,
    handle_updated_subscription,
)
from apps.core.tests.test_helpers import build_subscription_event


@pytest.mark.django_db
def test_active_subscription_grants_access_synchronously(profile):
    event = build_subscription_event(
        status="active",
        customer_id="cus_active",
        subscription_id="sub_active",
        metadata={"profile_id": profile.id},
        current_period_end=1_900_000_000,
        created=200,
    )

    handle_created_subscription(event)

    profile.refresh_from_db()
    assert profile.stripe_subscription_status == "active"
    assert profile.state == ProfileStates.SUBSCRIBED
    assert profile.has_active_subscription is True


@pytest.mark.django_db
def test_trial_does_not_grant_access(profile):
    event = build_subscription_event(
        status="trialing", metadata={"profile_id": profile.id}, created=200
    )

    handle_created_subscription(event)

    profile.refresh_from_db()
    assert profile.stripe_subscription_status == "trialing"
    assert profile.has_active_subscription is False


@pytest.mark.django_db
def test_scheduled_cancellation_keeps_access_through_paid_period(profile):
    event = build_subscription_event(
        status="active",
        metadata={"profile_id": profile.id},
        cancel_at_period_end=True,
        current_period_end=1_900_000_000,
        created=200,
    )

    handle_updated_subscription(event)

    profile.refresh_from_db()
    assert profile.state == ProfileStates.CANCELLED
    assert profile.stripe_cancel_at_period_end is True
    assert profile.has_active_subscription is True


@pytest.mark.django_db
def test_stale_subscription_event_cannot_restore_access(profile):
    Profile.objects.filter(id=profile.id).update(
        stripe_subscription_status="canceled",
        stripe_last_event_created=300,
        stripe_last_event_id="evt_new",
    )
    stale = build_subscription_event(
        status="active", metadata={"profile_id": profile.id}, created=200
    )

    handle_updated_subscription(stale)

    profile.refresh_from_db()
    assert profile.stripe_subscription_status == "canceled"
    assert profile.stripe_last_event_id == "evt_new"
    assert profile.has_active_subscription is False


@pytest.mark.django_db
def test_same_second_event_cannot_overwrite_terminal_status(profile):
    Profile.objects.filter(id=profile.id).update(
        stripe_subscription_status="canceled",
        stripe_last_event_created=300,
        stripe_last_event_id="evt_terminal",
    )
    event = build_subscription_event(
        status="active", metadata={"profile_id": profile.id}, created=300
    )

    handle_updated_subscription(event)

    profile.refresh_from_db()
    assert profile.stripe_subscription_status == "canceled"
    assert profile.stripe_last_event_id == "evt_terminal"


@pytest.mark.django_db
def test_deleted_subscription_revokes_access_and_clears_id(profile):
    Profile.objects.filter(id=profile.id).update(
        stripe_customer_id="cus_deleted",
        stripe_subscription_id="sub_deleted",
        stripe_subscription_status="active",
    )
    event = build_subscription_event(
        status="canceled",
        customer_id="cus_deleted",
        subscription_id="sub_deleted",
        created=300,
    )

    handle_deleted_subscription(event)

    profile.refresh_from_db()
    assert profile.state == ProfileStates.CHURNED
    assert profile.stripe_subscription_status == "canceled"
    assert profile.stripe_subscription_id == ""
    assert profile.has_active_subscription is False
