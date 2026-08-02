from django.core.management.base import BaseCommand
from django_q.models import Schedule

from apps.core.crawl_jobs import (
    RECONCILIATION_TASK,
    RECOVERY_TASK,
    recover_crawl_jobs,
    schedule_due_sitemap_reconciliations,
)


class Command(BaseCommand):
    help = "Create idempotent crawl schedules and run one startup scheduling sweep."

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
        recovery = recover_crawl_jobs()
        reconciliation = schedule_due_sitemap_reconciliations()
        action = "created" if created else "updated"
        reconciliation_action = "created" if reconciliation_created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Crawl recovery schedule {action} (id={schedule.pk}); "
                f"daily reconciliation schedule {reconciliation_action} "
                f"(id={reconciliation_schedule.pk}); startup recovery={recovery}; "
                f"startup reconciliation={reconciliation}."
            )
        )
