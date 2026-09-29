"""Daily dashboard observations, independent of crawling and paid provider calls."""

from datetime import UTC, timedelta
from itertools import batched

from django.utils import timezone

from apps.core.dashboard import DashboardService
from apps.core.models import Project, ProjectMetricSnapshot

METRICS = (
    ("domain_rating", "Domain Rating"),
    ("indexed_pages", "Indexed pages"),
    ("links_out", "Links out"),
    ("domains_out", "Domains out"),
    ("links_in", "Links in"),
    ("domains_in", "Domains in"),
)


def capture_daily_metrics(*, now=None):
    """Hourly recovery sweep; uniqueness makes each UTC day's first capture immutable."""
    now = now or timezone.now()
    day = now.astimezone(UTC).date()
    pending = Project.objects.exclude(metric_snapshots__date=day).order_by("pk")
    captured = 0
    for projects in batched(pending.iterator(chunk_size=200), 200, strict=False):
        given, received = DashboardService.link_counts([project.pk for project in projects])
        for project in projects:
            outgoing = given.get(project.pk, {})
            incoming = received.get(project.pk, {})
            _, created = ProjectMetricSnapshot.objects.get_or_create(
                project=project,
                date=day,
                defaults={
                    "captured_at": now,
                    "domain_rating": project.ahrefs_domain_rating
                    if project.ahrefs_domain_rating_updated_at
                    else None,
                    "domain_rating_updated_at": project.ahrefs_domain_rating_updated_at,
                    "indexed_pages": project.active_article_count,
                    "links_out": outgoing.get("link_count", 0),
                    "domains_out": outgoing.get("domain_count", 0),
                    "links_in": incoming.get("link_count", 0),
                    "domains_in": incoming.get("domain_count", 0),
                },
            )
            captured += created
    return captured


def _chart(rows, field, label):
    values = [float(getattr(row, field)) for row in rows if getattr(row, field) is not None]
    ceiling = 100 if field == "domain_rating" else max(values, default=1) or 1
    span = max((rows[-1].date - rows[0].date).days, 1)
    points, path = [], []
    previous_day = None
    for row in rows:
        value = getattr(row, field)
        if value is None:
            previous_day = None
            continue
        x = 48 + (row.date - rows[0].date).days / span * 504
        y = 150 - float(value) / ceiling * 130
        continuous = previous_day is not None and (row.date - previous_day).days == 1
        path.append(f"{'L' if continuous else 'M'}{x:.2f},{y:.2f}")
        points.append({"x": f"{x:.2f}", "y": f"{y:.2f}", "date": row.date, "value": value})
        previous_day = row.date
    return {
        "label": label,
        "path": " ".join(path),
        "points": points,
        "ceiling": ceiling,
        "latest": getattr(rows[-1], field),
    }


def metric_history(project, requested_days=None):
    days = int(requested_days) if str(requested_days) in {"30", "90", "365"} else 90
    today = timezone.now().astimezone(UTC).date()
    rows = list(
        project.metric_snapshots.filter(
            date__gte=today - timedelta(days=days - 1),
            date__lte=today,
        ).order_by("date")
    )
    return {
        "days": days,
        "rows": rows,
        "ranges": (30, 90, 365),
        "charts": [_chart(rows, field, label) for field, label in METRICS] if rows else [],
    }
