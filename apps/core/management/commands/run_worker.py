from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django_q.cluster import Cluster

from apps.core.worker_readiness import WORKER_READINESS_KEY


class Command(BaseCommand):
    help = "Start the default Django Q2 cluster and register its deployment identity."

    def handle(self, *args, **options):
        cluster = Cluster()
        cluster.start()
        try:
            cache.set(
                WORKER_READINESS_KEY,
                {
                    "release": settings.CITEGUILD_RELEASE,
                    "deployment": settings.CITEGUILD_DEPLOYMENT_ID,
                    "configuration_fingerprint": settings.CITEGUILD_CONFIG_FINGERPRINT,
                    "pid": cluster.pid,
                    "cluster_id": str(cluster.cluster_id),
                },
                timeout=None,
            )
        except Exception:
            cluster.stop()
            raise CommandError("Worker readiness registration failed.") from None
