"""Scheduler Agent — suggests start/stop schedules based on usage patterns."""

from __future__ import annotations

from digitaltap.models.cluster import ClusterInfo, ClusterStatus
from digitaltap.models.metrics import Finding, Severity

from .base import BaseAgent

_ALL_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
_WEEKENDS = ["Sat", "Sun"]


class SchedulerAgent(BaseAgent):
    name = "scheduler"
    description = "Suggests start/stop schedules to avoid paying for idle off-hours"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.min_savings_pct = self.options.get("min_schedule_savings_pct", 20)

    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        findings: list[Finding] = []

        candidates = [
            c for c in clusters
            if c.status in (ClusterStatus.RUNNING, ClusterStatus.IDLE)
            and c.usage_hours_by_day
        ]

        for cluster in candidates:
            schedule = self._detect_schedule(cluster)
            if schedule is None:
                continue

            pattern, active_days, active_hours, savings_pct = schedule
            if savings_pct < self.min_savings_pct:
                continue

            weekly_savings = cluster.hourly_cost_usd * self._off_hours_per_week(
                active_days, active_hours
            )
            monthly_savings = weekly_savings * 4.33

            severity = Severity.HIGH if monthly_savings > 400 else (
                Severity.MEDIUM if monthly_savings > 100 else Severity.LOW
            )

            llm_text = await self._llm_analyze(
                f"Cluster '{cluster.name}' (${cluster.hourly_cost_usd:.2f}/hr) shows a "
                f"'{pattern}' usage pattern: active {', '.join(active_days)} ~{active_hours}hrs/day. "
                f"It's currently running 24/7. Scheduling saves ${weekly_savings:.0f}/week. "
                f"Suggest a specific cron schedule and any caveats in 2 sentences."
            )

            schedule_str = self._format_schedule(active_days, active_hours)
            recommendation = llm_text or (
                f"Schedule this cluster to run {schedule_str}. "
                f"This saves ${weekly_savings:.0f}/week (${monthly_savings:.0f}/month) — "
                f"a {savings_pct:.0f}% reduction."
            )

            findings.append(
                Finding(
                    agent=self.name,
                    cluster_id=cluster.id,
                    cluster_name=cluster.name,
                    severity=severity,
                    title=f"Schedule opportunity: {pattern} pattern saves ${weekly_savings:.0f}/week",
                    description=(
                        f"Cluster '{cluster.name}' is running 24/7 but only actively used "
                        f"during {pattern} hours. Scheduling saves {savings_pct:.0f}% of cost."
                    ),
                    recommendation=recommendation,
                    estimated_savings_per_hour=round(
                        cluster.hourly_cost_usd * savings_pct / 100, 2
                    ),
                    estimated_savings_monthly=round(monthly_savings, 2),
                    evidence={
                        "pattern": pattern,
                        "active_days": active_days,
                        "active_hours_per_day": active_hours,
                        "schedule": schedule_str,
                        "savings_pct": round(savings_pct, 1),
                        "weekly_savings": round(weekly_savings, 2),
                        "usage_by_day": cluster.usage_hours_by_day,
                    },
                    llm_analysis=llm_text,
                )
            )

        return findings

    def _detect_schedule(
        self, cluster: ClusterInfo
    ) -> tuple[str, list[str], float, float] | None:
        """Detect usage pattern. Returns (pattern_name, active_days, avg_active_hours, savings_pct)."""
        usage = cluster.usage_hours_by_day
        if not usage:
            return None

        weekday_hours = [usage.get(d, 0) for d in _WEEKDAYS]
        weekend_hours = [usage.get(d, 0) for d in _WEEKENDS]

        avg_weekday = sum(weekday_hours) / max(len(weekday_hours), 1)
        avg_weekend = sum(weekend_hours) / max(len(weekend_hours), 1)
        total_weekly = sum(usage.values())

        # Pattern: Weekday-only (weekdays active, weekends minimal)
        if avg_weekday > 3 and avg_weekend < 1:
            active_hours = round(avg_weekday, 1)
            off_hours = (24 - active_hours) * 5 + 24 * 2  # off hours weekdays + all weekend
            savings_pct = off_hours / 168 * 100
            return ("weekday_business", _WEEKDAYS, active_hours, savings_pct)

        # Pattern: Business hours (weekdays, limited hours)
        if avg_weekday > 3 and avg_weekday < 14 and avg_weekend < 2:
            active_hours = round(avg_weekday, 1)
            off_hours = (24 - active_hours) * 5 + 24 * 2
            savings_pct = off_hours / 168 * 100
            return ("business_hours", _WEEKDAYS, active_hours, savings_pct)

        # Pattern: Morning-only
        if avg_weekday > 1 and avg_weekday < 8:
            active_hours = round(avg_weekday, 1)
            off_hours = (24 - active_hours) * 7
            savings_pct = off_hours / 168 * 100
            return ("morning_only", _WEEKDAYS, active_hours, savings_pct)

        # Pattern: Always-on but not fully utilized (24/7 is correct)
        if total_weekly > 140:  # >20hrs/day average
            return None  # correctly running 24/7

        # Pattern: Sporadic — suggest on-demand only
        if total_weekly < 30:
            active_hours = round(total_weekly / 7, 1)
            savings_pct = (1 - total_weekly / 168) * 100
            active_days = [d for d in _ALL_DAYS if usage.get(d, 0) > 1]
            if not active_days:
                active_days = _WEEKDAYS
            return ("sporadic", active_days, active_hours, savings_pct)

        return None

    def _off_hours_per_week(self, active_days: list[str], active_hours: float) -> float:
        """Calculate off-hours per week."""
        on_hours = len(active_days) * active_hours
        return 168 - on_hours

    def _format_schedule(self, active_days: list[str], active_hours: float) -> str:
        if set(active_days) == set(_WEEKDAYS):
            return f"Mon-Fri, {active_hours:.0f}hrs/day (e.g. 8am-{8+active_hours:.0f}:00)"
        days = ", ".join(active_days)
        return f"{days}, {active_hours:.0f}hrs/day"
