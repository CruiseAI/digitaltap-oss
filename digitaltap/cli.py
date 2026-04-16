"""CLI interface for Digital Tap AI."""

from __future__ import annotations

import asyncio
import time
import uuid

import click
from rich.console import Console

from digitaltap import __version__
from digitaltap.agents import (
    ClusterManagerAgent,
    CostAnomalyAgent,
    IdleDetectionAgent,
    RightSizingAgent,
    SchedulerAgent,
)
from digitaltap.collectors.mock import MockCollector
from digitaltap.config import Config
from digitaltap.llm.base import NoLLM
from digitaltap.llm.ollama import OllamaLLM
from digitaltap.models.metrics import Finding, ScanReport, Severity

console = Console()

# Scan-only agents (analysis, no side-effects)
SCAN_AGENT_MAP = {
    "idle-detection": IdleDetectionAgent,
    "cost-anomaly": CostAnomalyAgent,
    "right-sizing": RightSizingAgent,
    "scheduler": SchedulerAgent,
}

SEVERITY_ICONS = {
    Severity.CRITICAL: "🚨",
    Severity.HIGH: "⚠️ ",
    Severity.MEDIUM: "⚠️ ",
    Severity.LOW: "💡",
    Severity.INFO: "ℹ️ ",
}

AGENT_ICONS = {
    "idle_detection": "🔍",
    "cost_anomaly": "📊",
    "right_sizing": "📐",
    "scheduler": "🕐",
    "cluster_manager": "⚡",
}


def _get_collector(config: Config, demo: bool):
    if demo or config.collector == "mock":
        return MockCollector(seed=42)
    elif config.collector == "databricks":
        from digitaltap.collectors.databricks import DatabricksCollector
        return DatabricksCollector(**config.collector_options)
    elif config.collector == "aws":
        from digitaltap.collectors.aws import AWSCollector
        return AWSCollector(**config.collector_options)
    else:
        console.print(f"[red]Unknown collector: {config.collector}[/red]")
        raise SystemExit(1)


def _get_llm(config: Config):
    if config.llm.provider == "ollama":
        return OllamaLLM(
            model=config.llm.model,
            base_url=config.llm.base_url,
            timeout=config.llm.timeout,
        )
    return NoLLM()


def _print_header():
    console.print()
    console.print("[bold magenta]🔮 Digital Tap AI — Open Source Edition[/bold magenta]")
    console.print("━" * 50)


async def _collect_and_init(config: Config, demo: bool):
    """Shared setup: collect clusters, init LLM."""
    collector = _get_collector(config, demo)
    mode_label = "mock" if demo or config.collector == "mock" else config.collector
    console.print(f"\n📡 Collecting cluster data ({mode_label} mode)...")
    clusters = await collector.collect()
    console.print(f"   Found [bold]{len(clusters)}[/bold] clusters")

    llm = _get_llm(config)
    llm_ok = await llm.is_available()
    if llm_ok:
        console.print(f"   🧠 LLM: {config.llm.model} via {config.llm.provider}")
    else:
        console.print("   🧠 LLM: not available (using rule-based analysis)")

    return collector, clusters, llm, mode_label


# ── scan command ──────────────────────────────────────────────────────────────

