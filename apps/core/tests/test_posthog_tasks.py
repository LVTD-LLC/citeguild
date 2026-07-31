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
                    "environment": "dev",
                    "profile_id": 7,
                    "current_state": "signed_up",
                    "dataset_id": 3,
                },
            },
        )
    ]
