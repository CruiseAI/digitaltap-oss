"""Base LLM interface."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseLLM(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate a completion from the LLM."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the LLM is reachable."""
        ...


class NoLLM(BaseLLM):
    """Fallback that returns empty strings — agents work without LLM, just skip analysis."""

    async def generate(self, prompt: str, system: str = "") -> str:
        return ""

    async def is_available(self) -> bool:
        return False
