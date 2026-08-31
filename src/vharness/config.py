"""Endpoint configuration: CLI flags > env vars, for any OpenAI-compatible server."""

from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


@dataclass
class EndpointConfig:
    base_url: str
    api_key: str
    model: str

    def describe(self) -> str:
        key = self.api_key[:4] + "…" if self.api_key else "(none)"
        return f"{self.base_url} model={self.model} key={key}"


def resolve_endpoint(
    base_url: str | None,
    api_key: str | None,
    model: str | None,
    *,
    env_prefix: str = "VHARNESS",
) -> EndpointConfig:
    """Resolve endpoint settings from args, then env (VHARNESS_*, OPENAI_API_KEY)."""
    base_url = base_url or os.environ.get(f"{env_prefix}_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    api_key = api_key or os.environ.get(f"{env_prefix}_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = model or os.environ.get(f"{env_prefix}_MODEL") or os.environ.get("OPENAI_MODEL")
    if not model:
        raise ConfigError(
            "no model name: pass --model or set VHARNESS_MODEL"
        )
    if not base_url:
        raise ConfigError(
            "no endpoint: pass --base-url or set VHARNESS_BASE_URL "
            "(any OpenAI-compatible server: Ollama, vLLM, llama.cpp, LM Studio, ...)"
        )
    if not api_key:
        # Many local servers accept any key; default rather than fail.
        api_key = "no-key"
    return EndpointConfig(base_url=base_url.rstrip("/"), api_key=api_key, model=model)
