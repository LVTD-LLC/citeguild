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
