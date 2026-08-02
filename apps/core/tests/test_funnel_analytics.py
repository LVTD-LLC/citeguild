import pytest

from apps.core.funnel_analytics import (
    SEARCH_COMPLETED,
    SITE_SUBMITTED,
    FunnelEventError,
    track_funnel_event,
)


@pytest.mark.django_db
def test_funnel_event_queues_allowlisted_properties_and_stable_insert_id(
    profile,
    settings,
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    settings.POSTHOG_API_KEY = "phc_test"
    queued = []
    monkeypatch.setattr(
        "apps.core.analytics.async_task",
        lambda path, **kwargs: queued.append((path, kwargs)),
    )

    for _attempt in range(2):
        with django_capture_on_commit_callbacks(execute=True):
            track_funnel_event(
                profile,
                SITE_SUBMITTED,
                {"site_id": "site-uuid", "sitemap_kind": "urlset"},
                idempotency_key="project:site-uuid",
                source_function="test",
            )

    assert len(queued) == 2
    assert queued[0][0] == "apps.core.tasks.track_event"
    first = queued[0][1]
    second = queued[1][1]
    assert first["properties"] == {"site_id": "site-uuid", "sitemap_kind": "urlset"}
    assert first["insert_id"] == second["insert_id"]
    assert len(first["insert_id"]) == 64
    assert "site-uuid" not in first["insert_id"]


@pytest.mark.django_db
def test_funnel_event_rejects_unknown_or_sensitive_properties(profile, settings):
    settings.POSTHOG_API_KEY = "phc_test"

    with pytest.raises(FunnelEventError, match="Unknown properties"):
        track_funnel_event(
            profile,
            SEARCH_COMPLETED,
            {
                "transport": "api",
                "status": "succeeded",
                "query_chars": 10,
                "result_count": 1,
                "limit": 10,
                "language_filter": False,
                "excluded_domain_count": 0,
                "duration_ms": 4,
                "input_tokens": 3,
                "raw_query": "private draft text",
            },
        )

    with pytest.raises(FunnelEventError, match="Missing required"):
        track_funnel_event(profile, SITE_SUBMITTED, {"site_id": "site-uuid"})


@pytest.mark.django_db
def test_funnel_event_rejects_unbounded_values(profile, settings):
    settings.POSTHOG_API_KEY = "phc_test"

    with pytest.raises(FunnelEventError, match="bounded scalar"):
        track_funnel_event(
            profile,
            SITE_SUBMITTED,
            {"site_id": "x" * 129, "sitemap_kind": "urlset"},
        )

    with pytest.raises(FunnelEventError, match="URL or email-like"):
        track_funnel_event(
            profile,
            SITE_SUBMITTED,
            {"site_id": "https://private.example/sitemap.xml", "sitemap_kind": "urlset"},
        )
