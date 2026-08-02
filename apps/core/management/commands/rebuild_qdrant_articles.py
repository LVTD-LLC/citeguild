from django.core.management.base import BaseCommand

from apps.search.qdrant import rebuild_article_collection


class Command(BaseCommand):
    help = "Reconcile the Qdrant article collection from authoritative PostgreSQL records."

    def add_arguments(self, parser):
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        result = rebuild_article_collection(batch_size=options["batch_size"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Qdrant rebuild complete: indexed={result.indexed}, removed={result.removed}"
            )
        )
