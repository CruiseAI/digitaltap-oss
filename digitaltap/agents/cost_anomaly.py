"""Cost Anomaly Detection Agent — finds unexpected spend spikes."""

from __future__ import annotations

from digitaltap.models.cluster import ClusterInfo, ClusterStatus
from digitaltap.models.metrics import Finding, Severity

from .base import BaseAgent


class CostAnomalyAgent(BaseAgent):
    name = "cost_anomaly"
    description = "Detects clusters with unexpected cost spikes or anomalous spend patterns"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.spike_threshold = self.options.get("spike_threshold", 1.5)  # 50% above baseline

    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        findings: list[Finding] = []

        running = [c for c in clusters if c.status == ClusterStatus.RUNNING]

        # Calculate fleet-wide baselines for comparison
        if not running:
            return findings

        costs = [c.hourly_cost_usd for c in running]
        avg_cost = sum(costs) / len(costs)
        median_cost = sorted(costs)[len(costs) // 2]

        for cluster in running:
            anomalies = self._detect_anomalies(cluster, avg_cost, median_cost)
            if not anomalies:
                continue

            anomaly_type, ratio, baseline = anomalies
            increase_pct = (ratio - 1) * 100
            excess_per_hour = cluster.hourly_cost_usd - baseline
            monthly_excess = excess_per_hour * 720

            severity = Severity.CRITICAL if increase_pct > 200 else (
                Severity.HIGH if increase_pct > 100 else Severity.MEDIUM
            )

            llm_text = await self._llm_analyze(
                f"Cluster '{cluster.name}' shows a cost anomaly: "
                f"${cluster.hourly_cost_usd:.2f}/hr vs baseline ${baseline:.2f}/hr "
                f"({increase_pct:.0f}% increase). "
                f"Instance: {cluster.instance_type}, workers: {cluster.num_workers}, "
                f"CPU util: {cluster.cpu_utilization*100:.0f}%, "
                f"Anomaly type: {anomaly_type}. "
                f"Diagnose the likely cause and suggest a fix in 2 sentences."
            )

            recommendation = llm_text or self._rule_based_recommendation(
                cluster, anomaly_type, increase_pct, baseline
            )

            findings.append(
                Finding(
                    agent=self.name,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    severity=severity,
                    title=f"Cost spike {increase_pct:.0f}% above baseline (${cluster.hourly_cost_usd:.2f}/hr)",
                    description=(
                        f"Cluster '{cluster.name}' is running at ${cluster.hourly_cost_usd:.2f}/hr, "
                        f"which is {increase_pct:.0f}% above the baseline of ${baseline:.2f}/hr. "
                        f"Excess spend: ${excess_per_hour:.2f}/hr (${monthly_excess:.0f}/mo at this rate)."
                    ),
                    recommendation=recommendation,
                    estimated_savings_per_hour=round(excess_per_hour, 2),
                    estimated_savings_monthly=round(monthly_excess, 2),
                    evidence={
                        "anomaly_type": anomaly_type,
                        "current_cost_hr": cluster.hourly_cost_usd,
                        "baseline_cost_hr": round(baseline, 2),
                        "increase_pct": round(increase_pct, 1),
                        "instance_type": cluster.instance_type,
                        "workers": cluster.num_workers,
                        "cpu_util": cluster.cpu_utilization,
                    },
                    llm_analysis=llm_text,
                )
            )

        return findings

    def _detect_anomalies(
        self, cluster: ClusterInfo, avg_cost: float, median_cost: float
    ) -> tuple[str, float, float] | None:
        """Detect cost anomalies using multiple heuristics."""
        # Check 1: Cost vs fleet average
        if avg_cost > 0:
            ratio = cluster.hourly_cost_usd / avg_cost
            if ratio >= self.spike_threshold * 2:
                return ("fleet_outlier", ratio, avg_cost)

        # Check 2: Cost-per-worker anomaly (expensive instances)
        if cluster.num_workers > 0:
            cost_per_worker = cluster.hourly_cost_usd / cluster.num_workers
            if cost_per_worker > 3.0:  # GPU-tier pricing
                expected = median_cost
                ratio = cluster.hourly_cost_usd / max(expected, 0.01)
                if ratio >= self.spike_threshold:
                    return ("expensive_instances", ratio, expected)

        # Check 3: High cost + low utilization = anomalous waste
        if (
            cluster.hourly_cost_usd > avg_cost * self.spike_threshold
            and cluster.cpu_utilization < 0.2
        ):
            return ("cost_util_mismatch", cluster.hourly_cost_usd / max(avg_cost, 0.01), avg_cost)

        return None

    def _rule_based_recommendation(
        self, cluster: ClusterInfo, anomaly_type: str, increase_pct: float, baseline: float
    ) -> str:
        if anomaly_type == "expensive_instances":
            return (
                f"This cluster uses {cluster.instance_type} instances at "
                f"${cluster.hourly_cost_usd:.2f}/hr. Consider switching to spot instances "
                f"(up to 70% savings) or a more cost-effective instance family."
            )
        elif anomaly_type == "cost_util_mismatch":
            return (
                f"High cost (${cluster.hourly_cost_usd:.2f}/hr) with only "
                f"{cluster.cpu_utilization*100:.0f}% CPU utilization. "
                f"Right-size to fewer/smaller workers to match actual usage."
            )
        else:
            return (
                f"Cost is {increase_pct:.0f}% above fleet baseline. "
                f"Investigate whether this workload genuinely needs "
                f"${cluster.hourly_cost_usd:.2f}/hr of compute."
            )
