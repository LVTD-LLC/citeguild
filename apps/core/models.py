from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django_q.tasks import async_task

from apps.core.base_models import BaseModel
from apps.core.choices import EmailType, ProfileStates
from apps.core.model_utils import (
    generate_api_key,
    get_api_key_prefix,
    hash_api_key,
    verify_api_key,
)


class Profile(BaseModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    api_key_prefix = models.CharField(
        max_length=32,
        unique=True,
        null=True,
        blank=True,
        default=None,
    )
    api_key_hash = models.CharField(max_length=128, blank=True, default="")
    stripe_subscription_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The user's Stripe subscription id, if it exists",
    )
    stripe_customer_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="The user's Stripe customer id, if it exists",
    )

    state = models.CharField(
        max_length=255,
        choices=ProfileStates.choices,
        default=ProfileStates.STRANGER,
        help_text="The current state of the user's profile",
    )

    def track_state_change(self, to_state, metadata=None, source_function=None):
        async_task(
            "apps.core.tasks.track_state_change",
            profile_id=self.id,
            from_state=self.current_state,
            to_state=to_state,
            metadata=metadata,
            source_function=source_function,
            group="Track State Change",
        )

    @property
    def current_state(self):
        if not self.state_transitions.all().exists():
            return ProfileStates.STRANGER
        latest_transition = self.state_transitions.latest("created_at")
        return latest_transition.to_state

    @property
    def has_api_key(self):
        return bool(self.api_key_hash and self.api_key_prefix)

    def set_api_key(self, api_key=None):
        api_key = api_key or generate_api_key()
        api_key_prefix = get_api_key_prefix(api_key)
        if not api_key_prefix:
            raise ValueError("API keys must include a public prefix and secret.")

        self.api_key_prefix = api_key_prefix
        self.api_key_hash = hash_api_key(api_key)
        return api_key

    def rotate_api_key(self):
        api_key = self.set_api_key()
        self.save(update_fields=["api_key_prefix", "api_key_hash", "updated_at"])
        return api_key

    def check_api_key(self, api_key):
        api_key_prefix = get_api_key_prefix(api_key)
        if not api_key_prefix or api_key_prefix != self.api_key_prefix or not self.api_key_hash:
            return False

        return verify_api_key(api_key, self.api_key_hash)

    @property
    def has_active_subscription(self):
        return self.state in [
            ProfileStates.SUBSCRIBED,
            ProfileStates.CANCELLED,
        ] or (self.user.is_superuser and settings.ENVIRONMENT == "prod")


class ProfileStateTransition(BaseModel):
    profile = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="state_transitions",
    )
    from_state = models.CharField(max_length=255, choices=ProfileStates.choices)
    to_state = models.CharField(max_length=255, choices=ProfileStates.choices)
    backup_profile_id = models.IntegerField()
    metadata = models.JSONField(null=True, blank=True)


class EmailSent(BaseModel):
    email_address = models.EmailField(help_text="The recipient email address")
    email_type = models.CharField(
        max_length=50, choices=EmailType.choices, help_text="Type of email sent"
    )
    profile = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="emails_sent",
        help_text="Associated user profile, if applicable",
    )

    class Meta:
        verbose_name = "Email Sent"
        verbose_name_plural = "Emails Sent"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email_type} to {self.email_address}"
