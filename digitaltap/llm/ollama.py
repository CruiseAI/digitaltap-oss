"""Ollama LLM provider — connects to any local Ollama instance."""

from __future__ import annotations

import httpx

from .base import BaseLLM


class OllamaLLM(BaseLLM):
    """Talk to a local Ollama instance. Works with llama3, mistral, codellama, etc."""

    def __init__(
        self,
        model: str = "llama3",
        base_url: str = "http://localhost:11434",
        timeout: float = 120.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate a completion using Ollama's /api/generate endpoint."""
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 1024},
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/api/generate", json=payload)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                models = [m["name"].split(":")[0] for m in resp.json().get("models", [])]
                return self.model in models or any(self.model in m for m in models)
        except Exception:
            return False
