# 🔮 Digital Tap AI — Open Source Edition

**Save 40%+ on cloud compute with local AI agents. No API keys. No cloud dependencies. Runs entirely on your machine.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-purple.svg)](https://ollama.ai)

<!-- ![Demo](docs/demo.gif) -->

---

## What is this?

Digital Tap AI agents continuously analyze your cloud compute infrastructure and find waste — idle clusters burning money, oversized instances, cost anomalies, and scheduling opportunities.

**This open-source edition** includes 5 agents that work with any local LLM via [Ollama](https://ollama.ai). No cloud API keys required. No data leaves your machine.

| Agent | What it does | Typical savings |
|-------|-------------|-----------------|
| 🔍 **Idle Detection** | Finds clusters running with no workload | 20-35% |
| ⚡ **Cluster Manager** | **Automatically hibernates/stops idle clusters** | 20-40% |
| 📊 **Cost Anomaly** | Detects unexpected spend spikes | 5-15% |
| 📐 **Right-Sizing** | Recommends optimal instance types | 10-25% |
| 🕐 **Scheduler** | Suggests start/stop schedules based on usage patterns | 15-30% |

> ⚡ **The Cluster Manager doesn't just detect — it acts.** Dry-run by default, one flag to enforce. Configurable policies, grace periods, exclusion lists.

> **Want the full platform?** [digitaltap.ai](https://digitaltap.ai) adds multi-cloud support, team dashboards, Slack/Teams alerts, and more.

---

## Quick Start

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Pull a model (llama3 recommended, mistral also works great)
ollama pull llama3
```

### 2. Install Digital Tap AI

```bash
pip install digitaltap-ai

# Or from source:
git clone https://github.com/CruiseAI/digitaltap-oss.git
cd digitaltap-ai-oss
pip install -e .
```

### 3. Run the demo

```bash
# Scan: analyze all clusters (read-only)
digitaltap scan --demo

# Manage: detect AND act on idle clusters (dry-run by default)
digitaltap manage --demo

# Manage: actually hibernate idle clusters
digitaltap manage --demo --enforce

# Manage with custom policy
digitaltap manage --demo --enforce \
  --idle-threshold 30 \
  --grace-period 10 \
  --protect stream-processing \
  --protect ml-inference-api
```

#### `digitaltap manage --demo` (dry-run)

```
🔮 Digital Tap AI — Open Source Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📡 Collecting cluster data (mock mode)...
   Found 12 clusters
   ⚡ Mode: DRY-RUN

⚡ Detects idle clusters and automatically hibernates/stops them
   Policy: idle ≥ 15m, CPU < 5%, grace 5m, action: hibernate

   Action Log:
   🔍 16:29:51 [DRY_RUN] etl-pipeline-prod — idle 126m (threshold: 15m)
   🔍 16:29:51 [DRY_RUN] dev-sandbox-team-b — idle 146m (threshold: 15m)
   🔍 16:29:51 [DRY_RUN] staging-analytics — idle 51m (threshold: 15m)
   🔍 16:29:51 [DRY_RUN] ad-hoc-queries — idle 34m (threshold: 15m)
   🔍 16:29:51 [DRY_RUN] data-quality-checks — idle 44m (threshold: 15m)

   🔍 5 cluster(s) would be hibernated — $18.95/hr ($13,644/mo)
   Run with --enforce to take action
```

#### `digitaltap manage --demo --enforce` (takes action)

```
   Action Log:
   ✅ 16:29:54 [SUCCESS] etl-pipeline-prod — Hibernated
   ✅ 16:29:54 [SUCCESS] dev-sandbox-team-b — Hibernated
   ✅ 16:29:54 [SUCCESS] staging-analytics — Hibernated
   ✅ 16:29:54 [SUCCESS] ad-hoc-queries — Hibernated
   ✅ 16:29:54 [SUCCESS] data-quality-checks — Hibernated

   ✅ 5 cluster(s) hibernated — saving $18.95/hr ($13,644/mo)
```

#### `digitaltap scan --demo` (full analysis)

```
🔮 Digital Tap AI — Open Source Edition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 Idle Detection Agent
   🚨 etl-pipeline-prod — idle 126 min ($5.74/hr)
   🚨 dev-sandbox-team-b — idle 146 min ($1.61/hr)
   ⚠️  staging-analytics — idle 51 min ($2.76/hr)

📊 Cost Anomaly Agent
   🚨 ml-training-gpu — cost spike 445% above baseline

📐 Right-Sizing Agent
   ⚠️  reporting-cluster — 16 workers at 7% util → 1 worker

🕐 Scheduler Agent
   📅 dev-sandbox-team-b — only used Mon-Fri → schedule saves $207/week

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 Total potential savings: $1,847/month
```

---

## Docker

```bash
# Start Ollama + Digital Tap AI
docker compose up

# Or just Digital Tap AI (if Ollama is already running)
docker compose up digitaltap
```

---

## Connect Real Infrastructure

### Databricks

```bash
export DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
export DATABRICKS_TOKEN=dapi...

digitaltap scan --collector databricks
```

### AWS EMR

```bash
# Uses standard AWS credentials (AWS_PROFILE, AWS_ACCESS_KEY_ID, etc.)
digitaltap scan --collector aws
```

### Custom Collector

```python
from digitaltap.collectors.base import BaseCollector
from digitaltap.models.cluster import ClusterInfo

class MyCollector(BaseCollector):
    async def collect(self) -> list[ClusterInfo]:
        # Fetch your cluster data
        return [ClusterInfo(id="c1", name="my-cluster", ...)]
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                  CLI / API                   │
├─────────────────────────────────────────────┤
│              Agent Orchestrator              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │  Idle    │ │  Cost    │ │  Right-  │    │
│  │Detection │ │ Anomaly  │ │  Sizing  │ ...│
│  └────┬─────┘ └────┬─────┘ └────┬─────┘    │
│       └─────────────┼───────────┘           │
│              ┌──────┴──────┐                │
│              │  Local LLM  │                │
│              │  (Ollama)   │                │
│              └─────────────┘                │
├─────────────────────────────────────────────┤
│              Data Collectors                 │
│  ┌──────┐ ┌───────────┐ ┌─────┐ ┌──────┐  │
│  │ Mock │ │Databricks │ │ AWS │ │Custom│  │
│  └──────┘ └───────────┘ └─────┘ └──────┘  │
└─────────────────────────────────────────────┘
```

**Two modes:**
- `digitaltap scan` — **read-only** analysis across all agents
- `digitaltap manage` — **detect and act** on idle clusters (dry-run default, `--enforce` to act)

Each agent:
1. **Collects** cluster metrics via pluggable collectors
2. **Analyzes** data using rules + LLM reasoning
3. **Recommends** specific actions with estimated savings
4. **Acts** (Cluster Manager only) — hibernates/stops clusters with full audit log

The Cluster Manager uses a policy engine with configurable thresholds, grace periods, and exclusion lists. Every action is logged with timestamp and reason — nothing happens silently.

The LLM is used for nuanced analysis — understanding workload patterns, generating natural-language explanations, and making judgment calls that pure threshold-based rules miss. **All agents work without an LLM** (rule-based fallback), the LLM just makes recommendations smarter.

---

## Configuration

```yaml
# digitaltap.yaml
llm:
  provider: ollama
  model: llama3           # or mistral, codellama, etc.
  base_url: http://localhost:11434

agents:
  idle_detection:
    enabled: true
    idle_threshold_minutes: 15
  cluster_manager:
    enabled: true
    idle_threshold_minutes: 15   # idle time before action
    cpu_threshold: 0.05          # CPU % below which cluster is "idle"
    grace_period_minutes: 5      # extra buffer after threshold
    default_action: hibernate    # hibernate | stop
    enforce: false               # true = take action, false = dry-run
    protected_clusters:          # never touch these
      - stream-processing
      - ml-inference-api
    protected_tags:
      protected: "true"          # skip clusters with this tag
    protected_workspaces: []     # skip entire workspaces
  cost_anomaly:
    enabled: true
    spike_threshold: 1.5         # 50% above baseline
  right_sizing:
    enabled: true
    utilization_threshold: 0.3
  scheduler:
    enabled: true
    min_schedule_savings_pct: 20

collector:
  type: mock              # mock | databricks | aws
```

---

## Use as a Library

```python
import asyncio
from digitaltap.agents import IdleDetectionAgent, CostAnomalyAgent
from digitaltap.collectors.mock import MockCollector
from digitaltap.llm.ollama import OllamaLLM

async def main():
    llm = OllamaLLM(model="llama3")
    collector = MockCollector()
    clusters = await collector.collect()

    agent = IdleDetectionAgent(llm=llm)
    findings = await agent.analyze(clusters)

    for f in findings:
        print(f"{f.severity}: {f.cluster_name} — {f.recommendation}")
        print(f"  Estimated savings: ${f.estimated_savings_per_hour:.2f}/hr")

asyncio.run(main())
```

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) (coming soon).

Areas we'd love help with:
- Additional collectors (GCP Dataproc, Azure HDInsight, Kubernetes)
- More agent strategies (spot instance optimization, reserved capacity planning)
- Dashboard UI
- Prometheus/Grafana integration
- Better LLM prompts for analysis

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

## Full Platform

This is the open-source core. **[Digital Tap AI](https://digitaltap.ai)** (the full platform) adds:

- ⚡ **Auto-remediation** — automatically hibernate, resize, and schedule
- 🌐 **Multi-cloud** — Databricks, EMR, Dataproc, Synapse, and more
- 👥 **Team dashboards** — per-team cost attribution and savings tracking
- 🔔 **Alerts** — Slack, Teams, PagerDuty, email
- 📈 **Historical analytics** — trend analysis and forecasting
- 🔒 **Enterprise features** — SSO, RBAC, audit logs, SOC2

→ [digitaltap.ai](https://digitaltap.ai)
