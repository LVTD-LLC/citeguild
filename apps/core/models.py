from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django_q.tasks import async_task

from apps.core.base_models import BaseModel
from apps.core.choices import EmailType, ProfileStates, ProjectStates
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
    stripe_subscription_status = models.CharField(max_length=32, blank=True, default="")
    stripe_current_period_end = models.DateTimeField(null=True, blank=True)
    stripe_cancel_at_period_end = models.BooleanField(default=False)
    stripe_last_event_created = models.PositiveBigIntegerField(default=0)
    stripe_last_event_id = models.CharField(max_length=255, blank=True, default="")

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
        return self.stripe_subscription_status in {"active", "past_due"} or (
            self.user.is_superuser and settings.ENVIRONMENT == "prod"
        )


class StripeWebhookEvent(BaseModel):
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=255)
    event_created = models.PositiveBigIntegerField(default=0)
    outcome = models.CharField(max_length=32, default="processed")

    class Meta:
        ordering = ["-created_at"]


class Project(BaseModel):
    """One account-owned site submitted to the CiteGuild corpus."""

    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=120)
    sitemap_url = models.URLField(max_length=2048)
    normalized_sitemap_url = models.URLField(max_length=2048)
    normalized_host = models.CharField(max_length=253, unique=True)
    state = models.CharField(
        max_length=20, choices=ProjectStates.choices, default=ProjectStates.ACTIVE
    )
    suspension_reason = models.CharField(max_length=255, blank=True, default="")
    suspended_at = models.DateTimeField(null=True, blank=True)
    last_sync_uuid = models.UUIDField(null=True, blank=True)
    current_sync_uuid = models.UUIDField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    current_sync_started_at = models.DateTimeField(null=True, blank=True)
    article_count = models.PositiveIntegerField(default=0)
    active_article_count = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["name", "id"]
        indexes = [
            models.Index(fields=["owner", "state"], name="core_proj_owner_state_idx"),
            models.Index(fields=["state", "last_sync_at"], name="core_proj_sync_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_project_uuid_unique"),
        ]

    @property
    def is_sync_eligible(self):
        if self.state != ProjectStates.ACTIVE:
            return False
        owner = Profile.objects.select_related("user").get(pk=self.owner_id)
        return owner.has_active_subscription


class ProjectStateTransition(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="state_transitions")
    actor = models.ForeignKey(
        Profile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="project_state_changes",
    )
    from_state = models.CharField(max_length=20, choices=ProjectStates.choices)
    to_state = models.CharField(max_length=20, choices=ProjectStates.choices)
    reason = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)


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
