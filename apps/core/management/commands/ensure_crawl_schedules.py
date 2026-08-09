from django.core.management.base import BaseCommand
from django_q.models import Schedule

from apps.core.crawl_jobs import (
    RECONCILIATION_TASK,
    RECOVERY_TASK,
    recover_crawl_jobs,
    schedule_due_sitemap_reconciliations,
)
from apps.core.domain_ratings import DOMAIN_RATING_REFRESH_SWEEP_TASK


class Command(BaseCommand):
    help = "Create idempotent worker schedules and run one startup crawl sweep."

    def handle(self, *args, **options):
        schedule, created = Schedule.objects.update_or_create(
            name="citeguild-crawl-recovery",
            defaults={
                "func": RECOVERY_TASK,
                "schedule_type": Schedule.MINUTES,
                "minutes": 5,
                "repeats": -1,
            },
        )
        reconciliation_schedule, reconciliation_created = Schedule.objects.update_or_create(
            name="citeguild-daily-reconciliation",
            defaults={
                "func": RECONCILIATION_TASK,
                "schedule_type": Schedule.MINUTES,
                "minutes": 15,
                "repeats": -1,
            },
        )
        domain_rating_schedule, domain_rating_created = Schedule.objects.update_or_create(
            name="citeguild-domain-rating-refresh",
            defaults={
                "func": DOMAIN_RATING_REFRESH_SWEEP_TASK,
                "schedule_type": Schedule.DAILY,
                "repeats": -1,
            },
        )
        recovery = recover_crawl_jobs()
        reconciliation = schedule_due_sitemap_reconciliations()
        action = "created" if created else "updated"
        reconciliation_action = "created" if reconciliation_created else "updated"
        domain_rating_action = "created" if domain_rating_created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Crawl recovery schedule {action} (id={schedule.pk}); "
                f"daily reconciliation schedule {reconciliation_action} "
                f"(id={reconciliation_schedule.pk}); startup recovery={recovery}; "
                f"Domain Rating schedule {domain_rating_action} "
                f"(id={domain_rating_schedule.pk}); startup reconciliation={reconciliation}."
            )
        )
