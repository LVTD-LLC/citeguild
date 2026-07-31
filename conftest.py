from logging.handlers import BufferingHandler

import pytest
from django.conf import settings


@pytest.fixture
def collecting_log_handler():
    handler = BufferingHandler(capacity=100)
    yield handler
    handler.close()


def pytest_configure(config):
    settings.STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


@pytest.fixture(scope="session")
def django_db_modify_db_settings(django_db_modify_db_settings_parallel_suffix):
    """Let pytest-django reuse an already-migrated PGSandbox database."""
    if not settings.USE_EXISTING_TEST_DATABASE:
        return

    default_database = settings.DATABASES["default"]
    default_database.setdefault("TEST", {})
    default_database["TEST"]["NAME"] = default_database["NAME"]


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="password123",
    )


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def profile(user):
    return user.profile
