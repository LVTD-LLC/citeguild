"""Recover project vector cleanup after broker outages or lost worker tasks."""

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core.models import ProjectDeletionCleanup
from apps.search.qdrant import delete_project_points

logger = logging.getLogger(__name__)
PROJECT_CLEANUP_TASK = "apps.search.cleanup.recover_project_deletions"


def recover_project_deletions() -> int:
    if not settings.CITEGUILD_INDEXING_ENABLED:
        return 0
    pending = list(
        ProjectDeletionCleanup.objects.filter(next_attempt_at__lte=timezone.now())
        .order_by("next_attempt_at", "project_uuid")
        .values_list("project_uuid", flat=True)[:100]
    )
    completed = 0
    for project_uuid in pending:
        # Advancing before I/O bounds retries even if a worker is killed. Deleting
        # the same stable UUID twice is safe when a queued task overlaps a sweep.
        ProjectDeletionCleanup.objects.filter(project_uuid=project_uuid).update(
            next_attempt_at=timezone.now() + timedelta(minutes=5)
        )
        try:
            delete_project_points(str(project_uuid))
        except Exception as error:
            logger.warning(
                "search.project_cleanup.failed",
                extra={
                    "event.name": "search.project_cleanup.failed",
                    "outcome": "failure",
                    "exception_type": type(error).__name__,
                },
            )
        else:
            completed += 1
    return completed
