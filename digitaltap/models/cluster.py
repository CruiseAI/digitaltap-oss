"""Cluster data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClusterStatus(str, Enum):
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    STARTING = "starting"
    ERROR = "error"


class ClusterInfo(BaseModel):
    """Core cluster information collected from any platform."""

    id: str
    name: str
    platform: str = "unknown"  # databricks, aws, gcp, mock
    workspace: str = ""

    # Status
    status: ClusterStatus = ClusterStatus.RUNNING

    # Size
    instance_type: str = ""
    num_workers: int = 0
    driver_instance_type: str = ""
    autoscale_min: int | None = None
    autoscale_max: int | None = None

    # Cost
    hourly_cost_usd: float = 0.0
    total_cost_usd: float = 0.0

    # Timing
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    idle_minutes: float = 0.0
    uptime_hours: float = 0.0

    # Utilization (0.0 - 1.0)
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0

    # Usage patterns
    usage_hours_by_day: dict[str, float] = Field(default_factory=dict)
    # e.g. {"Mon": 8.5, "Tue": 7.2, ...}

    tags: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
