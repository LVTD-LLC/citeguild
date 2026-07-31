import atexit

import posthog
from django.apps import AppConfig
from django.conf import settings


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    label = "core"

    def ready(self):
        import apps.core.signals  # noqa
        import apps.core.task_logging  # noqa

        import apps.core.stripe_webhooks  # noqa

        if settings.POSTHOG_API_KEY:
            posthog.api_key = settings.POSTHOG_API_KEY
            posthog.host = settings.POSTHOG_HOST
            atexit.register(posthog.shutdown)

        if settings.POSTHOG_AI_OBSERVABILITY_ENABLED and settings.POSTHOG_API_KEY:
            from apps.core.ai_observability import configure_ai_observability

            configure_ai_observability()
        if settings.ENVIRONMENT == "dev":
            posthog.debug = True
