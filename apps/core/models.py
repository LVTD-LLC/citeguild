import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django_q.tasks import async_task

from apps.core.base_models import BaseModel
from apps.core.choices import (
    ArticleEmbeddingStates,
    ArticleStates,
    CrawlAttemptStates,
    EmailType,
    ExtractionStates,
    PageCrawlStates,
    ProfileStates,
    ProjectStates,
    ProjectSyncKinds,
    ProjectSyncStates,
)
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
    active_sitemap_inventory = models.ForeignKey(
        "SitemapInventory",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_for_projects",
    )

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


class ProjectSyncRequest(BaseModel):
    """Durable queue boundary consumed by the crawler worker pipeline."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="sync_requests")
    kind = models.CharField(
        max_length=20,
        choices=ProjectSyncKinds.choices,
        default=ProjectSyncKinds.INITIAL,
    )
    state = models.CharField(
        max_length=20,
        choices=ProjectSyncStates.choices,
        default=ProjectSyncStates.QUEUED,
    )
    sitemap_kind = models.CharField(max_length=20)
    idempotency_key = models.CharField(
        max_length=160,
        unique=True,
        default=uuid.uuid4,
    )
    attempt_count = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    error_code = models.CharField(max_length=64, blank=True, default="")
    broker_task_id = models.CharField(max_length=64, blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_count = models.PositiveIntegerField(default=0)
    queued_count = models.PositiveIntegerField(default=0)
    succeeded_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=models.Q(state__in=["queued", "running"]),
                name="core_project_one_active_sync",
            ),
            models.UniqueConstraint(fields=["uuid"], name="core_project_sync_uuid_unique"),
        ]
        indexes = [models.Index(fields=["state", "created_at"], name="core_sync_state_created_idx")]


class PageCrawlWork(BaseModel):
    sync_request = models.ForeignKey(
        ProjectSyncRequest,
        on_delete=models.CASCADE,
        related_name="page_work",
    )
    candidate = models.ForeignKey(
        "SitemapCandidate",
        on_delete=models.CASCADE,
        related_name="crawl_work",
    )
    state = models.CharField(
        max_length=20,
        choices=PageCrawlStates.choices,
        default=PageCrawlStates.QUEUED,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    error_code = models.CharField(max_length=64, blank=True, default="")
    broker_task_id = models.CharField(max_length=64, blank=True, default="")
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["sync_request", "candidate"],
                name="core_page_work_unique",
            ),
            models.UniqueConstraint(fields=["uuid"], name="core_page_work_uuid_unique"),
        ]
        indexes = [
            models.Index(fields=["state", "next_attempt_at"], name="core_page_work_retry_idx"),
            models.Index(fields=["sync_request", "state"], name="core_page_work_sync_state_idx"),
        ]


class PageExtractionResult(BaseModel):
    work = models.OneToOneField(
        PageCrawlWork,
        on_delete=models.CASCADE,
        related_name="extraction",
    )
    state = models.CharField(max_length=20, choices=ExtractionStates.choices)
    final_url = models.URLField(max_length=2048)
    canonical_url = models.URLField(max_length=2048)
    http_status = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=300, blank=True, default="")
    description = models.CharField(max_length=1000, blank=True, default="")
    language = models.CharField(max_length=35, blank=True, default="")
    text = models.TextField(blank=True, default="")
    noindex = models.BooleanField(default=False)
    source_bytes = models.PositiveIntegerField(default=0)
    text_chars = models.PositiveIntegerField(default=0)
    outbound_links = models.JSONField(default=list, blank=True)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_page_extraction_uuid_unique")
        ]


class Article(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="articles")
    original_url = models.URLField(max_length=2048)
    final_url = models.URLField(max_length=2048)
    canonical_url = models.URLField(max_length=2048)
    normalized_canonical_url = models.URLField(max_length=2048)
    title = models.CharField(max_length=300, blank=True, default="")
    description = models.CharField(max_length=1000, blank=True, default="")
    language = models.CharField(max_length=35, blank=True, default="")
    content = models.TextField(blank=True, default="")
    content_hash = models.CharField(max_length=64, blank=True, default="")
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    extraction_state = models.CharField(max_length=20, choices=ExtractionStates.choices)
    state = models.CharField(
        max_length=20,
        choices=ArticleStates.choices,
        default=ArticleStates.DISCOVERED,
    )
    is_active = models.BooleanField(default=False)
    inactivity_reason = models.CharField(max_length=64, blank=True, default="")
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    last_fetched_at = models.DateTimeField()
    last_changed_at = models.DateTimeField()
    inactive_at = models.DateTimeField(null=True, blank=True)
    qdrant_point_id = models.UUIDField(unique=True, editable=False)

    class Meta:
        ordering = ["normalized_canonical_url", "id"]
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_article_uuid_unique"),
            models.UniqueConstraint(
                fields=["project", "normalized_canonical_url"],
                name="core_article_project_canonical_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "state"], name="core_article_project_state_idx"),
            models.Index(
                fields=["normalized_canonical_url"],
                name="core_article_canonical_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.qdrant_point_id is None:
            self.qdrant_point_id = self.uuid
        return super().save(*args, **kwargs)


class ArticleSourceURL(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="article_sources")
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="source_urls")
    normalized_url = models.URLField(max_length=2048)
    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    consecutive_missing_syncs = models.PositiveSmallIntegerField(default=0)
    inactive_at = models.DateTimeField(null=True, blank=True)
    last_seen_sync = models.ForeignKey(
        ProjectSyncRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seen_article_sources",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_article_source_uuid_unique"),
            models.UniqueConstraint(
                fields=["project", "normalized_url"],
                name="core_article_source_project_url_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "is_active"], name="core_article_source_active_idx")
        ]


class ArticleEmbedding(BaseModel):
    article = models.OneToOneField(
        Article,
        on_delete=models.CASCADE,
        related_name="embedding",
    )
    state = models.CharField(max_length=20, choices=ArticleEmbeddingStates.choices)
    vector = models.JSONField(default=list, blank=True)
    content_hash = models.CharField(max_length=64)
    model = models.CharField(max_length=255)
    dimensions = models.PositiveIntegerField()
    input_chars = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=64, blank=True, default="")
    embedded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_article_embedding_uuid_unique"),
        ]


class ArticleCrawlAttempt(BaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="crawl_attempts")
    sync_request = models.ForeignKey(
        ProjectSyncRequest,
        on_delete=models.CASCADE,
        related_name="article_attempts",
    )
    work = models.ForeignKey(
        PageCrawlWork,
        on_delete=models.CASCADE,
        related_name="article_attempts",
    )
    article = models.ForeignKey(
        Article,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="crawl_attempts",
    )
    attempt_number = models.PositiveSmallIntegerField()
    state = models.CharField(max_length=20, choices=CrawlAttemptStates.choices)
    requested_url = models.URLField(max_length=2048)
    final_url = models.URLField(max_length=2048, blank=True, default="")
    canonical_url = models.URLField(max_length=2048, blank=True, default="")
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    extraction_state = models.CharField(max_length=20, blank=True, default="")
    source_bytes = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(max_length=64, blank=True, default="")
    error_code = models.CharField(max_length=64, blank=True, default="")
    fetched_at = models.DateTimeField()

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_article_attempt_uuid_unique"),
            models.UniqueConstraint(
                fields=["work", "attempt_number"],
                name="core_article_attempt_work_number_unique",
            ),
            models.UniqueConstraint(
                fields=["work"],
                condition=models.Q(state=CrawlAttemptStates.SUCCEEDED),
                name="core_article_attempt_one_success",
            ),
        ]
        indexes = [
            models.Index(fields=["project", "fetched_at"], name="core_art_attempt_project_idx")
        ]


class OutboundLinkObservation(BaseModel):
    source_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="outbound_links",
    )
    target_article = models.ForeignKey(
        Article,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inbound_links",
    )
    normalized_destination_url = models.URLField(max_length=2048)
    anchor_text = models.CharField(max_length=300, blank=True, default="")
    is_active = models.BooleanField(default=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    inactive_at = models.DateTimeField(null=True, blank=True)
    last_seen_sync = models.ForeignKey(
        ProjectSyncRequest,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observed_outbound_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_outbound_link_uuid_unique"),
            models.UniqueConstraint(
                fields=["source_article", "normalized_destination_url"],
                name="core_outbound_link_source_url_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["target_article", "is_active"], name="core_outbound_target_idx")
        ]


class SitemapInventory(BaseModel):
    """Immutable candidate set promoted only after a complete successful parse."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="inventories")
    sync_request = models.OneToOneField(
        ProjectSyncRequest,
        on_delete=models.CASCADE,
        related_name="sitemap_inventory",
    )
    candidate_count = models.PositiveIntegerField(default=0)
    sitemap_count = models.PositiveIntegerField(default=0)
    diagnostics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["uuid"], name="core_sitemap_inventory_uuid_unique")
        ]


class SitemapCandidate(BaseModel):
    inventory = models.ForeignKey(
        SitemapInventory,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    url = models.URLField(max_length=2048)
    normalized_url = models.URLField(max_length=2048)
    lastmod_hint = models.CharField(max_length=40, blank=True, default="")

    class Meta:
        ordering = ["normalized_url", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "normalized_url"],
                name="core_sitemap_candidate_unique",
            ),
            models.UniqueConstraint(fields=["uuid"], name="core_sitemap_candidate_uuid_unique"),
        ]
        indexes = [
            models.Index(
                fields=["inventory", "normalized_url"],
                name="core_sitemap_candidate_url_idx",
            )
        ]


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
