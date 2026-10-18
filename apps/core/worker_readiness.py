"""Release matching without exposing worker identities or executing probe tasks."""

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django_q.conf import Conf
from django_q.status import Stat

WORKER_READINESS_KEY = "citeguild:worker-readiness"


def worker_ready() -> bool:
    try:
        registration = cache.get(WORKER_READINESS_KEY)
        expected = {
            "release": settings.CITEGUILD_RELEASE,
            "deployment": settings.CITEGUILD_DEPLOYMENT_ID,
            "configuration_fingerprint": settings.CITEGUILD_CONFIG_FINGERPRINT,
        }
        if not isinstance(registration, dict):
            return False
        if any(registration.get(key) != value for key, value in expected.items()):
            return False
        status = Stat.get(pid=registration["pid"], cluster_id=registration["cluster_id"])
        if status is None:
            return False
        age = (timezone.now() - status.timestamp).total_seconds()
        return bool(
            registration["cluster_id"]
            and status.status in (Conf.IDLE, Conf.WORKING)
            and 0 <= age <= 10
            and len(status.workers) >= Conf.WORKERS
            and status.monitor
            and status.pusher
        )
    except Exception:
        # Missing/stale status or broker failure must never mark a release ready.
        # Do not expose cache/broker errors, host names, process IDs or task data.
        return False
