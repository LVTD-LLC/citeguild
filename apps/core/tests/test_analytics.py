from types import SimpleNamespace

import pytest

from apps.core import tasks
from apps.core.analytics import EVENT_PREFIX, has_analytics_consent, track_event
from apps.core.context_processors import posthog_api_key


def test_analytics_requires_explicit_consent():
    assert has_analytics_consent(SimpleNamespace(COOKIES={"analytics_consent": "granted"}))
    assert not has_analytics_consent(SimpleNamespace(COOKIES={"analytics_consent": "denied"}))
    assert not has_analytics_consent(SimpleNamespace(COOKIES={}))
    assert not has_analytics_consent(None)


def test_browser_identity_exposes_profile_id_without_email(settings):
    settings.POSTHOG_API_KEY = "phc_test"
    settings.POSTHOG_BROWSER_HOST = "https://example.test"
    settings.ENVIRONMENT = "test"
    request = SimpleNamespace(
        resolver_match=SimpleNamespace(url_name="landing", route=""),
        user=SimpleNamespace(
            is_authenticated=True,
            profile=SimpleNamespace(id=7),
            email="private@example.com",
        ),
    )

    context = posthog_api_key(request)

    assert context["posthog_distinct_id"] == "7"
    assert "posthog_user_email" not in context
    assert "private@example.com" not in repr(context)


@pytest.mark.django_db
def test_track_event_queues_only_bounded_properties(
    profile,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.POSTHOG_API_KEY = "phc_test"
    queued = {}

    def fake_async_task(path, **kwargs):
        queued["path"] = path
        queued["kwargs"] = kwargs

    monkeypatch.setattr("apps.core.analytics.async_task", fake_async_task)

    with django_capture_on_commit_callbacks(execute=True):
        track_event(
            profile,
            f"{EVENT_PREFIX}_feature_completed",
            {"feature": "example"},
            source_function="test",
        )

    assert queued["path"] == "apps.core.tasks.track_event"
    assert queued["kwargs"]["profile_id"] == profile.id
    assert queued["kwargs"]["current_state"] == profile.state
    assert queued["kwargs"]["properties"] == {"feature": "example"}
    assert "email" not in queued["kwargs"]


@pytest.mark.django_db
def test_track_event_uses_profile_identity_without_email(profile, settings, monkeypatch):
    settings.POSTHOG_API_KEY = "phc_test"
    settings.ENVIRONMENT = "test"
    captures = []
    monkeypatch.setattr(
        tasks.posthog,
        "capture",
        lambda *args, **kwargs: captures.append((args, kwargs)),
    )

    result = tasks.track_event(
        profile.id,
        f"{EVENT_PREFIX}_feature_completed",
        profile.state,
        {"feature": "example"},
    )

    assert result == f"Tracked event {EVENT_PREFIX}_feature_completed for profile {profile.id}"
    args, kwargs = captures[0]
    assert args == (f"{EVENT_PREFIX}_feature_completed",)
    assert kwargs["distinct_id"] == str(profile.id)
    assert kwargs["properties"] == {
        "event_version": 1,
        "environment": "test",
        "profile_id": profile.id,
        "current_state": profile.state,
        "feature": "example",
    }
    assert profile.user.email not in repr(captures)
