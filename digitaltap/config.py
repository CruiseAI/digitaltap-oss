"""Configuration management for Digital Tap AI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "llama3"
    base_url: str = "http://localhost:11434"
    timeout: float = 120.0


@dataclass
class AgentSettings:
    enabled: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    llm: LLMConfig = field(default_factory=LLMConfig)
    collector: str = "mock"
    collector_options: dict[str, Any] = field(default_factory=dict)
    agents: dict[str, AgentSettings] = field(default_factory=lambda: {
        "idle_detection": AgentSettings(options={"idle_threshold_minutes": 15}),
        "cost_anomaly": AgentSettings(options={"spike_threshold": 1.5}),
        "right_sizing": AgentSettings(options={"utilization_threshold": 0.3}),
        "scheduler": AgentSettings(options={"min_schedule_savings_pct": 20}),
        "cluster_manager": AgentSettings(options={
            "idle_threshold_minutes": 15,
            "cpu_threshold": 0.05,
            "grace_period_minutes": 5,
            "default_action": "hibernate",
            "enforce": False,
            "protected_clusters": [],
            "protected_tags": {"protected": "true"},
            "protected_workspaces": [],
        }),
    })
    output_format: str = "rich"  # rich | json | text

    @classmethod
    def load(cls, path: str | Path | None = None) -> Config:
        """Load config from YAML file, env vars, or defaults."""
        config = cls()

        # Try config file
        if path is None:
            for candidate in ["digitaltap.yaml", "digitaltap.yml", ".digitaltap.yaml"]:
                if Path(candidate).exists():
                    path = candidate
                    break

        if path and Path(path).exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

            if "llm" in data:
                llm = data["llm"]
                config.llm = LLMConfig(
                    provider=llm.get("provider", config.llm.provider),
                    model=llm.get("model", config.llm.model),
                    base_url=llm.get("base_url", config.llm.base_url),
                    timeout=llm.get("timeout", config.llm.timeout),
                )

            if "collector" in data:
                c = data["collector"]
                if isinstance(c, str):
                    config.collector = c
                elif isinstance(c, dict):
                    config.collector = c.get("type", "mock")
                    config.collector_options = {k: v for k, v in c.items() if k != "type"}

            if "agents" in data:
                for name, settings in data["agents"].items():
                    if isinstance(settings, dict):
                        config.agents[name] = AgentSettings(
                            enabled=settings.get("enabled", True),
                            options={k: v for k, v in settings.items() if k != "enabled"},
                        )

        # Env var overrides
        if url := os.environ.get("OLLAMA_BASE_URL"):
            config.llm.base_url = url
        if model := os.environ.get("DIGITALTAP_MODEL"):
            config.llm.model = model

        return config
