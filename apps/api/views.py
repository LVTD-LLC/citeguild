import logging
from dataclasses import asdict
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Query, Status
from ninja.errors import AuthenticationError, HttpError
from ninja.errors import ValidationError as NinjaValidationError

from apps.api.auth import api_key_auth, session_auth
from apps.api.rate_limits import consume_v1_rate_limit
from apps.api.schemas import (
    APIErrorOut,
    ProjectListOut,
    ProjectListParams,
    ProjectStatusOut,
    ProjectSubmissionErrorOut,
    ProjectSubmissionIn,
    ProjectSubmissionOut,
    SearchRequest,
    SearchResponseOut,
    UserInfoOut,
    UserSettingsOut,
)
from apps.api.services import serialize_user_info
from apps.core.models import Project
from apps.core.projects import ProjectHostConflict, ProjectService
from apps.core.sitemap_submission import SitemapSubmissionError, SitemapSubmissionService
from apps.search.service import SearchError, SearchService

logger = logging.getLogger(__name__)

api = NinjaAPI()


def _request_id(request: HttpRequest) -> str:
    return str(getattr(request, "request_id", ""))


def _error_payload(
    request: HttpRequest,
    *,
    code: str,
    message: str,
    retryable: bool = False,
) -> dict:
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "request_id": _request_id(request),
    }


@api.exception_handler(AuthenticationError)
def authentication_error(request: HttpRequest, _error: AuthenticationError):
    return api.create_response(
        request,
        _error_payload(
            request,
            code="authentication_required",
            message="A valid API credential is required.",
        ),
        status=401,
    )


@api.exception_handler(NinjaValidationError)
def validation_error(request: HttpRequest, _error: NinjaValidationError):
    return api.create_response(
        request,
        _error_payload(
            request,
            code="validation_error",
            message="The request did not match the API contract.",
        ),
        status=422,
    )


