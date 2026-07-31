import logging

import requests
from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


class AppriseNotificationError(Exception):
    pass


def is_apprise_configured():
    return bool(settings.APPRISE_API_URL and settings.APPRISE_CONFIG_KEY)


def send_admin_notification(subject, message, *, notification_type="info"):
    """Send an internal admin notification via Apprise, falling back to email."""
    if is_apprise_configured():
        try:
            return send_apprise_notification(subject, message, notification_type=notification_type)
        except AppriseNotificationError as exc:
            logger.error(
                "admin_notification.delivery.completed",
                extra={
                    "event.name": "admin_notification.delivery.completed",
                    "provider": "apprise",
                    "notification_type": notification_type,
                    "outcome": "failure",
                    "error.type": exc.__class__.__name__,
                },
            )
            if not settings.ADMIN_NOTIFICATION_EMAIL_FALLBACK:
                raise
    elif not settings.ADMIN_NOTIFICATION_EMAIL_FALLBACK:
        raise AppriseNotificationError("Apprise is not configured")

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        settings.ADMIN_NOTIFICATION_EMAIL_RECIPIENTS,
        fail_silently=False,
    )
    return "email"


def send_apprise_notification(subject, message, *, notification_type="info"):
    url = f"{settings.APPRISE_API_URL.rstrip('/')}/notify/{settings.APPRISE_CONFIG_KEY}"
    payload = {
        "title": subject,
        "body": message.strip(),
        "type": notification_type,
        "format": settings.APPRISE_NOTIFICATION_FORMAT,
    }
    auth = None
    if settings.APPRISE_BASIC_AUTH_USER and settings.APPRISE_BASIC_AUTH_PASSWORD:
        auth = (settings.APPRISE_BASIC_AUTH_USER, settings.APPRISE_BASIC_AUTH_PASSWORD)

    try:
        response = requests.post(
            url,
            json=payload,
            auth=auth,
            timeout=settings.APPRISE_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AppriseNotificationError(str(exc)) from exc

    return "apprise"
