import logging

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.http import HttpRequest
from ninja import NinjaAPI
from ninja.errors import HttpError

from apps.api.auth import api_key_auth, session_auth
from apps.api.schemas import (
    ProjectSubmissionErrorOut,
    ProjectSubmissionIn,
    ProjectSubmissionOut,
    UserInfoOut,
    UserSettingsOut,
)
from apps.api.services import serialize_user_info
from apps.core.projects import ProjectHostConflict
from apps.core.sitemap_submission import SitemapSubmissionError, SitemapSubmissionService

logger = logging.getLogger(__name__)

api = NinjaAPI()


@api.get("/healthcheck", auth=None, include_in_schema=False, tags=["private"])
def healthcheck(request: HttpRequest):
    """
    Comprehensive healthcheck endpoint for monitoring and load balancers.

    Checks database, Redis, and the Qdrant article collection.

    Returns:
    - 200 OK if all services are healthy
    - 503 if any service is down

    NOTE: We intentionally return boolean health fields (instead of "healthy"/"unhealthy"
    strings) to make healthcheck consumption trivial for load balancers and scripts.
    """

    checks = {
        "database": False,
        "redis": False,
    }
    if settings.QDRANT_URL:
        checks["qdrant"] = False

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = True
    except Exception as error:
        logger.error(
            "healthcheck.dependency.completed",
            extra={
                "event.name": "healthcheck.dependency.completed",
                "dependency": "database",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )

    # Check Redis connectivity
    try:
        cache_key = "healthcheck_test"
        cache_value = "ok"
        cache.set(cache_key, cache_value, timeout=10)
        retrieved_value = cache.get(cache_key)

        if retrieved_value == cache_value:
            checks["redis"] = True
        else:
            logger.error(
                "healthcheck.dependency.completed",
                extra={
                    "event.name": "healthcheck.dependency.completed",
                    "dependency": "redis",
                    "outcome": "failure",
                    "error.type": "CacheValueMismatch",
                },
            )
    except Exception as error:
        logger.error(
            "healthcheck.dependency.completed",
            extra={
                "event.name": "healthcheck.dependency.completed",
                "dependency": "redis",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )

    from apps.search.qdrant import article_collection_healthy

    if settings.QDRANT_URL:
        checks["qdrant"] = article_collection_healthy()
    if settings.QDRANT_URL and not checks["qdrant"]:
        logger.error(
            "healthcheck.dependency.completed",
            extra={
                "event.name": "healthcheck.dependency.completed",
                "dependency": "qdrant",
                "outcome": "failure",
                "error.type": "QdrantCollectionUnavailable",
            },
        )

    healthy = all(checks.values())
    payload = {
        "healthy": healthy,
        "checks": checks,
        "configuration_fingerprint": settings.CITEGUILD_CONFIG_FINGERPRINT,
    }

    if healthy:
        return payload

    return 503, payload


@api.get(
    "/user",
    response=UserInfoOut,
    auth=api_key_auth,
    tags=["user"],
)
def get_user_info(request: HttpRequest):
    """Return safe profile and account details for the authenticated API key."""
    return serialize_user_info(request.auth)


@api.post(
    "/projects",
    response={
        201: ProjectSubmissionOut,
        400: ProjectSubmissionErrorOut,
        403: ProjectSubmissionErrorOut,
        409: ProjectSubmissionErrorOut,
        422: ProjectSubmissionErrorOut,
        503: ProjectSubmissionErrorOut,
    },
    auth=api_key_auth,
    tags=["projects"],
)
def create_project(request: HttpRequest, payload: ProjectSubmissionIn):
    """Validate one sitemap and stage one idempotent initial sync."""
    try:
        submission = SitemapSubmissionService.submit(
            owner=request.auth,
            name=payload.name,
            sitemap_url=payload.sitemap_url,
        )
    except PermissionDenied:
        return 403, {
            "code": "subscription_required",
            "message": "An active subscription is required to add a site.",
            "retryable": False,
        }
    except ProjectHostConflict:
        return 409, {
            "code": "host_conflict",
            "message": "This site host already belongs to a CiteGuild project.",
            "retryable": False,
        }
    except SitemapSubmissionError as error:
        return (503 if error.retryable else 422), error.as_dict()
    except ValidationError:
        return 400, {
            "code": "invalid_submission",
            "message": "The site name or sitemap URL is invalid.",
            "retryable": False,
        }

    return 201, {
        "id": submission.project.uuid,
        "name": submission.project.name,
        "sitemap_url": submission.project.normalized_sitemap_url,
        "normalized_host": submission.project.normalized_host,
        "state": submission.project.state,
        "sitemap_kind": submission.sitemap_kind.value,
        "sync_request_id": submission.sync_request.uuid,
        "sync_state": submission.sync_request.state,
    }


@api.get(
    "/user/settings",
    response=UserSettingsOut,
    auth=[session_auth],
    include_in_schema=False,
    tags=["private"],
)
def user_settings(request: HttpRequest):
    profile = request.auth
    try:
        profile_data = {
            "has_pro_subscription": profile.has_active_subscription,
        }

        data = {"profile": profile_data}

        return data
    except Exception as error:
        logger.error(
            "user_settings.fetch.completed",
            extra={
                "event.name": "user_settings.fetch.completed",
                "profile_id": profile.id,
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
            exc_info=True,
        )
        raise HttpError(500, "An unexpected error occurred.") from None