def _rate_limit_response(request: HttpRequest) -> HttpResponse | None:
    try:
        result = consume_v1_rate_limit(request.auth.api_key_prefix)
    except Exception as error:
        logger.error(
            "api.rate_limit.completed",
            extra={
                "event.name": "api.rate_limit.completed",
                "profile_id": request.auth.id,
                "operation.status": "failed",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
        )
        return api.create_response(
            request,
            _error_payload(
                request,
                code="rate_limit_unavailable",
                message="The API is temporarily unavailable.",
                retryable=True,
            ),
            status=503,
        )
    if result.allowed:
        return None
    response = api.create_response(
        request,
        _error_payload(
            request,
            code="rate_limited",
            message="The API rate limit has been reached.",
            retryable=True,
        ),
        status=429,
    )
    response["Retry-After"] = str(result.retry_after)
    response["X-RateLimit-Limit"] = str(result.limit)
    response["X-RateLimit-Remaining"] = str(result.remaining)
    return response


def _project_status(project: Project) -> dict:
    return {
        "id": project.uuid,
        "name": project.name,
        "sitemap_url": project.normalized_sitemap_url,
        "normalized_host": project.normalized_host,
        "state": project.state,
        "article_count": project.article_count,
        "active_article_count": project.active_article_count,
        "last_sync_at": project.last_sync_at,
        "current_sync_started_at": project.current_sync_started_at,
        "last_error_code": project.last_error_code,
    }


def _submission_payload(submission) -> dict:
    return {
        "id": submission.project.uuid,
        "name": submission.project.name,
        "sitemap_url": submission.project.normalized_sitemap_url,
        "normalized_host": submission.project.normalized_host,
        "state": submission.project.state,
        "sitemap_kind": submission.sitemap_kind.value,
        "sync_request_id": submission.sync_request.uuid,
        "sync_state": submission.sync_request.state,
    }


V1_COMMON_RESPONSES = {
    401: APIErrorOut,
    422: APIErrorOut,
    429: APIErrorOut,
    500: APIErrorOut,
    503: APIErrorOut,
}


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


@api.get(
    "/v1/account",
    response={200: UserInfoOut, **V1_COMMON_RESPONSES},
    auth=api_key_auth,
    tags=["v1 account"],
    summary="Inspect the authenticated account",
)
def get_v1_account(request: HttpRequest):
    """Return public-safe account state for the credential owner."""
    if limited := _rate_limit_response(request):
        return limited
    return serialize_user_info(request.auth)


@api.get(
    "/v1/projects",
    response={200: ProjectListOut, **V1_COMMON_RESPONSES},
    auth=api_key_auth,
    tags=["v1 projects"],
    summary="List account-owned site status",
)
def list_v1_projects(request: HttpRequest, params: Query[ProjectListParams]):
    """List only the authenticated account's sites with bounded pagination."""
    if limited := _rate_limit_response(request):
        return limited
    projects = ProjectService.for_owner(request.auth)
    return {
        "count": projects.count(),
        "limit": params.limit,
        "offset": params.offset,
        "results": [
            _project_status(project)
            for project in projects[params.offset : params.offset + params.limit]
        ],
    }


@api.post(
    "/v1/projects",
    response={
        201: ProjectSubmissionOut,
        400: APIErrorOut,
        403: APIErrorOut,
        409: APIErrorOut,
        **V1_COMMON_RESPONSES,
    },
    auth=api_key_auth,
    tags=["v1 projects"],
    summary="Add a sitemap-backed site",
)
def create_v1_project(request: HttpRequest, payload: ProjectSubmissionIn):
    """Validate one sitemap and stage one idempotent initial sync."""
    if limited := _rate_limit_response(request):
        return limited
    try:
        submission = SitemapSubmissionService.submit(
            owner=request.auth,
            name=payload.name,
            sitemap_url=payload.sitemap_url,
        )
    except PermissionDenied:
        return Status(
            403,
            _error_payload(
                request,
                code="subscription_required",
                message="An active subscription is required to add a site.",
            ),
        )
    except ProjectHostConflict:
        return Status(
            409,
            _error_payload(
                request,
                code="host_conflict",
                message="This site host already belongs to a CiteGuild project.",
            ),
        )
    except SitemapSubmissionError as error:
        error_data = error.as_dict()
        return Status(
            503 if error.retryable else 422,
            _error_payload(
                request,
                code=error_data["code"],
                message=error_data["message"],
                retryable=error.retryable,
            ),
        )
    except DjangoValidationError:
        return Status(
            400,
            _error_payload(
                request,
                code="invalid_submission",
                message="The site name or sitemap URL is invalid.",
            ),
        )
    return Status(201, _submission_payload(submission))


@api.get(
    "/v1/projects/{project_uuid}",
    response={200: ProjectStatusOut, 404: APIErrorOut, **V1_COMMON_RESPONSES},
    auth=api_key_auth,
    tags=["v1 projects"],
    summary="Inspect one account-owned site",
)
def get_v1_project(request: HttpRequest, project_uuid: UUID):
    """Return site and indexing status without exposing another account."""
    if limited := _rate_limit_response(request):
        return limited
    try:
        project = ProjectService.get_for_owner(request.auth, project_uuid)
    except Project.DoesNotExist:
        return Status(
            404,
            _error_payload(
                request,
                code="project_not_found",
                message="The requested project was not found.",
            ),
        )
    return _project_status(project)


_SEARCH_INPUT_ERRORS = {
    "invalid_query",
    "query_required",
    "query_too_long",
    "invalid_limit",
    "invalid_language",
    "invalid_excluded_domain",
    "too_many_excluded_domains",
}


@api.post(
    "/v1/search",
    response={200: SearchResponseOut, 403: APIErrorOut, **V1_COMMON_RESPONSES},
    auth=api_key_auth,
    tags=["v1 search"],
    summary="Search the active member corpus",
)
def search_v1(request: HttpRequest, payload: SearchRequest):
    """Expose the shared v1 semantic-search service without transport drift."""
    if limited := _rate_limit_response(request):
        return limited
    try:
        result = SearchService().search(
            profile=request.auth,
            query=payload.query,
            limit=payload.limit,
            language=payload.language,
            excluded_domains=payload.excluded_domains,
            transport="api",
        )
    except SearchError as error:
        if error.code == "subscription_required":
            status = 403
            message = "An active subscription is required to search."
        elif error.code in _SEARCH_INPUT_ERRORS:
            status = 422
            message = "The search request is invalid."
        else:
            status = 503
            message = "Search is temporarily unavailable."
        return Status(
            status,
            _error_payload(
                request,
                code=error.code,
                message=message,
                retryable=error.retryable,
            ),
        )
    except Exception as error:
        logger.error(
            "api.search.completed",
            extra={
                "event.name": "api.search.completed",
                "profile_id": request.auth.id,
                "operation.status": "failed",
                "outcome": "failure",
                "error.type": error.__class__.__name__,
            },
        )
        return Status(
            500,
            _error_payload(
                request,
                code="internal_error",
                message="An unexpected error occurred.",
            ),
        )
    return {
        "contract_version": result.contract_version,
        "results": [asdict(item) for item in result.results],
    }


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
    except DjangoValidationError:
        return 400, {
            "code": "invalid_submission",
            "message": "The site name or sitemap URL is invalid.",
            "retryable": False,
        }

    return 201, _submission_payload(submission)


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
