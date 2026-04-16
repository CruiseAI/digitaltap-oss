#!/usr/bin/env python3
"""Demo: use Digital Tap AI as a library — including the Cluster Manager."""

import asyncio

from digitaltap.agents import (
    IdleDetectionAgent,
    CostAnomalyAgent,
    RightSizingAgent,
    SchedulerAgent,
    ClusterManagerAgent,
)
from digitaltap.collectors.mock import MockCollector
from digitaltap.llm.ollama import OllamaLLM


async def main():
    # Use Ollama (falls back to rule-based if not running)
    llm = OllamaLLM(model="llama3")
    collector = MockCollector(seed=42)

    clusters = await collector.collect()
    print(f"Collected {len(clusters)} clusters\n")

    # ── Analysis agents (read-only) ──
    analysis_agents = [
        IdleDetectionAgent(llm=llm, idle_threshold_minutes=15),
        CostAnomalyAgent(llm=llm, spike_threshold=1.5),
        RightSizingAgent(llm=llm, utilization_threshold=0.3),
        SchedulerAgent(llm=llm, min_schedule_savings_pct=20),
    ]

    total_savings = 0.0
    for agent in analysis_agents:
        findings = await agent.analyze(clusters)
        print(f"--- {agent.description} ---")
        for f in findings:
            print(f"  [{f.severity.value.upper()}] {f.cluster_name}: {f.title}")
            print(f"    💰 ${f.estimated_savings_monthly:.0f}/mo")
            total_savings += f.estimated_savings_monthly
        print()

    print(f"Analysis savings: ${total_savings:,.0f}/month\n")

    # ── Cluster Manager (takes action!) ──
    print("=" * 60)
    print("CLUSTER MANAGER — DRY RUN")
    print("=" * 60)

    manager = ClusterManagerAgent(
        collector=collector,
        llm=llm,
        idle_threshold_minutes=15,
        grace_period_minutes=5,
        enforce=False,  # dry-run
        protected_clusters=["stream-processing"],
    )
    findings = await manager.analyze(clusters)
    for log in manager.action_log:
        print(f"  {log.format_line()}")
    print()

    # Now enforce
    print("=" * 60)
    print("CLUSTER MANAGER — ENFORCE MODE")
    print("=" * 60)

    collector.reset_actions()  # reset state for clean demo
    clusters = await collector.collect()  # re-collect

    manager_enforce = ClusterManagerAgent(
        collector=collector,
        llm=llm,
        idle_threshold_minutes=15,
        grace_period_minutes=0,
        enforce=True,
        protected_clusters=["stream-processing"],
    )
    findings = await manager_enforce.analyze(clusters)
    for log in manager_enforce.action_log:
        print(f"  {log.format_line()}")

    acted = [l for l in manager_enforce.action_log if l.status.value == "success"]
    savings = sum(l.savings_per_hour for l in acted)
    print(f"\n  ✅ {len(acted)} clusters hibernated — saving ${savings:.2f}/hr")
    print(f"  Collector action log: {collector.get_action_log()}")


if __name__ == "__main__":
    asyncio.run(main())
