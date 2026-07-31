import hashlib
import hmac
import logging
import re

from allauth.mfa import app_settings as mfa_app_settings
from allauth.socialaccount.models import SocialApp
from django.conf import settings

from apps.core.choices import ProfileStates

logger = logging.getLogger(__name__)

POSTHOG_PAGEVIEW_GROUPS = {
    "account_confirm_email": "auth",
    "account_email_verification_sent": "auth",
    "account_login": "auth",
    "account_reset_password": "auth",
    "account_reset_password_done": "auth",
    "account_reset_password_from_key": "auth",
    "account_reset_password_from_key_done": "auth",
    "account_signup": "auth",
    "account_signup_by_passkey": "auth",
    "blog_post": "blog",
    "blog_posts": "blog",
    "docs_home": "docs",
    "docs_page": "docs",
    "landing": "marketing",
    "pricing": "marketing",
    "privacy_policy": "marketing",
    "socialaccount_login": "auth",
    "terms_of_service": "marketing",
}
POSTHOG_ROUTE_PARAMETER_PATTERN = re.compile(r"<(?:[^:>]+:)?([^>]+)>")


def current_state(request):
    if request.user.is_authenticated:
        return {"current_state": request.user.profile.current_state}
    return {"current_state": ProfileStates.STRANGER}


def mfa_recovery_codes_settings(request):
    return {"mfa_recovery_codes_show_once": mfa_app_settings.RECOVERY_CODES_SHOW_ONCE}


def public_site_url(request):
    return {"public_site_url": settings.SITE_URL.rstrip("/")}


def pro_subscription_status(request):
    """
    Adds a 'has_pro_subscription' variable to the context.
    This variable is True if the user has an active pro subscription, False otherwise.
    """
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        return {"has_pro_subscription": request.user.profile.has_active_subscription}
    return {"has_pro_subscription": False}


def posthog_api_key(request):
    resolver_match = getattr(request, "resolver_match", None)
    content_group = POSTHOG_PAGEVIEW_GROUPS.get(
        getattr(resolver_match, "url_name", None),
        "",
    )
    route = getattr(resolver_match, "route", "") if content_group else ""
    normalized_route = (
        f"/{POSTHOG_ROUTE_PARAMETER_PATTERN.sub(r':\1', route).lstrip('/')}"
        if content_group
        else ""
    )
    context = {
        "posthog_api_key": settings.POSTHOG_API_KEY,
        "posthog_browser_host": settings.POSTHOG_BROWSER_HOST,
        "posthog_content_group": content_group,
        "posthog_distinct_id": "",
        "posthog_environment": settings.ENVIRONMENT,
        "posthog_event_prefix": "citeguild",
        "posthog_pageview_enabled": bool(settings.POSTHOG_API_KEY and normalized_route),
        "posthog_pageview_route": normalized_route,
    }
    if request.user.is_authenticated and hasattr(request.user, "profile"):
        context["posthog_distinct_id"] = str(request.user.profile.id)
    return context


def mjml_url(request):
    return {"mjml_url": settings.MJML_URL}


def _chatwoot_identifier_hash(identifier):
    if not settings.CHATWOOT_HMAC_SECRET:
        return ""

    return hmac.new(
        settings.CHATWOOT_HMAC_SECRET.encode("utf-8"),
        str(identifier).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def chatwoot_config(request):
    base_url = settings.CHATWOOT_BASE_URL.rstrip("/")
    website_token = settings.CHATWOOT_WEBSITE_TOKEN
    if not base_url or not website_token:
        return {"chatwoot": {"enabled": False}}

    config = {
        "enabled": True,
        "base_url": base_url,
        "website_token": website_token,
        "user": None,
    }

    user = request.user
    if user.is_authenticated:
        identifier = str(user.pk)
        user_config = {
            "identifier": identifier,
            "email": user.email,
            "name": user.get_full_name() or user.email,
        }

        identifier_hash = _chatwoot_identifier_hash(identifier)
        if identifier_hash:
            user_config["identifier_hash"] = identifier_hash

        config["user"] = user_config

    return {"chatwoot": config}


def available_social_providers(request):
    """
    Checks which social authentication providers are available.
    Returns a list of provider names from either SOCIALACCOUNT_PROVIDERS settings
    or SocialApp database entries, as django-allauth supports both configuration methods.
    """
    available_providers = set()

    configured_providers = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {})

    available_providers.update(configured_providers.keys())

    try:
        social_apps = SocialApp.objects.all()
        for social_app in social_apps:
            available_providers.add(social_app.provider)
    except Exception as error:
        logger.warning(
            "social_provider.discovery.completed",
            extra={
                "event.name": "social_provider.discovery.completed",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )

    available_providers_list = sorted(list(available_providers))

    return {
        "available_social_providers": available_providers_list,
        "has_social_providers": len(available_providers_list) > 0,
    }
