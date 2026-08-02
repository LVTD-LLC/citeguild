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
