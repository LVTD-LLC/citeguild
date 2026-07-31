from django.test import override_settings

from apps.core import ai_observability


@override_settings(POSTHOG_AI_OBSERVABILITY_ENABLED=False, POSTHOG_API_KEY="phc_test")
def test_ai_observability_is_opt_in(monkeypatch):
    processor_calls = []
    monkeypatch.setattr(
        ai_observability,
        "PostHogSpanProcessor",
        lambda **kwargs: processor_calls.append(kwargs),
    )

    assert ai_observability.configure_ai_observability() is None
    assert processor_calls == []


@override_settings(
    POSTHOG_AI_OBSERVABILITY_ENABLED=True,
    POSTHOG_API_KEY="phc_test",
    POSTHOG_HOST="https://us.i.posthog.com",
    POSTHOG_SERVICE_NAME="test-service",
    POSTHOG_SERVICE_VERSION="test-version",
    ENVIRONMENT="test",
)
def test_ai_observability_excludes_model_content(monkeypatch):
    instrumentations = []

    class FakeProvider:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def add_span_processor(self, processor):
            self.processor = processor

        def get_tracer(self, *args):
            return object()

        def shutdown(self):
            return None

    monkeypatch.setattr(ai_observability, "TracerProvider", FakeProvider)
    monkeypatch.setattr(ai_observability, "PostHogSpanProcessor", lambda **kwargs: object())
    monkeypatch.setattr(
        ai_observability.Agent,
        "instrument_all",
        lambda instrumentation: instrumentations.append(instrumentation),
    )
    monkeypatch.setattr(
        ai_observability.Embedder,
        "instrument_all",
        lambda instrumentation: instrumentations.append(instrumentation),
    )

    ai_observability.configure_ai_observability()

    assert len(instrumentations) == 2
    assert instrumentations[0] is instrumentations[1]
    assert instrumentations[0].include_content is False
    assert instrumentations[0].include_binary_content is False
