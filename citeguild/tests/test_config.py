from __future__ import annotations

from io import StringIO

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command

from citeguild.config import RuntimeConfig


def _production_environment(**overrides: str) -> dict[str, str]:
    values = {
        "ENVIRONMENT": "prod",
        "APP_PROCESS_TYPE": "server",
        "SECRET_KEY": "production-secret-that-is-not-a-template-value",
        "SITE_URL": "https://citeguild.app",
        "DATABASE_URL": "postgresql://citeguild:secret@postgres:5432/citeguild",
        "REDIS_URL": "redis://:secret@redis:6379/0",
        "QDRANT_URL": "http://srv-captain--citeguild-qdrant:6333",
        "QDRANT_API_KEY": "qdrant-secret",
    }
    values.update(overrides)
    return values


def test_local_configuration_uses_safe_bounded_defaults() -> None:
    config = RuntimeConfig.from_mapping(
        {
            "ENVIRONMENT": "dev",
            "SECRET_KEY": "local-only",
            "SITE_URL": "http://localhost:8000",
            "POSTGRES_DB": "citeguild",
            "POSTGRES_USER": "citeguild",
            "POSTGRES_PASSWORD": "citeguild",
            "POSTGRES_HOST": "localhost",
        }
    )

    assert config.process_type == "server"
    assert config.qdrant_collection == "citeguild-articles"
    assert config.embedding_dimensions == 1536
    assert config.crawl_max_sitemap_entries == 50_000
    assert config.crawl_max_redirects == 5
    assert config.reconcile_interval_hours == 24


@pytest.mark.parametrize("process_type", ["server", "worker"])
def test_configuration_fingerprint_is_identical_across_processes(process_type: str) -> None:
    environment = _production_environment(APP_PROCESS_TYPE=process_type)

    assert (
        RuntimeConfig.from_mapping(environment).fingerprint
        == RuntimeConfig.from_mapping(
            _production_environment(APP_PROCESS_TYPE="server")
        ).fingerprint
    )


def test_configuration_fingerprint_does_not_depend_on_secrets() -> None:
    first = RuntimeConfig.from_mapping(_production_environment())
    second = RuntimeConfig.from_mapping(
        _production_environment(
            SECRET_KEY="another-production-secret",
            DATABASE_URL="postgresql://citeguild:other@postgres:5432/citeguild",
            REDIS_URL="redis://:other@redis:6379/0",
            QDRANT_API_KEY="another-qdrant-secret",
        )
    )

    assert first.fingerprint == second.fingerprint
    assert "secret" not in first.fingerprint


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"SECRET_KEY": "super-secret-key"}, "SECRET_KEY"),
        ({"SITE_URL": "http://citeguild.app"}, "SITE_URL"),
        ({"DATABASE_URL": ""}, "DATABASE_URL or POSTGRES"),
        (
            {"DATABASE_URL": "postgresql://postgres:5432/citeguild"},
            "DATABASE_URL must include authentication",
        ),
        ({"REDIS_URL": "redis://redis:6379/0"}, "Redis authentication"),
        ({"QDRANT_API_KEY": ""}, "QDRANT_API_KEY"),
    ],
)
def test_production_configuration_fails_clearly(overrides: dict[str, str], message: str) -> None:
    with pytest.raises(ImproperlyConfigured, match=message):
        RuntimeConfig.from_mapping(_production_environment(**overrides))


def test_enabled_billing_requires_complete_stripe_contract() -> None:
    with pytest.raises(ImproperlyConfigured, match="STRIPE_SECRET_KEY"):
        RuntimeConfig.from_mapping(_production_environment(CITEGUILD_BILLING_ENABLED="true"))


def test_invalid_numeric_value_names_the_setting() -> None:
    with pytest.raises(ImproperlyConfigured, match="CITEGUILD_EMBEDDING_DIMENSIONS"):
        RuntimeConfig.from_mapping(
            {
                "ENVIRONMENT": "dev",
                "SECRET_KEY": "local-only",
                "SITE_URL": "http://localhost:8000",
                "POSTGRES_DB": "citeguild",
                "POSTGRES_USER": "citeguild",
                "POSTGRES_PASSWORD": "citeguild",
                "POSTGRES_HOST": "localhost",
                "CITEGUILD_EMBEDDING_DIMENSIONS": "many",
            }
        )


def test_management_command_reports_the_secret_safe_fingerprint() -> None:
    output = StringIO()

    call_command("config_fingerprint", stdout=output)

    assert output.getvalue().strip() == (
        f"CiteGuild configuration fingerprint: {settings.CITEGUILD_CONFIG_FINGERPRINT}"
    )
