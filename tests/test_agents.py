"""Tests for Digital Tap AI agents."""

import asyncio
import pytest

from digitaltap.agents import (
    IdleDetectionAgent,
    CostAnomalyAgent,
    RightSizingAgent,
    SchedulerAgent,
    ClusterManagerAgent,
)
from digitaltap.collectors.mock import MockCollector
from digitaltap.models.metrics import ActionStatus


@pytest.fixture
def clusters():
    return asyncio.get_event_loop().run_until_complete(MockCollector(seed=42).collect())


@pytest.fixture
def collector():
    return MockCollector(seed=42)


def test_idle_detection(clusters):
    agent = IdleDetectionAgent(idle_threshold_minutes=15)
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(findings) > 0
    for f in findings:
        assert f.agent == "idle_detection"
        assert f.estimated_savings_per_hour > 0
        assert f.evidence["idle_minutes"] >= 15


def test_cost_anomaly(clusters):
    agent = CostAnomalyAgent(spike_threshold=1.5)
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(findings) > 0
    for f in findings:
        assert f.agent == "cost_anomaly"
        assert f.evidence["increase_pct"] > 0


def test_right_sizing(clusters):
    agent = RightSizingAgent(utilization_threshold=0.3)
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(findings) > 0
    for f in findings:
        assert f.agent == "right_sizing"
        assert f.evidence["recommended_workers"] < f.evidence["current_workers"]


def test_scheduler(clusters):
    agent = SchedulerAgent(min_schedule_savings_pct=20)
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(findings) > 0
    for f in findings:
        assert f.agent == "scheduler"
        assert f.evidence["savings_pct"] >= 20


def test_mock_collector_deterministic():
    c1 = asyncio.get_event_loop().run_until_complete(MockCollector(seed=42).collect())
    c2 = asyncio.get_event_loop().run_until_complete(MockCollector(seed=42).collect())
    assert len(c1) == len(c2)
    assert c1[0].name == c2[0].name


# ── Cluster Manager tests ────────────────────────────────────────────────────

def test_cluster_manager_dry_run(clusters, collector):
    agent = ClusterManagerAgent(
        collector=collector, idle_threshold_minutes=15, enforce=False
    )
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(findings) > 0
    for f in findings:
        assert f.agent == "cluster_manager"
        # In dry-run mode, nothing should actually be stopped
        assert f.evidence["action_status"] in ("dry_run", "skipped")
    # Collector should have no stopped clusters
    assert len(collector._stopped) == 0


def test_cluster_manager_enforce(collector):
    clusters = asyncio.get_event_loop().run_until_complete(collector.collect())
    agent = ClusterManagerAgent(
        collector=collector, idle_threshold_minutes=15, grace_period_minutes=0, enforce=True
    )
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    acted = [f for f in findings if f.evidence.get("action_status") == "success"]
    assert len(acted) > 0, "Should have hibernated at least one cluster"
    assert len(collector._stopped) > 0, "Collector should track stopped clusters"


def test_cluster_manager_protected_clusters(collector):
    clusters = asyncio.get_event_loop().run_until_complete(collector.collect())
    idle_names = [c.name for c in clusters if c.idle_minutes >= 15]
    assert len(idle_names) > 0

    agent = ClusterManagerAgent(
        collector=collector,
        idle_threshold_minutes=15,
        grace_period_minutes=0,
        enforce=True,
        protected_clusters=idle_names,  # protect ALL idle clusters
    )
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    # Nothing should have been acted on
    assert len(collector._stopped) == 0
    skipped = [l for l in agent.action_log if l.status == ActionStatus.SKIPPED]
    assert len(skipped) >= len(idle_names)


def test_cluster_manager_grace_period(collector):
    clusters = asyncio.get_event_loop().run_until_complete(collector.collect())
    # Set grace period so high nothing triggers
    agent = ClusterManagerAgent(
        collector=collector,
        idle_threshold_minutes=15,
        grace_period_minutes=9999,
        enforce=True,
    )
    findings = asyncio.get_event_loop().run_until_complete(agent.analyze(clusters))
    assert len(collector._stopped) == 0, "Grace period should prevent all actions"


def test_mock_collector_actions():
    collector = MockCollector(seed=42)
    loop = asyncio.get_event_loop()
    assert loop.run_until_complete(collector.stop_cluster("cluster-test")) is True
    assert "cluster-test" in collector._stopped
    assert collector._stopped["cluster-test"] == "stopped"

    assert loop.run_until_complete(collector.hibernate_cluster("cluster-test2")) is True
    assert collector._stopped["cluster-test2"] == "hibernated"
    assert len(collector.get_action_log()) == 2

    collector.reset_actions()
    assert len(collector._stopped) == 0
