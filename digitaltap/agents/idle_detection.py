"""Idle Cluster Detection Agent — finds clusters running with no workload."""

from __future__ import annotations

from digitaltap.models.cluster import ClusterInfo, ClusterStatus
from digitaltap.models.metrics import Finding, Severity

from .base import BaseAgent


class IdleDetectionAgent(BaseAgent):
    name = "idle_detection"
    description = "Detects clusters that are running but have no active workload"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.idle_threshold_minutes = self.options.get("idle_threshold_minutes", 15)

    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        findings: list[Finding] = []

        idle_clusters = [
            c
            for c in clusters
            if c.status == ClusterStatus.RUNNING and c.idle_minutes >= self.idle_threshold_minutes
        ]

        for cluster in idle_clusters:
            wasted_cost = cluster.hourly_cost_usd * (cluster.idle_minutes / 60)
            monthly_waste = cluster.hourly_cost_usd * self._estimate_idle_hours_monthly(cluster)

            severity = Severity.CRITICAL if cluster.idle_minutes > 120 else (
                Severity.HIGH if cluster.idle_minutes > 30 else Severity.MEDIUM
            )

            # Try LLM analysis for richer recommendations
            llm_text = await self._llm_analyze(
                f"Cluster '{cluster.name}' has been idle for {cluster.idle_minutes:.0f} minutes. "
                f"It costs ${cluster.hourly_cost_usd:.2f}/hr with {cluster.num_workers} workers "
                f"({cluster.instance_type}). "
                f"Usage pattern: {cluster.usage_hours_by_day}. "
                f"What's the best action — hibernate, terminate, or schedule? "
                f"Give a 2-sentence recommendation."
            )

            recommendation = llm_text or self._rule_based_recommendation(cluster)

            findings.append(
                Finding(
                    agent=self.name,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    severity=severity,
                    title=f"Idle for {cluster.idle_minutes:.0f} min (${cluster.hourly_cost_usd:.2f}/hr)",
                    description=(
                        f"Cluster '{cluster.name}' has been idle for {cluster.idle_minutes:.0f} minutes "
                        f"while costing ${cluster.hourly_cost_usd:.2f}/hr. "
                        f"${wasted_cost:.2f} wasted in this idle session."
                    ),
                    recommendation=recommendation,
                    estimated_savings_per_hour=cluster.hourly_cost_usd,
                    estimated_savings_monthly=round(monthly_waste, 2),
                    evidence={
                        "idle_minutes": cluster.idle_minutes,
                        "hourly_cost": cluster.hourly_cost_usd,
                        "wasted_this_session": round(wasted_cost, 2),
                        "instance_type": cluster.instance_type,
                        "workers": cluster.num_workers,
                    },
                    llm_analysis=llm_text,
                )
            )

        return findings

    def _estimate_idle_hours_monthly(self, cluster: ClusterInfo) -> float:
        """Estimate monthly idle hours from usage patterns."""
        total_usage = sum(cluster.usage_hours_by_day.values())
        if total_usage == 0:
            return cluster.hourly_cost_usd * 720  # assume always idle
        total_possible = 24 * 7
        idle_ratio = max(0, 1 - total_usage / total_possible)
        # Scale: clusters with high idle now likely idle often
        return idle_ratio * 720 * min(1.0, cluster.idle_minutes / 60)

    def _rule_based_recommendation(self, cluster: ClusterInfo) -> str:
        if cluster.idle_minutes > 120:
            return (
                f"Terminate or hibernate immediately — {cluster.idle_minutes:.0f} min idle "
                f"is burning ${cluster.hourly_cost_usd:.2f}/hr for nothing."
            )
        elif cluster.idle_minutes > 30:
            return (
                f"Hibernate this cluster to save ${cluster.hourly_cost_usd:.2f}/hr. "
                f"It can resume in ~60s when needed."
            )
        else:
            return (
                f"Consider setting a {self.idle_threshold_minutes}-minute auto-hibernate policy "
                f"to prevent idle waste."
            )
