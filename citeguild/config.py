"""Typed, secret-safe runtime configuration for CiteGuild components."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured


def _text(values: Mapping[str, str], name: str, default: str = "") -> str:
    return values.get(name, default).strip()


def _integer(values: Mapping[str, str], name: str, default: int, *, minimum: int = 1) -> int:
    raw = _text(values, name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be an integer.") from error
    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be at least {minimum}.")
    return value


def _number(values: Mapping[str, str], name: str, default: float, *, minimum: float) -> float:
    raw = _text(values, name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ImproperlyConfigured(f"{name} must be a number.") from error
    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be at least {minimum}.")
    return value


def _boolean(values: Mapping[str, str], name: str, default: bool = False) -> bool:
    raw = _text(values, name, str(default)).lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean.")


def _has_url_password(url: str) -> bool:
    return bool(urlparse(url).password)


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """One validated contract shared by the web and worker processes."""

    environment: str
    process_type: str
    site_url: str
    qdrant_collection: str
    qdrant_timeout_seconds: float
    embedding_model: str
    embedding_dimensions: int
    crawl_request_timeout_seconds: float
    crawl_max_redirects: int
    crawl_max_sitemap_bytes: int
    crawl_max_sitemap_entries: int
    crawl_max_page_bytes: int
    crawl_concurrency: int
    reconcile_interval_hours: int
    indexing_enabled: bool
    billing_enabled: bool
    secret_key: str = field(repr=False)
    database_url: str = field(repr=False)
    database_password: str = field(repr=False)
    redis_url: str = field(repr=False)
    redis_password: str = field(repr=False)
    qdrant_url: str = field(repr=False)
    qdrant_api_key: str = field(repr=False)
    stripe_secret_key: str = field(repr=False)
    stripe_context: str = field(repr=False)
    stripe_webhook_secret: str = field(repr=False)
    stripe_price_id_monthly: str = field(repr=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RuntimeConfig:
        config = cls(
            environment=_text(values, "ENVIRONMENT"),
            process_type=_text(values, "APP_PROCESS_TYPE", "server"),
            site_url=_text(values, "SITE_URL"),
            qdrant_collection=_text(values, "CITEGUILD_QDRANT_COLLECTION", "citeguild-articles"),
            qdrant_timeout_seconds=_number(values, "QDRANT_TIMEOUT_SECONDS", 5.0, minimum=0.1),
            embedding_model=_text(
                values,
                "CITEGUILD_EMBEDDING_MODEL",
                "openai/text-embedding-3-small",
            ),
            embedding_dimensions=_integer(values, "CITEGUILD_EMBEDDING_DIMENSIONS", 1536),
            crawl_request_timeout_seconds=_number(
                values, "CITEGUILD_CRAWL_REQUEST_TIMEOUT_SECONDS", 20.0, minimum=0.1
            ),
            crawl_max_redirects=_integer(values, "CITEGUILD_CRAWL_MAX_REDIRECTS", 5, minimum=0),
            crawl_max_sitemap_bytes=_integer(
                values, "CITEGUILD_CRAWL_MAX_SITEMAP_BYTES", 10_000_000
            ),
            crawl_max_sitemap_entries=_integer(
                values, "CITEGUILD_CRAWL_MAX_SITEMAP_ENTRIES", 50_000
            ),
            crawl_max_page_bytes=_integer(values, "CITEGUILD_CRAWL_MAX_PAGE_BYTES", 5_000_000),
            crawl_concurrency=_integer(values, "CITEGUILD_CRAWL_CONCURRENCY", 4),
            reconcile_interval_hours=_integer(values, "CITEGUILD_RECONCILE_INTERVAL_HOURS", 24),
            indexing_enabled=_boolean(values, "CITEGUILD_INDEXING_ENABLED"),
            billing_enabled=_boolean(values, "CITEGUILD_BILLING_ENABLED"),
            secret_key=_text(values, "SECRET_KEY"),
            database_url=_text(values, "DATABASE_URL"),
            database_password=_text(values, "POSTGRES_PASSWORD"),
            redis_url=_text(values, "REDIS_URL"),
            redis_password=_text(values, "REDIS_PASSWORD"),
            qdrant_url=_text(values, "QDRANT_URL"),
            qdrant_api_key=_text(values, "QDRANT_API_KEY"),
            stripe_secret_key=_text(values, "STRIPE_SECRET_KEY"),
            stripe_context=_text(values, "STRIPE_CONTEXT"),
            stripe_webhook_secret=_text(values, "STRIPE_WEBHOOK_SECRET"),
            stripe_price_id_monthly=_text(values, "STRIPE_PRICE_ID_MONTHLY"),
        )
        config._validate(values)
        return config

    def _validate(self, values: Mapping[str, str]) -> None:
        self._validate_base()
        if self.environment == "prod":
            self._validate_production(values)

    def _validate_base(self) -> None:
        if self.environment not in {"dev", "test", "prod"}:
            raise ImproperlyConfigured("ENVIRONMENT must be dev, test, or prod.")
        if self.process_type not in {"server", "worker"}:
            raise ImproperlyConfigured("APP_PROCESS_TYPE must be server or worker.")
        if not self.secret_key:
            raise ImproperlyConfigured("SECRET_KEY is required.")
        if not self.site_url:
            raise ImproperlyConfigured("SITE_URL is required.")

    def _validate_production(self, values: Mapping[str, str]) -> None:
        if self.secret_key == "super-secret-key":
            raise ImproperlyConfigured("SECRET_KEY must not use the development template value.")
        if not self.site_url.startswith("https://"):
            raise ImproperlyConfigured("SITE_URL must use HTTPS in production.")

        split_database_values = (
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "POSTGRES_HOST",
        )
        if not self.database_url and not all(_text(values, name) for name in split_database_values):
            raise ImproperlyConfigured(
                "DATABASE_URL or POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, and "
                "POSTGRES_HOST are required in production."
            )
        if self.database_url and not _has_url_password(self.database_url):
            raise ImproperlyConfigured("DATABASE_URL must include authentication in production.")
        if not self.redis_password and not _has_url_password(self.redis_url):
            raise ImproperlyConfigured("Redis authentication is required in production.")
        if not self.qdrant_url:
            raise ImproperlyConfigured("QDRANT_URL is required in production.")
        if not self.qdrant_api_key:
            raise ImproperlyConfigured("QDRANT_API_KEY is required in production.")

        if self.billing_enabled:
            self._validate_billing()

    def _validate_billing(self) -> None:
        for name, value in (
            ("STRIPE_SECRET_KEY", self.stripe_secret_key),
            ("STRIPE_CONTEXT", self.stripe_context),
            ("STRIPE_WEBHOOK_SECRET", self.stripe_webhook_secret),
            ("STRIPE_PRICE_ID_MONTHLY", self.stripe_price_id_monthly),
        ):
            if not value:
                raise ImproperlyConfigured(
                    f"{name} is required when CITEGUILD_BILLING_ENABLED=true."
                )

    @property
    def fingerprint(self) -> str:
        """Hash public behavior-affecting values, never credentials or connection URLs."""
        public_contract = {
            "billing_enabled": self.billing_enabled,
            "crawl_concurrency": self.crawl_concurrency,
            "crawl_max_page_bytes": self.crawl_max_page_bytes,
            "crawl_max_redirects": self.crawl_max_redirects,
            "crawl_max_sitemap_bytes": self.crawl_max_sitemap_bytes,
            "crawl_max_sitemap_entries": self.crawl_max_sitemap_entries,
            "crawl_request_timeout_seconds": self.crawl_request_timeout_seconds,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_model": self.embedding_model,
            "environment": self.environment,
            "indexing_enabled": self.indexing_enabled,
            "qdrant_collection": self.qdrant_collection,
            "qdrant_timeout_seconds": self.qdrant_timeout_seconds,
            "reconcile_interval_hours": self.reconcile_interval_hours,
            "site_url": self.site_url,
        }
        encoded = json.dumps(public_contract, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()[:16]
