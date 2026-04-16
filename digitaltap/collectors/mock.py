"""Mock collector — generates realistic cluster data for demos and testing.

Supports simulated stop/hibernate actions with state tracking so the
cluster manager agent demo shows real-looking enforcement output.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from digitaltap.models.cluster import ClusterInfo, ClusterStatus

from .base import BaseCollector

logger = logging.getLogger(__name__)

# Realistic instance types and their hourly costs
_INSTANCE_TYPES = {
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
    "i3.xlarge": 0.312,
    "i3.2xlarge": 0.624,
    "c5.2xlarge": 0.340,
    "c5.4xlarge": 0.680,
    "p3.2xlarge": 3.06,
    "g4dn.xlarge": 0.526,
}

_CLUSTER_TEMPLATES = [
    # (name, instance_type, workers, status_bias, idle_bias, util_bias, usage_pattern)
    ("etl-pipeline-prod", "i3.2xlarge", 8, "running", "high_idle", "low", "weekday_business"),
    ("ml-training-gpu", "p3.2xlarge", 4, "running", "active", "spike", "sporadic"),
    ("dev-sandbox-team-a", "m5.xlarge", 2, "running", "active", "medium", "weekday_business"),
    ("dev-sandbox-team-b", "m5.2xlarge", 3, "running", "high_idle", "low", "weekday_business"),
    ("data-warehouse-main", "r5.4xlarge", 16, "running", "active", "medium_high", "always_on"),
    ("reporting-cluster", "r5.2xlarge", 16, "running", "active", "very_low", "weekday_morning"),
    ("staging-analytics", "m5.2xlarge", 6, "running", "high_idle", "low", "weekday_business"),
    ("stream-processing", "c5.4xlarge", 4, "running", "active", "high", "always_on"),
    ("ad-hoc-queries", "m5.4xlarge", 8, "running", "medium_idle", "medium", "sporadic"),
    ("nightly-batch", "i3.xlarge", 12, "stopped", "active", "high", "nightly"),
    ("ml-inference-api", "g4dn.xlarge", 2, "running", "active", "medium", "always_on"),
    ("data-quality-checks", "c5.2xlarge", 4, "running", "medium_idle", "low", "weekday_morning"),
]

_WORKSPACES = ["production", "staging", "development"]


def _usage_pattern(pattern: str) -> dict[str, float]:
    """Generate realistic usage hours by day of week."""
    if pattern == "weekday_business":
        return {d: random.uniform(7.0, 9.5) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]} | {
            d: random.uniform(0.0, 0.5) for d in ["Sat", "Sun"]
        }
    elif pattern == "weekday_morning":
        return {d: random.uniform(3.0, 5.0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]} | {
            d: 0.0 for d in ["Sat", "Sun"]
        }
    elif pattern == "always_on":
        return {d: random.uniform(22.0, 24.0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    elif pattern == "nightly":
        return {d: random.uniform(2.0, 4.0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
    elif pattern == "sporadic":
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        return {d: random.choice([0.0, 0.0, random.uniform(2.0, 12.0)]) for d in days}
    return {d: random.uniform(4.0, 8.0) for d in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}


def _utilization(bias: str) -> tuple[float, float]:
    """Return (cpu_util, mem_util) based on bias."""
    ranges = {
        "very_low": (0.03, 0.12),
        "low": (0.08, 0.22),
        "medium": (0.30, 0.55),
        "medium_high": (0.50, 0.75),
        "high": (0.65, 0.90),
        "spike": (0.85, 1.0),
    }
    lo, hi = ranges.get(bias, (0.3, 0.6))
    return round(random.uniform(lo, hi), 3), round(random.uniform(lo, hi), 3)


class MockCollector(BaseCollector):
    """Generates realistic mock cluster data. Supports simulated stop/hibernate."""

    def __init__(self, num_clusters: int | None = None, seed: int | None = None):
        self.num_clusters = num_clusters
        if seed is not None:
            random.seed(seed)
        # Track simulated state changes
        self._stopped: dict[str, str] = {}     # cluster_id -> "stopped" | "hibernated"
        self._action_log: list[dict] = []

    async def collect(self) -> list[ClusterInfo]:
        templates = _CLUSTER_TEMPLATES
        if self.num_clusters is not None:
            templates = templates[: self.num_clusters]

        now = datetime.utcnow()
        clusters: list[ClusterInfo] = []

        for name, inst_type, workers, status_bias, idle_bias, util_bias, usage_pat in templates:
            cluster_id = f"cluster-{name}"
            cost_per_worker = _INSTANCE_TYPES.get(inst_type, 0.50)
            driver_cost = cost_per_worker * 1.2
            hourly_cost = driver_cost + cost_per_worker * workers

            # Determine idle time
            if idle_bias == "high_idle":
                idle_min = random.uniform(30, 180)
            elif idle_bias == "medium_idle":
                idle_min = random.uniform(10, 45)
            else:
                idle_min = random.uniform(0, 5)

            status = ClusterStatus.RUNNING if status_bias == "running" else ClusterStatus.STOPPED
            cpu_util, mem_util = _utilization(util_bias)

            # If it's the cost spike scenario, inflate cost
            if util_bias == "spike":
                hourly_cost *= random.uniform(2.5, 4.0)

            # Apply simulated state changes from previous actions
            if cluster_id in self._stopped:
                action = self._stopped[cluster_id]
                status = ClusterStatus.STOPPED
                idle_min = 0.0
                cpu_util = 0.0
                mem_util = 0.0

            uptime_hrs = random.uniform(1.0, 72.0)
            started = now - timedelta(hours=uptime_hrs)
            last_active = now - timedelta(minutes=idle_min)

            clusters.append(
                ClusterInfo(
                    id=cluster_id,
                    name=name,
                    platform="mock",
                    workspace=random.choice(_WORKSPACES),
                    status=status,
                    instance_type=inst_type,
                    num_workers=workers,
                    driver_instance_type=inst_type,
                    hourly_cost_usd=round(hourly_cost, 2),
                    total_cost_usd=round(hourly_cost * uptime_hrs, 2),
                    started_at=started,
                    last_activity_at=last_active,
                    idle_minutes=round(idle_min, 1),
                    uptime_hours=round(uptime_hrs, 1),
                    cpu_utilization=cpu_util,
                    memory_utilization=mem_util,
                    usage_hours_by_day=_usage_pattern(usage_pat),
                    tags={"team": random.choice(["data-eng", "ml", "analytics", "platform"])},
                )
            )

        return clusters

    async def test_connection(self) -> bool:
        return True

    @property
    def supports_actions(self) -> bool:
        return True

    async def stop_cluster(self, cluster_id: str) -> bool:
        """Simulate stopping a cluster."""
        logger.info(f"[MockCollector] Simulating STOP for {cluster_id}")
        self._stopped[cluster_id] = "stopped"
        self._action_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "cluster_id": cluster_id,
            "action": "stop",
        })
        return True

    async def hibernate_cluster(self, cluster_id: str) -> bool:
        """Simulate hibernating a cluster."""
        logger.info(f"[MockCollector] Simulating HIBERNATE for {cluster_id}")
        self._stopped[cluster_id] = "hibernated"
        self._action_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "cluster_id": cluster_id,
            "action": "hibernate",
        })
        return True

    def get_action_log(self) -> list[dict]:
        """Return all simulated actions taken."""
        return list(self._action_log)

    def reset_actions(self) -> None:
        """Clear simulated state (useful between test runs)."""
        self._stopped.clear()
        self._action_log.clear()
