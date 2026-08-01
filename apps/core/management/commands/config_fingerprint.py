from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print the secret-safe CiteGuild runtime configuration fingerprint."

    def handle(self, *args, **options):
        self.stdout.write(
            f"CiteGuild configuration fingerprint: {settings.CITEGUILD_CONFIG_FINGERPRINT}"
        )
