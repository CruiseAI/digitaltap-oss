"""Cluster Manager Agent — detects AND actively manages idle clusters.

This is the money-saving agent. It doesn't just report — it takes action:
- Detects idle clusters using configurable policies
- Hibernates or stops them (with dry-run as the safe default)
- Respects grace periods, exclusion lists, and CPU thresholds
- Logs every action with timestamps and reasons

Modes:
  dry-run (default) — shows what WOULD be stopped, takes no action
  enforce           — actually stops/hibernates clusters via the collector
"""

from __future__ import annotations

import logging
from datetime import datetime

from digitaltap.collectors.base import BaseCollector
from digitaltap.models.cluster import ClusterInfo, ClusterStatus
from digitaltap.models.metrics import (
    ActionLog,
    ActionStatus,
    ActionType,
    Finding,
    Severity,
)

from .base import BaseAgent

logger = logging.getLogger(__name__)


class ClusterManagerAgent(BaseAgent):
    name = "cluster_manager"
    description = "Detects idle clusters and automatically hibernates/stops them"

    def __init__(self, collector: BaseCollector | None = None, **kwargs):
        super().__init__(**kwargs)
        self.collector = collector

        # Policy: when to act
        self.idle_threshold_minutes: float = self.options.get("idle_threshold_minutes", 15)
        self.cpu_threshold: float = self.options.get("cpu_threshold", 0.05)  # 5%
        self.grace_period_minutes: float = self.options.get("grace_period_minutes", 5)

        # Policy: how to act
        self.enforce: bool = self.options.get("enforce", False)
        self.default_action: str = self.options.get("default_action", "hibernate")  # hibernate | stop

        # Policy: who NOT to touch
        self.protected_clusters: list[str] = self.options.get("protected_clusters", [])
        self.protected_tags: dict[str, str] = self.options.get("protected_tags", {"protected": "true"})
        self.protected_workspaces: list[str] = self.options.get("protected_workspaces", [])

        # State
        self.action_log: list[ActionLog] = []

    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        """Analyze clusters, build findings, and optionally take action."""
        findings: list[Finding] = []
        self.action_log.clear()

        for cluster in clusters:
            if cluster.status != ClusterStatus.RUNNING:
                continue

            # --- Check protection rules ---
            skip_reason = self._check_protected(cluster)
            if skip_reason:
                self.action_log.append(ActionLog(
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    action=ActionType.SKIP_PROTECTED,
                    status=ActionStatus.SKIPPED,
                    reason=f"Protected: {skip_reason}",
                ))
                continue

            # --- Evaluate idle policy ---
            violation = self._evaluate_policy(cluster)
            if violation is None:
                continue  # cluster is fine

            policy_reason, severity = violation

            # --- Grace period check ---
            if cluster.idle_minutes < (self.idle_threshold_minutes + self.grace_period_minutes):
                if cluster.idle_minutes >= self.idle_threshold_minutes:
                    self.action_log.append(ActionLog(
                        cluster_id=cluster.id,
                        cluster_name=cluster.name,
                        action=ActionType.SKIP_GRACE_PERIOD,
                        status=ActionStatus.SKIPPED,
                        reason=(
                            f"In grace period ({cluster.idle_minutes:.0f}m idle, "
                            f"threshold {self.idle_threshold_minutes}m + "
                            f"{self.grace_period_minutes}m grace)"
                        ),
                        savings_per_hour=cluster.hourly_cost_usd,
                    ))
                    # Still report finding but don't act
                    findings.append(self._build_finding(cluster, policy_reason, severity, acted=False, grace=True))
                    continue

            # --- Determine action ---
            action_type = ActionType.HIBERNATE if self.default_action == "hibernate" else ActionType.STOP

            # --- LLM analysis for context ---
            llm_text = await self._llm_analyze(
                f"Cluster '{cluster.name}' is idle ({cluster.idle_minutes:.0f}m) with "
                f"CPU {cluster.cpu_utilization*100:.0f}%, costing ${cluster.hourly_cost_usd:.2f}/hr. "
                f"Should we {self.default_action} it? Any risks? 1-2 sentences."
            )

            # --- Execute or dry-run ---
            if self.enforce and self.collector and self.collector.supports_actions:
                action_log = await self._execute_action(cluster, action_type, policy_reason)
            else:
                action_log = ActionLog(
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    action=action_type if self.enforce else ActionType.DRY_RUN,
                    status=ActionStatus.DRY_RUN,
                    reason=policy_reason,
                    details=f"Would {self.default_action} — run with --enforce to take action",
                    savings_per_hour=cluster.hourly_cost_usd,
                )

            self.action_log.append(action_log)

            findings.append(self._build_finding(
                cluster, policy_reason, severity,
                acted=(action_log.status == ActionStatus.SUCCESS),
                llm_text=llm_text,
                action_log=action_log,
            ))

        return findings

    def _check_protected(self, cluster: ClusterInfo) -> str | None:
        """Check if cluster is on exclusion list. Returns reason if protected, None if actionable."""
        # Check cluster name / ID
        if cluster.name in self.protected_clusters or cluster.id in self.protected_clusters:
            return f"in exclusion list"

        # Check tags
        for tag_key, tag_val in self.protected_tags.items():
            if cluster.tags.get(tag_key) == tag_val:
                return f"tag {tag_key}={tag_val}"

        # Check workspace
        if cluster.workspace in self.protected_workspaces:
            return f"workspace '{cluster.workspace}' is protected"

        return None

    def _evaluate_policy(self, cluster: ClusterInfo) -> tuple[str, Severity] | None:
        """Evaluate whether a cluster violates idle policy. Returns (reason, severity) or None."""
        reasons: list[str] = []

        # Rule 1: Idle time exceeds threshold
        idle_violation = cluster.idle_minutes >= self.idle_threshold_minutes
        if idle_violation:
            reasons.append(f"idle {cluster.idle_minutes:.0f}m (threshold: {self.idle_threshold_minutes}m)")

        # Rule 2: CPU below threshold while running
        cpu_violation = cluster.cpu_utilization < self.cpu_threshold
        if cpu_violation:
            reasons.append(f"CPU {cluster.cpu_utilization*100:.1f}% (threshold: {self.cpu_threshold*100:.0f}%)")

        # Need at least idle violation (CPU alone doesn't trigger — cluster might be IO-bound)
        if not idle_violation:
            return None

        severity = Severity.CRITICAL if cluster.idle_minutes > 120 else (
            Severity.HIGH if cluster.idle_minutes > 30 else Severity.MEDIUM
        )

        reason = "Policy violation: " + "; ".join(reasons)
        return reason, severity

    async def _execute_action(
        self, cluster: ClusterInfo, action_type: ActionType, reason: str
    ) -> ActionLog:
        """Actually stop or hibernate a cluster via the collector."""
        assert self.collector is not None

        try:
            if action_type == ActionType.HIBERNATE:
                success = await self.collector.hibernate_cluster(cluster.id)
                verb = "Hibernated"
            else:
                success = await self.collector.stop_cluster(cluster.id)
                verb = "Stopped"

            if success:
                logger.info(f"[ClusterManager] {verb} {cluster.name} ({cluster.id}) — {reason}")
                return ActionLog(
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    action=action_type,
                    status=ActionStatus.SUCCESS,
                    reason=reason,
                    details=f"{verb} successfully",
                    savings_per_hour=cluster.hourly_cost_usd,
                )
            else:
                return ActionLog(
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    action=action_type,
                    status=ActionStatus.FAILED,
                    reason=reason,
                    error=f"{action_type.value} returned False",
                    savings_per_hour=0.0,
                )

        except Exception as e:
            logger.error(f"[ClusterManager] Failed to {action_type.value} {cluster.name}: {e}")
            return ActionLog(
                cluster_id=cluster.id,
                cluster_name=cluster.name,
                action=action_type,
                status=ActionStatus.FAILED,
                reason=reason,
                error=str(e),
                savings_per_hour=0.0,
            )

    def _build_finding(
        self,
        cluster: ClusterInfo,
        reason: str,
        severity: Severity,
        acted: bool = False,
        grace: bool = False,
        llm_text: str = "",
        action_log: ActionLog | None = None,
    ) -> Finding:
        wasted = cluster.hourly_cost_usd * (cluster.idle_minutes / 60)
        monthly = cluster.hourly_cost_usd * 720 * min(1.0, cluster.idle_minutes / 60) * 0.4

        if acted:
            status_str = f"✅ {self.default_action.upper()}D"
            rec = f"Cluster was {self.default_action}d automatically. Saving ${cluster.hourly_cost_usd:.2f}/hr."
        elif grace:
            status_str = "⏳ GRACE PERIOD"
            rec = (
                f"Cluster is idle but within grace period. Will be {self.default_action}d "
                f"after {self.idle_threshold_minutes + self.grace_period_minutes:.0f}m total idle time."
            )
        else:
            status_str = f"🔍 WOULD {self.default_action.upper()}"
            rec = (
                f"Run with --enforce to {self.default_action} this cluster and save "
                f"${cluster.hourly_cost_usd:.2f}/hr."
            )

        if llm_text:
            rec = llm_text

        return Finding(
            agent=self.name,
            cluster_id=cluster.id,
            cluster_name=cluster.name,
            severity=severity,
            title=f"[{status_str}] Idle {cluster.idle_minutes:.0f}m — ${cluster.hourly_cost_usd:.2f}/hr",
            description=f"{reason}. Wasted ${wasted:.2f} this session.",
            recommendation=rec,
            estimated_savings_per_hour=cluster.hourly_cost_usd if acted else 0.0,
            estimated_savings_monthly=round(monthly, 2),
            evidence={
                "idle_minutes": cluster.idle_minutes,
                "cpu_utilization": cluster.cpu_utilization,
                "hourly_cost": cluster.hourly_cost_usd,
                "wasted_this_session": round(wasted, 2),
                "action_taken": action_log.action.value if action_log else "none",
                "action_status": action_log.status.value if action_log else "none",
                "enforce_mode": self.enforce,
                "protected": False,
            },
            llm_analysis=llm_text,
        )
