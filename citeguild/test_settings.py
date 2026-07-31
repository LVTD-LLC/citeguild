"""Django settings used by pytest and CI test runs."""

import os
from pathlib import Path
from tempfile import gettempdir

from citeguild import settings as base_settings

for setting_name in dir(base_settings):
    if setting_name.isupper():
        globals()[setting_name] = getattr(base_settings, setting_name)

TEST_WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER") or str(os.getpid())
TEST_RUNTIME_ROOT = Path(gettempdir()) / "citeguild_tests" / TEST_WORKER_ID

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = str(TEST_RUNTIME_ROOT / "media")
ALLOWED_HOSTS = [*base_settings.ALLOWED_HOSTS, "localhost", "testserver"]

STORAGES = {
    **base_settings.STORAGES,
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {
            "location": MEDIA_ROOT,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": f"citeguild-test-cache-{TEST_WORKER_ID}",
        "KEY_PREFIX": f"test:{TEST_WORKER_ID}",
    }
}

Q_CLUSTER = {
    **{key: value for key, value in base_settings.Q_CLUSTER.items() if key != "redis"},
    "name": f"citeguild-test-{TEST_WORKER_ID}",
    "orm": "default",
    "timeout": 30,
    "retry": 60,
    "workers": 1,
    "max_attempts": 1,
    "save_limit": 0,
    "error_reporter": {},
}
