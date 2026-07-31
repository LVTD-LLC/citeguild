"""Load mutmut's copied application modules after Django starts pytest."""

import os
import sys
from pathlib import Path

MUTATED_MODULES = (
    "apps.api.services",
    "apps.api.views",
    "apps.core.utils",
)


def pytest_sessionstart(session):
    """Prefer modules in mutmut's workspace over modules Django imported early."""
    del session
    if not os.environ.get("MUTANT_UNDER_TEST"):
        return

    import apps
    import apps.api
    import apps.core

    for package, relative_path in (
        (apps, "apps"),
        (apps.api, "apps/api"),
        (apps.core, "apps/core"),
    ):
        mutated_path = str(Path.cwd() / relative_path)
        if mutated_path not in package.__path__:
            package.__path__.insert(0, mutated_path)

    for module_name in MUTATED_MODULES:
        sys.modules.pop(module_name, None)
