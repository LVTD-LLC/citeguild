from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.core import signals
from apps.core.choices import ProfileStates
from apps.core.models import Profile


@pytest.mark.django_db
def test_user_save_does_not_revert_profile_state(sync_state_transitions):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username="signaluser",
        email="signaluser@example.com",
        password="password123",
    )
    profile = user.profile

    Profile.objects.filter(id=profile.id).update(state=ProfileStates.STRANGER)

    cached_user = user_model.objects.select_related("profile").get(id=user.id)

    Profile.objects.filter(id=profile.id).update(state=ProfileStates.SIGNED_UP)

    cached_user.save()

    profile.refresh_from_db()
    assert profile.state == ProfileStates.SIGNED_UP


@pytest.mark.parametrize(
    ("profile_state", "expected_state"),
    [
        (ProfileStates.STRANGER, ProfileStates.SIGNED_UP),
        (ProfileStates.SUBSCRIBED, ProfileStates.SUBSCRIBED),
    ],
)
def test_login_analytics_snapshots_effective_lifecycle_state(
    profile_state,
    expected_state,
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(
        signals,
        "track_event",
        lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs),
    )
    user = SimpleNamespace(
        profile=SimpleNamespace(state=profile_state),
        backend="allauth.account.auth_backends.AuthenticationBackend",
    )
    request = SimpleNamespace(COOKIES={"analytics_consent": "granted"})

    signals.track_user_login(sender=None, request=request, user=user)

    assert captured["kwargs"]["current_state"] == expected_state
