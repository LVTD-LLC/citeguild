from django.core.management.base import BaseCommand

from apps.search.qdrant import ensure_article_collection


class Command(BaseCommand):
    help = "Create or validate the configured Qdrant article collection."

    def handle(self, *args, **options):
        created = ensure_article_collection()
        outcome = "created" if created else "compatible"
        self.stdout.write(self.style.SUCCESS(f"Qdrant article collection is {outcome}."))
