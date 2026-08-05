from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings

from apps.core.context_processors import sentry_browser_config


@override_settings(SENTRY_ACTIVE=False, SENTRY_BROWSER_ENABLED=False, SENTRY_DSN="")
def test_sentry_browser_context_is_disabled_without_active_sentry():
    request = RequestFactory().get("/")

    assert sentry_browser_config(request) == {"sentry_browser": {"enabled": False}}


@override_settings(
    SENTRY_ACTIVE=True,
    SENTRY_BROWSER_ENABLED=True,
    SENTRY_DSN="https://public@example.ingest.sentry.io/123",
    SENTRY_RELEASE="abc123",
    SENTRY_BROWSER_TRACES_SAMPLE_RATE=0.75,
    ENVIRONMENT="prod",
)
def test_sentry_browser_context_exposes_public_config_without_user_data():
    request = RequestFactory().get("/dashboard/?token=private")

    context = sentry_browser_config(request)

    assert context == {
        "sentry_browser": {
            "enabled": True,
            "dsn": "https://public@example.ingest.sentry.io/123",
            "environment": "prod",
            "release": "abc123",
            "traces_sample_rate": 0.75,
        }
    }
    assert "private" not in repr(context)


def test_sentry_browser_component_loads_bundle_only_when_enabled():
    enabled_html = render_to_string(
        "components/sentry.html",
        {
            "sentry_browser": {
                "enabled": True,
                "dsn": "https://public@example.ingest.sentry.io/123",
            }
        },
    )
    disabled_html = render_to_string(
        "components/sentry.html",
        {"sentry_browser": {"enabled": False}},
    )

    assert 'id="sentry-browser-config"' in enabled_html
    assert 'src="/static/js/sentry.js"' in enabled_html
    assert disabled_html.strip() == ""
