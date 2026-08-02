from django.core.management.base import BaseCommand
from django_q.models import Schedule

from apps.core.crawl_jobs import RECOVERY_TASK, recover_crawl_jobs


class Command(BaseCommand):
    help = "Create the idempotent crawl-recovery schedule and run one startup recovery sweep."

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
        recovery = recover_crawl_jobs()
        action = "created" if created else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Crawl recovery schedule {action} (id={schedule.pk}); startup recovery={recovery}."
            )
        )
