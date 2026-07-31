from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.core.notifications import (
    AppriseNotificationError,
    send_admin_notification,
    send_apprise_notification,
)


@override_settings(
    APPRISE_API_URL="https://apprise.example.com",
    APPRISE_CONFIG_KEY="project-alerts",
    APPRISE_BASIC_AUTH_USER="apprise",
    APPRISE_BASIC_AUTH_PASSWORD="secret",
    APPRISE_NOTIFICATION_FORMAT="markdown",
    APPRISE_REQUEST_TIMEOUT=10,
)
def test_send_apprise_notification_posts_to_saved_config_key():
    response = Mock()
    response.raise_for_status.return_value = None

    with patch("apps.core.notifications.requests.post", return_value=response) as post:
        result = send_apprise_notification(
            "New signup",
            "A user signed up",
            notification_type="success",
        )

    assert result == "apprise"
    post.assert_called_once_with(
        "https://apprise.example.com/notify/project-alerts",
        json={
            "title": "New signup",
            "body": "A user signed up",
            "type": "success",
            "format": "markdown",
        },
        auth=("apprise", "secret"),
        timeout=10,
    )


@override_settings(
    APPRISE_API_URL="https://apprise.example.com",
    APPRISE_CONFIG_KEY="project-alerts",
    APPRISE_BASIC_AUTH_USER="",
    APPRISE_BASIC_AUTH_PASSWORD="",
    APPRISE_NOTIFICATION_FORMAT="text",
    APPRISE_REQUEST_TIMEOUT=5,
)
def test_send_apprise_notification_omits_auth_when_basic_auth_is_unset():
    response = Mock()
    response.raise_for_status.return_value = None

    with patch("apps.core.notifications.requests.post", return_value=response) as post:
        result = send_apprise_notification("Subject", "Body")

    assert result == "apprise"
    assert post.call_args.kwargs["auth"] is None
    assert post.call_args.kwargs["timeout"] == 5


@override_settings(
    APPRISE_API_URL="",
    APPRISE_CONFIG_KEY="",
    ADMIN_NOTIFICATION_EMAIL_RECIPIENTS=["Ops <ops@example.com>"],
    DEFAULT_FROM_EMAIL="App <hello@example.com>",
)
def test_send_admin_notification_falls_back_to_email_when_apprise_is_unconfigured():
    with patch("apps.core.notifications.send_mail", return_value=1) as send_mail:
        result = send_admin_notification("Subject", "Body")

    assert result == "email"
    send_mail.assert_called_once_with(
        "Subject",
        "Body",
        "App <hello@example.com>",
        ["Ops <ops@example.com>"],
        fail_silently=False,
    )


@override_settings(
    APPRISE_API_URL="https://apprise.example.com",
    APPRISE_CONFIG_KEY="project-alerts",
    ADMIN_NOTIFICATION_EMAIL_FALLBACK=True,
    ADMIN_NOTIFICATION_EMAIL_RECIPIENTS=["Ops <ops@example.com>"],
    DEFAULT_FROM_EMAIL="App <hello@example.com>",
)
def test_send_admin_notification_falls_back_to_email_when_apprise_fails():
    with (
        patch(
            "apps.core.notifications.send_apprise_notification",
            side_effect=AppriseNotificationError("timeout"),
        ),
        patch("apps.core.notifications.send_mail", return_value=1) as send_mail,
    ):
        result = send_admin_notification("Subject", "Body")

    assert result == "email"
    send_mail.assert_called_once()


@override_settings(
    APPRISE_API_URL="https://apprise.example.com",
    APPRISE_CONFIG_KEY="project-alerts",
    ADMIN_NOTIFICATION_EMAIL_FALLBACK=False,
)
def test_send_admin_notification_can_disable_email_fallback():
    with patch(
        "apps.core.notifications.send_apprise_notification",
        side_effect=AppriseNotificationError("timeout"),
    ):
        with pytest.raises(AppriseNotificationError):
            send_admin_notification("Subject", "Body")


@override_settings(
    APPRISE_API_URL="",
    APPRISE_CONFIG_KEY="",
    ADMIN_NOTIFICATION_EMAIL_FALLBACK=False,
)
def test_send_admin_notification_can_disable_email_fallback_when_apprise_is_unconfigured():
    with pytest.raises(AppriseNotificationError, match="Apprise is not configured"):
        send_admin_notification("Subject", "Body")
