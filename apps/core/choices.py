from django.db import models


class ProfileStates(models.TextChoices):
    STRANGER = "stranger"
    SIGNED_UP = "signed_up"
    # Freemium state set after the core activation action is completed.
    FREE = "free"

    # Trial state for apps with time-limited paid-plan access.
    TRIAL_STARTED = "trial_started"
    TRIAL_ENDED = "trial_ended"
    SUBSCRIBED = "subscribed"
    # Subscription cancelled, but access remains until the paid period ends.
    CANCELLED = "cancelled"
    CHURNED = "churned"  # when user lost access to paid features

    ACCOUNT_DELETED = "account_deleted"


class EmailType(models.TextChoices):
    EMAIL_CONFIRMATION = "EMAIL_CONFIRMATION", "Email Confirmation"
    WELCOME = "WELCOME", "Welcome"


class ProjectStates(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class ProjectSyncKinds(models.TextChoices):
    INITIAL = "initial", "Initial"
    DAILY = "daily", "Daily"
    MANUAL = "manual", "Manual"
    REPAIR = "repair", "Repair"


class ProjectSyncStates(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class PageCrawlStates(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class ExtractionStates(models.TextChoices):
    READY = "ready", "Ready"
    EMPTY = "empty", "Empty"
    NOINDEX = "noindex", "Noindex"
