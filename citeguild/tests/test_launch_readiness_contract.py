from pathlib import Path

from django.conf import settings


def test_launch_runbook_covers_required_operator_boundaries():
    content = (Path(settings.BASE_DIR) / "docs/operations/launch-readiness.md").read_text()

    for required in (
        "Current decision: **no-launch pending CG-034 completion**",
        "Component diagnosis and recovery",
        "Abuse and crawler incident flow",
        "Metrics and review cadence",
        "Production-safe failure exercise",
        "Explicit launch risks",
        "public announcement is a separate, explicit decision",
        "API key rotation immediately revokes the prior key",
    ):
        assert required in content
