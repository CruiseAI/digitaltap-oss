"""Finding, action log, and report models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    HIBERNATE = "hibernate"
    STOP = "stop"
    SKIP_PROTECTED = "skip_protected"
    SKIP_GRACE_PERIOD = "skip_grace_period"
    DRY_RUN = "dry_run"


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    SKIPPED = "skipped"


class ActionLog(BaseModel):
    """Record of an action taken (or simulated) by the cluster manager."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cluster_id: str
    cluster_name: str
    action: ActionType
    status: ActionStatus
    reason: str
    details: str = ""
    savings_per_hour: float = 0.0
    error: str = ""

    def format_line(self) -> str:
        ts = self.timestamp.strftime("%H:%M:%S")
        icon = {
            ActionStatus.SUCCESS: "✅",
            ActionStatus.DRY_RUN: "🔍",
            ActionStatus.SKIPPED: "⏭️ ",
            ActionStatus.FAILED: "❌",
        }.get(self.status, "•")
        tag = f"[{self.status.value.upper()}]"
        return f"   {icon} {ts} {tag} {self.cluster_name} — {self.reason}"


class Finding(BaseModel):
    """A single finding from an agent analysis."""

    agent: str
    cluster_id: str
    cluster_name: str
    severity: Severity = Severity.MEDIUM
    title: str
    description: str
    recommendation: str
    estimated_savings_per_hour: float = 0.0
    estimated_savings_monthly: float = 0.0
    evidence: dict[str, Any] = Field(default_factory=dict)
    llm_analysis: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScanReport(BaseModel):
    """Full scan report aggregating all agent findings."""

    scan_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    collector: str = "mock"
    clusters_scanned: int = 0
    findings: list[Finding] = Field(default_factory=list)
    actions: list[ActionLog] = Field(default_factory=list)
    total_monthly_savings: float = 0.0
    total_current_monthly_spend: float = 0.0
    savings_percentage: float = 0.0
    duration_seconds: float = 0.0

    def compute_totals(self) -> None:
        self.total_monthly_savings = sum(f.estimated_savings_monthly for f in self.findings)
        if self.total_current_monthly_spend > 0:
            self.savings_percentage = (
                self.total_monthly_savings / self.total_current_monthly_spend * 100
            )
