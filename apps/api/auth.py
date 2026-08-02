import logging

from django.http import HttpRequest
from ninja.security import APIKeyHeader, HttpBearer

from apps.core.model_utils import get_api_key_prefix
from apps.core.models import Profile
from citeguild.logging_utils import bind_log_context

logger = logging.getLogger(__name__)


def get_profile_for_api_key(key: str) -> Profile | None:
    api_key_prefix = get_api_key_prefix(key)
    if not api_key_prefix:
        logger.warning(
            "api.authentication.completed",
            extra={
                "event.name": "api.authentication.completed",
                "auth.method": "api_key",
                "auth.reason": "invalid_format",
                "outcome": "failure",
            },
        )
        return None

    try:
        profile = Profile.objects.select_related("user").get(api_key_prefix=api_key_prefix)
    except Profile.DoesNotExist:
        logger.warning(
            "api.authentication.completed",
            extra={
                "event.name": "api.authentication.completed",
                "auth.method": "api_key",
                "auth.reason": "invalid_credentials",
                "outcome": "failure",
            },
        )
        return None

    if not profile.check_api_key(key):
        logger.warning(
            "api.authentication.completed",
            extra={
                "event.name": "api.authentication.completed",
                "auth.method": "api_key",
                "auth.reason": "invalid_credentials",
                "outcome": "failure",
            },
        )
        return None

    bind_log_context(
        **{
            "profile_id": profile.id,
            "api_key_id": api_key_prefix,
            "auth.method": "api_key",
        }
    )
    return profile


class APIKeyHeaderAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request: HttpRequest, key: str) -> Profile | None:
        return get_profile_for_api_key(key)


class BearerAPIKeyAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Profile | None:
        return get_profile_for_api_key(token)


class SessionAuth:
    """Authentication via Django session"""

    def authenticate(self, request: HttpRequest) -> Profile | None:
        if hasattr(request, "user") and request.user.is_authenticated:
            try:
                profile = request.user.profile
            except Profile.DoesNotExist:
                logger.warning(
                    "api.authentication.completed",
                    extra={
                        "event.name": "api.authentication.completed",
                        "auth.method": "session",
                        "auth.reason": "profile_missing",
                        "user_id": request.user.id,
                        "outcome": "failure",
                    },
                )
                return None
            bind_log_context(
                **{
                    "user_id": request.user.id,
                    "profile_id": profile.id,
                    "auth.method": "session",
                }
            )
            return profile
        return None

    def __call__(self, request: HttpRequest):
        return self.authenticate(request)


def _require_superuser(profile: Profile | None) -> Profile | None:
    if profile and profile.user.is_superuser:
        return profile

    if profile:
        logger.warning(
            "api.authorization.completed",
            extra={
                "event.name": "api.authorization.completed",
                "auth.reason": "superuser_required",
                "profile_id": profile.id,
                "outcome": "failure",
            },
        )
    return None


class SuperuserAPIKeyHeaderAuth(APIKeyHeader):
    param_name = "X-API-Key"

    def authenticate(self, request: HttpRequest, key: str) -> Profile | None:
        return _require_superuser(get_profile_for_api_key(key))


class SuperuserBearerAPIKeyAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str) -> Profile | None:
        return _require_superuser(get_profile_for_api_key(token))


api_key_auth = [APIKeyHeaderAuth(), BearerAPIKeyAuth()]
session_auth = SessionAuth()
superuser_api_auth = [SuperuserAPIKeyHeaderAuth(), SuperuserBearerAPIKeyAuth()]
