"""Right-Sizing Agent — recommends optimal instance types and worker counts."""

from __future__ import annotations

from digitaltap.models.cluster import ClusterInfo, ClusterStatus
from digitaltap.models.metrics import Finding, Severity

from .base import BaseAgent

# Simplified instance pricing for right-sizing recommendations
_INSTANCE_FAMILY: dict[str, list[tuple[str, int, float]]] = {
    # (type, vCPUs, hourly_cost)
    "m5": [("m5.large", 2, 0.096), ("m5.xlarge", 4, 0.192), ("m5.2xlarge", 8, 0.384), ("m5.4xlarge", 16, 0.768)],
    "r5": [("r5.large", 2, 0.126), ("r5.xlarge", 4, 0.252), ("r5.2xlarge", 8, 0.504), ("r5.4xlarge", 16, 1.008)],
    "c5": [("c5.large", 2, 0.085), ("c5.xlarge", 4, 0.170), ("c5.2xlarge", 8, 0.340), ("c5.4xlarge", 16, 0.680)],
    "i3": [("i3.large", 2, 0.156), ("i3.xlarge", 4, 0.312), ("i3.2xlarge", 8, 0.624)],
}


class RightSizingAgent(BaseAgent):
    name = "right_sizing"
    description = "Recommends optimal instance types and worker counts based on utilization"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.utilization_threshold = self.options.get("utilization_threshold", 0.3)

    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        findings: list[Finding] = []

        running = [c for c in clusters if c.status == ClusterStatus.RUNNING and c.num_workers > 1]

        for cluster in running:
            result = self._evaluate_sizing(cluster)
            if result is None:
                continue

            rec_workers, rec_type, current_cost, new_cost, reason = result
            savings_hr = current_cost - new_cost
            savings_monthly = savings_hr * 720

            if savings_hr < 0.50:  # skip trivial savings
                continue

            severity = Severity.HIGH if savings_monthly > 500 else (
                Severity.MEDIUM if savings_monthly > 100 else Severity.LOW
            )

            llm_text = await self._llm_analyze(
                f"Cluster '{cluster.name}': {cluster.num_workers}x {cluster.instance_type} "
                f"at {cluster.cpu_utilization*100:.0f}% CPU, {cluster.memory_utilization*100:.0f}% memory. "
                f"Costs ${current_cost:.2f}/hr. "
                f"Proposed: {rec_workers}x {rec_type} at ${new_cost:.2f}/hr. "
                f"Reason: {reason}. "
                f"Is this right-sizing safe? Any risks? 2 sentences."
            )

            recommendation = llm_text or (
                f"Resize from {cluster.num_workers}x {cluster.instance_type} to "
                f"{rec_workers}x {rec_type} — saves ${savings_hr:.2f}/hr "
                f"(${savings_monthly:.0f}/mo). {reason}"
            )

            findings.append(
                Finding(
                    agent=self.name,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    severity=severity,
                    title=(
                        f"Overprovisioned: {cluster.num_workers} workers at "
                        f"{cluster.cpu_utilization*100:.0f}% util → {rec_workers} workers"
                    ),
                    description=(
                        f"Cluster '{cluster.name}' runs {cluster.num_workers}x {cluster.instance_type} "
                        f"but only uses {cluster.cpu_utilization*100:.0f}% CPU / "
                        f"{cluster.memory_utilization*100:.0f}% memory. "
                        f"Downsizing to {rec_workers}x {rec_type} saves ${savings_hr:.2f}/hr."
                    ),
                    recommendation=recommendation,
                    estimated_savings_per_hour=round(savings_hr, 2),
                    estimated_savings_monthly=round(savings_monthly, 2),
                    evidence={
                        "current_workers": cluster.num_workers,
                        "recommended_workers": rec_workers,
                        "current_instance": cluster.instance_type,
                        "recommended_instance": rec_type,
                        "cpu_util": cluster.cpu_utilization,
                        "mem_util": cluster.memory_utilization,
                        "current_cost_hr": current_cost,
                        "new_cost_hr": new_cost,
                    },
                    llm_analysis=llm_text,
                )
            )

        return findings

    def _evaluate_sizing(
        self, cluster: ClusterInfo
    ) -> tuple[int, str, float, float, str] | None:
        """Evaluate if cluster is over-provisioned. Returns (new_workers, new_type, old_cost, new_cost, reason)."""
        max_util = max(cluster.cpu_utilization, cluster.memory_utilization)

        if max_util >= self.utilization_threshold:
            return None  # adequately sized

        # Strategy 1: Reduce worker count
        # Target: bring utilization to ~60% of new capacity
        target_util = 0.6
        ideal_workers = max(1, int(cluster.num_workers * max_util / target_util))

        if ideal_workers >= cluster.num_workers:
            return None

        # Estimate costs
        family = cluster.instance_type.split(".")[0] if "." in cluster.instance_type else "m5"
        family_info = _INSTANCE_FAMILY.get(family, _INSTANCE_FAMILY["m5"])

        # Find current per-worker cost
        per_worker = cluster.hourly_cost_usd / max(cluster.num_workers + 1, 1)  # +1 for driver

        # Strategy 2: Also consider smaller instance type
        rec_type = cluster.instance_type
        rec_cost_per = per_worker

        if max_util < 0.15 and len(family_info) > 1:
            # Very low util — try one size smaller
            current_idx = next(
                (i for i, (t, _, _) in enumerate(family_info) if t == cluster.instance_type),
                -1,
            )
            if current_idx > 0:
                rec_type, _, rec_cost_per = family_info[current_idx - 1]

        current_cost = cluster.hourly_cost_usd
        new_cost = rec_cost_per * (ideal_workers + 1)  # +1 for driver

        if new_cost >= current_cost * 0.85:  # need at least 15% savings
            return None

        reason = (
            f"CPU at {cluster.cpu_utilization*100:.0f}%, memory at "
            f"{cluster.memory_utilization*100:.0f}% — cluster is significantly over-provisioned."
        )

        return ideal_workers, rec_type, round(current_cost, 2), round(new_cost, 2), reason
