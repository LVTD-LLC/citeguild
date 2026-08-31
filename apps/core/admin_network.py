import math
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Count, F
from django.utils import timezone

from apps.core.models import DetectedNetworkLink


@dataclass(frozen=True)
class NetworkPeriod:
    key: str
    label: str
    days: int | None


@dataclass(frozen=True)
class NetworkNode:
    project_id: int
    host: str
    label: str
    x: float
    y: float
    label_y: float
    radius: float
    citation_count: int


@dataclass(frozen=True)
class NetworkEdge:
    source_host: str
    target_host: str
    citation_count: int
    path: str
    label_x: float
    label_y: float
    stroke_width: float


@dataclass(frozen=True)
class AdminNetworkOverview:
    period: NetworkPeriod
    periods: tuple[NetworkPeriod, ...]
    citation_count: int
    connection_count: int
    connected_site_count: int
    omitted_site_count: int
    nodes: tuple[NetworkNode, ...]
    edges: tuple[NetworkEdge, ...]


class AdminNetworkOverviewService:
    """Build a bounded, aggregate-only view of the private member link graph."""

    PERIODS = (
        NetworkPeriod("7", "7 days", 7),
        NetworkPeriod("30", "30 days", 30),
        NetworkPeriod("90", "90 days", 90),
        NetworkPeriod("all", "All time", None),
    )
    DEFAULT_PERIOD = "30"
    GRAPH_SITE_LIMIT = 12
    GRAPH_CONNECTION_LIMIT = 500
    WIDTH = 640
    HEIGHT = 300

    @classmethod
    def build(cls, period_key: str | None) -> AdminNetworkOverview:
        periods = {period.key: period for period in cls.PERIODS}
        period = periods.get(period_key, periods[cls.DEFAULT_PERIOD])

        links = DetectedNetworkLink.objects.filter(is_active=True).exclude(
            source_article__project_id=F("target_project_id")
        )
        if period.days is not None:
            links = links.filter(last_detected_at__gte=timezone.now() - timedelta(days=period.days))

        citation_count = links.count()
        grouped_links = links.values(
            "source_article__project_id",
            "source_article__project__normalized_host",
            "target_project_id",
            "target_project__normalized_host",
        ).annotate(citation_count=Count("id"))
        connection_count = grouped_links.count()

        source_ids = set(links.values_list("source_article__project_id", flat=True).distinct())
        target_ids = set(links.values_list("target_project_id", flat=True).distinct())
        connected_site_count = len(source_ids | target_ids)

        strongest_connections = list(
            grouped_links.order_by(
                "-citation_count",
                "source_article__project__normalized_host",
                "target_project__normalized_host",
            )[: cls.GRAPH_CONNECTION_LIMIT]
        )
        nodes, edges = cls._layout(strongest_connections)

        return AdminNetworkOverview(
            period=period,
            periods=cls.PERIODS,
            citation_count=citation_count,
            connection_count=connection_count,
            connected_site_count=connected_site_count,
            omitted_site_count=max(connected_site_count - len(nodes), 0),
            nodes=nodes,
            edges=edges,
        )

    @classmethod
    def _layout(cls, connections) -> tuple[tuple[NetworkNode, ...], tuple[NetworkEdge, ...]]:
        activity: dict[int, int] = {}
        hosts: dict[int, str] = {}
        for connection in connections:
            source_id = connection["source_article__project_id"]
            target_id = connection["target_project_id"]
            count = connection["citation_count"]
            hosts[source_id] = connection["source_article__project__normalized_host"]
            hosts[target_id] = connection["target_project__normalized_host"]
            activity[source_id] = activity.get(source_id, 0) + count
            activity[target_id] = activity.get(target_id, 0) + count

        selected_ids = {
            project_id
            for project_id, _count in sorted(
                activity.items(),
                key=lambda item: (-item[1], hosts[item[0]]),
            )[: cls.GRAPH_SITE_LIMIT]
        }
        ordered_ids = sorted(selected_ids, key=lambda project_id: hosts[project_id])
        max_activity = max((activity[project_id] for project_id in ordered_ids), default=1)
        center_x = cls.WIDTH / 2
        center_y = cls.HEIGHT / 2
        orbit_x = 245
        orbit_y = 105
        node_positions: dict[int, NetworkNode] = {}

        for index, project_id in enumerate(ordered_ids):
            angle = (2 * math.pi * index / len(ordered_ids)) - (math.pi / 2)
            x = center_x + orbit_x * math.cos(angle)
            y = center_y + orbit_y * math.sin(angle)
            radius = 17 + (8 * math.sqrt(activity[project_id] / max_activity))
            host = hosts[project_id]
            node_positions[project_id] = NetworkNode(
                project_id=project_id,
                host=host,
                label=cls._short_host(host),
                x=round(x, 1),
                y=round(y, 1),
                label_y=round(y + 34, 1),
                radius=round(radius, 1),
                citation_count=activity[project_id],
            )

        visible_connections = [
            connection
            for connection in connections
            if connection["source_article__project_id"] in selected_ids
            and connection["target_project_id"] in selected_ids
        ]
        visible_directions = {
            (
                connection["source_article__project_id"],
                connection["target_project_id"],
            )
            for connection in visible_connections
        }
        max_connection_count = max(
            (connection["citation_count"] for connection in visible_connections),
            default=1,
        )
        edges = tuple(
            cls._edge(
                connection,
                node_positions,
                max_connection_count,
                reciprocal=(
                    connection["target_project_id"],
                    connection["source_article__project_id"],
                )
                in visible_directions,
            )
            for connection in visible_connections
        )

        return tuple(node_positions.values()), edges

    @classmethod
    def _edge(
        cls,
        connection,
        nodes: dict[int, NetworkNode],
        max_connection_count: int,
        *,
        reciprocal: bool,
    ) -> NetworkEdge:
        source_id = connection["source_article__project_id"]
        target_id = connection["target_project_id"]
        source = nodes[source_id]
        target = nodes[target_id]
        dx = target.x - source.x
        dy = target.y - source.y
        distance = math.hypot(dx, dy)
        ux = dx / distance
        uy = dy / distance
        start_x = source.x + ux * (source.radius + 3)
        start_y = source.y + uy * (source.radius + 3)
        end_x = target.x - ux * (target.radius + 8)
        end_y = target.y - uy * (target.radius + 8)
        midpoint_x = (start_x + end_x) / 2
        midpoint_y = (start_y + end_y) / 2
        bend = 18 if reciprocal else 0
        control_x = midpoint_x - uy * bend
        control_y = midpoint_y + ux * bend
        label_x = (start_x + 2 * control_x + end_x) / 4
        label_y = (start_y + 2 * control_y + end_y) / 4
        count = connection["citation_count"]

        return NetworkEdge(
            source_host=source.host,
            target_host=target.host,
            citation_count=count,
            path=(
                f"M {start_x:.1f} {start_y:.1f} "
                f"Q {control_x:.1f} {control_y:.1f} {end_x:.1f} {end_y:.1f}"
            ),
            label_x=round(label_x, 1),
            label_y=round(label_y, 1),
            stroke_width=round(1.25 + 3.75 * math.sqrt(count / max_connection_count), 2),
        )

    @staticmethod
    def _short_host(host: str) -> str:
        if len(host) <= 20:
            return host
        return f"{host[:17]}…"
