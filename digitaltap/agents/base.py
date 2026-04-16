"""Base agent class for Digital Tap AI agents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from digitaltap.llm.base import BaseLLM, NoLLM
from digitaltap.models.cluster import ClusterInfo
from digitaltap.models.metrics import Finding


class BaseAgent(ABC):
    """Base class for all analysis agents."""

    name: str = "base"
    description: str = ""

    def __init__(self, llm: BaseLLM | None = None, **options):
        self.llm = llm or NoLLM()
        self.options = options

    @abstractmethod
    async def analyze(self, clusters: list[ClusterInfo]) -> list[Finding]:
        """Analyze clusters and return findings."""
        ...

    async def _llm_analyze(self, prompt: str) -> str:
        """Run LLM analysis with graceful fallback."""
        try:
            if await self.llm.is_available():
                return await self.llm.generate(
                    prompt,
                    system=(
                        "You are a cloud infrastructure cost optimization expert. "
                        "Analyze the data and provide concise, actionable recommendations. "
                        "Be specific about potential savings in dollar amounts."
                    ),
                )
        except Exception:
            pass
        return ""