async def _run_scan(config: Config, demo: bool, agent_filter: str | None, output: str):
    start = time.time()
    _print_header()

    collector, clusters, llm, mode_label = await _collect_and_init(config, demo)

    # Build agents
    agents_to_run = []
    for key, cls in SCAN_AGENT_MAP.items():
        if agent_filter and key != agent_filter:
            continue
        settings = config.agents.get(cls.name, None)
        if settings and not settings.enabled:
            continue
        opts = settings.options if settings else {}
        agents_to_run.append(cls(llm=llm, **opts))

    report = ScanReport(
        scan_id=str(uuid.uuid4())[:8],
        collector=mode_label,
        clusters_scanned=len(clusters),
    )
    report.total_current_monthly_spend = sum(c.hourly_cost_usd for c in clusters) * 720

    for agent in agents_to_run:
        icon = AGENT_ICONS.get(agent.name, "🔧")
        console.print(f"\n{icon} [bold]{agent.description}[/bold]")

        findings = await agent.analyze(clusters)
        report.findings.extend(findings)

        if not findings:
            console.print("   ✅ No issues found")
        else:
            for f in findings:
                sev_icon = SEVERITY_ICONS.get(f.severity, "")
                console.print(f"   {sev_icon} [bold]{f.cluster_name}[/bold] — {f.title}")
                if f.recommendation:
                    short = f.recommendation[:120] + ("..." if len(f.recommendation) > 120 else "")
                    console.print(f"      → {short}")

            agent_savings = sum(f.estimated_savings_monthly for f in findings)
            console.print(f"   ✅ {len(findings)} finding(s) — ${agent_savings:,.0f}/mo potential savings")

    report.compute_totals()
    report.duration_seconds = time.time() - start

    console.print()
    console.print("━" * 50)
    console.print(
        f"[bold green]💰 Total potential savings: "
        f"${report.total_monthly_savings:,.0f}/month "
        f"({report.savings_percentage:.0f}% of "
        f"${report.total_current_monthly_spend:,.0f}/mo spend)[/bold green]"
    )
    console.print(f"   Scanned {report.clusters_scanned} clusters in {report.duration_seconds:.1f}s")
    console.print()

    if output == "json":
        console.print_json(report.model_dump_json(indent=2))


# ── manage command ────────────────────────────────────────────────────────────

async def _run_manage(config: Config, demo: bool, enforce: bool, output: str):
    start = time.time()
    _print_header()

    collector, clusters, llm, mode_label = await _collect_and_init(config, demo)

    mode_str = "[bold red]ENFORCE[/bold red]" if enforce else "[bold yellow]DRY-RUN[/bold yellow]"
    console.print(f"   ⚡ Mode: {mode_str}")

    # Build manager agent with collector reference for actions
    settings = config.agents.get("cluster_manager", None)
    opts = dict(settings.options) if settings else {}
    opts["enforce"] = enforce

    manager = ClusterManagerAgent(collector=collector, llm=llm, **opts)

    console.print(f"\n⚡ [bold]{manager.description}[/bold]")

    # Policy summary
    console.print(f"   Policy: idle ≥ {manager.idle_threshold_minutes}m, "
                  f"CPU < {manager.cpu_threshold*100:.0f}%, "
                  f"grace {manager.grace_period_minutes}m, "
                  f"action: {manager.default_action}")
    if manager.protected_clusters:
        console.print(f"   Protected clusters: {', '.join(manager.protected_clusters)}")
    console.print()

    findings = await manager.analyze(clusters)

    # Print action log (the detailed play-by-play)
    if manager.action_log:
        console.print("   [bold]Action Log:[/bold]")
        for log in manager.action_log:
            console.print(log.format_line())
        console.print()

    # Summary
    acted = [l for l in manager.action_log if l.status.value == "success"]
    dry_run = [l for l in manager.action_log if l.status.value == "dry_run"]
    skipped = [l for l in manager.action_log if l.status.value == "skipped"]
    failed = [l for l in manager.action_log if l.status.value == "failed"]

    savings_hr = sum(l.savings_per_hour for l in (acted or dry_run))

    if acted:
        console.print(
            f"   [bold green]✅ {len(acted)} cluster(s) {manager.default_action}d — "
            f"saving ${savings_hr:.2f}/hr (${savings_hr * 720:,.0f}/mo)[/bold green]"
        )
    elif dry_run:
        console.print(
            f"   [bold yellow]🔍 {len(dry_run)} cluster(s) would be {manager.default_action}d — "
            f"${savings_hr:.2f}/hr (${savings_hr * 720:,.0f}/mo)[/bold yellow]"
        )
        console.print(
            f"   [dim]Run with --enforce to take action[/dim]"
        )

    if skipped:
        console.print(f"   ⏭️  {len(skipped)} cluster(s) skipped (protected/grace period)")
    if failed:
        console.print(f"   ❌ {len(failed)} action(s) failed")

    duration = time.time() - start
    console.print()
    console.print("━" * 50)
    console.print(f"   Evaluated {len(clusters)} clusters in {duration:.1f}s")
    console.print()

    if output == "json":
        import json
        data = {
            "mode": "enforce" if enforce else "dry_run",
            "actions": [l.model_dump(mode="json") for l in manager.action_log],
            "findings": [f.model_dump(mode="json") for f in findings],
            "summary": {
                "acted": len(acted),
                "dry_run": len(dry_run),
                "skipped": len(skipped),
                "failed": len(failed),
                "savings_per_hour": savings_hr,
                "savings_monthly": savings_hr * 720,
            },
        }
        console.print_json(json.dumps(data, indent=2, default=str))


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__)
def main():
    """Digital Tap AI — Save 40%+ on cloud compute with local AI agents."""
    pass


