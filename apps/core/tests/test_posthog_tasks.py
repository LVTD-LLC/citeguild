from apps.core import tasks


def test_track_event_uses_event_first_posthog_capture_signature(monkeypatch):
    monkeypatch.setattr(tasks.settings, "POSTHOG_API_KEY", "phc_test")
    captures = []
    monkeypatch.setattr(
        tasks.posthog,
        "capture",
        lambda event, **kwargs: captures.append((event, kwargs)),
    )

    tasks.track_event(
        7,
        "dataset_created",
        "signed_up",
        {"dataset_id": 3},
        source_function="test",
    )

    assert captures == [
        (
            "dataset_created",
            {
                "distinct_id": "7",
                "properties": {
                    "event_version": 1,
                    "environment": tasks.settings.ENVIRONMENT,
                    "site_host": tasks.analytics_site_host(),
                    "profile_id": 7,
                    "current_state": "signed_up",
                    "dataset_id": 3,
                },
            },
        )
    ]


def test_track_event_sends_posthog_insert_id_without_logging_source_key(monkeypatch):
    monkeypatch.setattr(tasks.settings, "POSTHOG_API_KEY", "phc_test")
    captures = []
    records = []
    monkeypatch.setattr(
        tasks.posthog,
        "capture",
        lambda event, **kwargs: captures.append((event, kwargs)),
    )
    monkeypatch.setattr(
        tasks.logger, "info", lambda *args, **kwargs: records.append((args, kwargs))
    )

    tasks.track_event(
        7,
        "citeguild_site_submitted",
        "subscribed",
        {"site_id": "site-uuid"},
        insert_id="a" * 64,
        source_function="test",
    )

    assert captures[0][1]["properties"]["$insert_id"] == "a" * 64
    assert "$insert_id" not in repr(records)


def test_service_host_overrides_caller_supplied_host(settings, monkeypatch):
    settings.POSTHOG_API_KEY = "phc_test"
    settings.SITE_URL = "https://citeguild.com/path?ignored=value"
    captured = []
    monkeypatch.setattr(tasks.posthog, "capture", lambda *a, **kw: captured.append(kw))
    monkeypatch.setattr(tasks.posthog, "flush", lambda **kw: None)
    tasks.track_event(7, "citeguild_search_completed", "signed_up", {"site_host": "private.test"})
    tasks.track_account_deleted_event(7, "signed_up")
    assert [c["properties"]["site_host"] for c in captured] == ["citeguild.com"] * 2
    assert "ignored" not in repr(captured)
