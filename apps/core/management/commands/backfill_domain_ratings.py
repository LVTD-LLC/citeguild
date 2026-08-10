import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.domain_ratings import (
    DOMAIN_RATING_REFRESH_UPDATED,
    DOMAIN_RATING_REQUEST_SPACING_SECONDS,
    DomainRatingError,
    refresh_project_domain_rating,
)
from apps.core.models import Project


def refresh_missing_project(project_id: int) -> bool:
    try:
        # Only a persisted rating counts as success; missing, stale, and failed
        # outcomes remain visible in the command's non-zero summary.
        return refresh_project_domain_rating(project_id) == DOMAIN_RATING_REFRESH_UPDATED
    except DomainRatingError:
        return False


class Command(BaseCommand):
    help = "Fetch Ahrefs Domain Rating for every site that does not have one yet."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many missing ratings in the current run.",
        )

    def handle(self, *args, **options):
        if not settings.AHREFS_API_KEY:
            raise CommandError("AHREFS_API_KEY is required for the Domain Rating backfill.")

        limit = options["limit"]
        if limit is not None and limit < 1:
            raise CommandError("--limit must be a positive integer.")

        project_ids = (
            Project.objects.filter(  # ty: ignore[unresolved-attribute]
                ahrefs_domain_rating_updated_at__isnull=True
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if limit is not None:
            project_ids = project_ids[:limit]
        selected_ids = list(project_ids)

        self.stdout.write(f"Selected {len(selected_ids)} site(s) missing Domain Rating.")
        updated = 0
        failed = 0
        for position, project_id in enumerate(selected_ids, start=1):
            if position > 1:
                time.sleep(DOMAIN_RATING_REQUEST_SPACING_SECONDS)
            if refresh_missing_project(project_id):
                updated += 1
            else:
                failed += 1

            if position % 25 == 0 or position == len(selected_ids):
                self.stdout.write(
                    f"Progress: processed={position}, updated={updated}, failed={failed}."
                )

        summary = (
            "Domain Rating backfill complete: "
            f"selected={len(selected_ids)}, updated={updated}, failed={failed}."
        )
        if failed:
            raise CommandError(f"{summary} Rerun the command to retry missing ratings.")
        self.stdout.write(self.style.SUCCESS(summary))