@main.command()
@click.option("--demo", is_flag=True, help="Use mock data (no credentials needed)")
@click.option("--agent", type=click.Choice(list(SCAN_AGENT_MAP.keys())), help="Run specific agent")
@click.option("--config", "config_path", type=click.Path(), help="Config file path")
@click.option("--output", type=click.Choice(["rich", "json"]), default="rich")
@click.option("--model", help="Ollama model to use (e.g. llama3, mistral)")
def scan(demo: bool, agent: str | None, config_path: str | None, output: str, model: str | None):
    """Scan clusters and find optimization opportunities."""
    config = Config.load(config_path)
    if model:
        config.llm.model = model
    asyncio.run(_run_scan(config, demo, agent, output))


@main.command()
@click.option("--demo", is_flag=True, help="Use mock data (no credentials needed)")
@click.option("--enforce", is_flag=True,
              help="Actually stop/hibernate clusters (default: dry-run)")
@click.option("--config", "config_path", type=click.Path(), help="Config file path")
@click.option("--output", type=click.Choice(["rich", "json"]), default="rich")
@click.option("--model", help="Ollama model to use")
@click.option("--idle-threshold", type=float, help="Idle minutes before action (default: 15)")
@click.option("--cpu-threshold", type=float, help="CPU % below which cluster is idle (default: 5)")
@click.option("--grace-period", type=float, help="Extra grace minutes (default: 5)")
@click.option("--action", type=click.Choice(["hibernate", "stop"]), help="Action to take (default: hibernate)")
@click.option("--protect", multiple=True, help="Cluster names to never touch (repeatable)")
def manage(
    demo: bool,
    enforce: bool,
    config_path: str | None,
    output: str,
    model: str | None,
    idle_threshold: float | None,
    cpu_threshold: float | None,
    grace_period: float | None,
    action: str | None,
    protect: tuple,
):
    """Manage idle clusters — detect and stop/hibernate them.

    \b
    Default: DRY-RUN mode (shows what would happen).
    Use --enforce to actually take action.

    \b
    Examples:
      digitaltap manage --demo                          # dry-run with mock data
      digitaltap manage --demo --enforce                # enforce with mock data
      digitaltap manage --demo --idle-threshold 30      # custom threshold
      digitaltap manage --demo --protect stream-processing --protect ml-inference-api
    """
    config = Config.load(config_path)
    if model:
        config.llm.model = model

    # CLI overrides for manager settings
    mgr_settings = config.agents.get("cluster_manager")
    if mgr_settings:
        if idle_threshold is not None:
            mgr_settings.options["idle_threshold_minutes"] = idle_threshold
        if cpu_threshold is not None:
            mgr_settings.options["cpu_threshold"] = cpu_threshold / 100.0
        if grace_period is not None:
            mgr_settings.options["grace_period_minutes"] = grace_period
        if action is not None:
            mgr_settings.options["default_action"] = action
        if protect:
            existing = mgr_settings.options.get("protected_clusters", [])
            mgr_settings.options["protected_clusters"] = list(existing) + list(protect)

    asyncio.run(_run_manage(config, demo, enforce, output))


@main.command()
@click.option("--demo", is_flag=True, help="Use mock data")
@click.option("--config", "config_path", type=click.Path(), help="Config file path")
@click.option("--model", help="Ollama model to use")
def report(demo: bool, config_path: str | None, model: str | None):
    """Generate a detailed savings report."""
    config = Config.load(config_path)
    if model:
        config.llm.model = model
    asyncio.run(_run_scan(config, demo, None, "rich"))


if __name__ == "__main__":
    main()
