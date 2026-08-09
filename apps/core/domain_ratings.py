"""Best-effort Ahrefs Domain Rating enrichment for member sites."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Protocol

import httpx
from django.conf import settings
from django.db.models import F, Q
from django.utils import timezone
from django_q.tasks import async_task

from apps.core.models import Project

logger = logging.getLogger(__name__)

AHREFS_DOMAIN_RATING_URL = "https://api.ahrefs.com/v3/public/domain-rating-free"
DOMAIN_RATING_REFRESH_TASK = "apps.core.domain_ratings.refresh_project_domain_rating"
DOMAIN_RATING_REFRESH_SWEEP_TASK = "apps.core.domain_ratings.refresh_due_project_domain_ratings"
DOMAIN_RATING_REFRESH_INTERVAL = timedelta(days=30)
DOMAIN_RATING_REFRESH_BATCH_SIZE = 50
DOMAIN_RATING_REQUEST_SPACING_SECONDS = 1.0
DOMAIN_RATING_QUANTUM = Decimal("0.1")


class DomainRatingError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class DomainRatingFetcher(Protocol):
    def fetch(self, target: str) -> Decimal: ...


class AhrefsDomainRatingClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ):
        self.api_key = settings.AHREFS_API_KEY if api_key is None else api_key
        self.timeout_seconds = (
            settings.AHREFS_DOMAIN_RATING_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        self.client = client

    def fetch(self, target: str) -> Decimal:
        if not self.api_key:
            raise DomainRatingError("provider_not_configured")

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            if self.client is None:
                response = httpx.get(
                    AHREFS_DOMAIN_RATING_URL,
                    params={"target": target},
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self.client.get(
                    AHREFS_DOMAIN_RATING_URL,
                    params={"target": target},
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
        except (httpx.TimeoutException, httpx.TransportError):
            raise DomainRatingError("provider_unavailable", retryable=True) from None

        self._validate_status(response.status_code)
        return self._parse_rating(response)

    @staticmethod
    def _validate_status(status_code: int) -> None:
        if status_code in {401, 403}:
            raise DomainRatingError("provider_authentication_failed")
        if status_code == 429:
            raise DomainRatingError("provider_rate_limited", retryable=True)
        if status_code >= 500:
            raise DomainRatingError("provider_unavailable", retryable=True)
        if status_code != 200:
            raise DomainRatingError("provider_http_error")

    @staticmethod
    def _parse_rating(response: httpx.Response) -> Decimal:
        try:
            raw_rating = response.json()["domain_rating"]["domain_rating"]
            if isinstance(raw_rating, bool):
                raise TypeError
            rating = Decimal(str(raw_rating))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise DomainRatingError("provider_invalid_response") from None
        if not rating.is_finite() or not Decimal("0") <= rating <= Decimal("100"):
            raise DomainRatingError("provider_invalid_response")
        return rating.quantize(DOMAIN_RATING_QUANTUM, rounding=ROUND_HALF_UP)


def refresh_project_domain_rating(
    project_id: int,
    *,
    fetcher: DomainRatingFetcher | None = None,
) -> str:
    project = (
        Project.objects.filter(  # ty: ignore[unresolved-attribute]
            pk=project_id
        )
        .only("id", "normalized_host")
        .first()
    )
    if project is None:
        return "missing"

    fetcher = fetcher or AhrefsDomainRatingClient()
    try:
        rating = fetcher.fetch(project.normalized_host)
    except DomainRatingError as error:
        logger.warning(
            "Domain Rating refresh did not complete.",
            extra={
                "event.name": "domain_rating.refresh.failed",
                "outcome": "failure",
                "project_id": project.pk,
                "error_code": error.code,
                "retryable": error.retryable,
            },
        )
        if error.retryable:
            raise
        return f"failed:{error.code}"

    updated = Project.objects.filter(  # ty: ignore[unresolved-attribute]
        pk=project.pk,
        normalized_host=project.normalized_host,
    ).update(
        ahrefs_domain_rating=rating,
        ahrefs_domain_rating_updated_at=timezone.now(),
    )
    if not updated:
        return "stale"
    logger.info(
        "Domain Rating refresh completed.",
        extra={
            "event.name": "domain_rating.refresh.completed",
            "outcome": "success",
            "project_id": project.pk,
        },
    )
    return "updated"


def queue_project_domain_rating_refresh(project_id: int) -> str | None:
    if not settings.AHREFS_API_KEY:
        return None
    try:
        return async_task(
            DOMAIN_RATING_REFRESH_TASK,
            project_id,
            group=f"domain-rating:{project_id}",
        )
    except Exception:
        logger.exception(
            "Domain Rating refresh could not be queued.",
            extra={
                "event.name": "domain_rating.refresh.enqueue_failed",
                "outcome": "failure",
                "project_id": project_id,
            },
        )
        return None


def refresh_due_project_domain_ratings(
    *,
    now=None,
    limit: int = DOMAIN_RATING_REFRESH_BATCH_SIZE,
    fetcher: DomainRatingFetcher | None = None,
    sleep=time.sleep,
) -> dict[str, int]:
    if not settings.AHREFS_API_KEY:
        return {"due_projects": 0, "updated_projects": 0, "failed_projects": 0}

    now = now or timezone.now()
    limit = max(1, min(limit, 100))
    due_ids = list(
        Project.objects.filter(  # ty: ignore[unresolved-attribute]
            Q(ahrefs_domain_rating_updated_at__isnull=True)
            | Q(ahrefs_domain_rating_updated_at__lte=(now - DOMAIN_RATING_REFRESH_INTERVAL))
        )
        .order_by(F("ahrefs_domain_rating_updated_at").asc(nulls_first=True), "id")
        .values_list("id", flat=True)[:limit]
    )
    if not due_ids:
        return {"due_projects": 0, "updated_projects": 0, "failed_projects": 0}

    fetcher = fetcher or AhrefsDomainRatingClient()
    updated_projects = 0
    failed_projects = 0
    for position, project_id in enumerate(due_ids):
        if position:
            sleep(DOMAIN_RATING_REQUEST_SPACING_SECONDS)
        try:
            outcome = refresh_project_domain_rating(project_id, fetcher=fetcher)
        except DomainRatingError:
            failed_projects += 1
            continue
        if outcome == "updated":
            updated_projects += 1
        else:
            failed_projects += 1

    logger.info(
        "Domain Rating refresh sweep completed.",
        extra={
            "event.name": "domain_rating.refresh_sweep.completed",
            "outcome": "success",
            "due_projects": len(due_ids),
            "updated_projects": updated_projects,
            "failed_projects": failed_projects,
        },
    )
    return {
        "due_projects": len(due_ids),
        "updated_projects": updated_projects,
        "failed_projects": failed_projects,
    }
