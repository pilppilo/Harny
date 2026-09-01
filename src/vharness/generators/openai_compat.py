"""OpenAI-compatible HTTP generator: retry, truncation retry, SQLite cache, usage stats."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import threading
import time

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from ..config import EndpointConfig
from ..core import Generation
from .base import Generator, register_builtin

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0


def _transient(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


@register_builtin
class OpenAICompatible(Generator):
    name = "openai"
    help = "any OpenAI-compatible chat-completions endpoint (Ollama, vLLM, llama.cpp, hosted APIs, …)"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "no-key",
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        cache_path: str | None = None,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.stats = {
            "queries": 0, "cache_hits": 0, "api_errors": 0, "parse_notice": 0,
            "prompt_tokens": 0, "completion_tokens": 0, "latencies": [],
        }
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
        self._cache_path = cache_path
        self._cache_lock = threading.Lock()
        self._cache: sqlite3.Connection | None = None
        if cache_path:
            self._cache = sqlite3.connect(cache_path, check_same_thread=False)
            self._cache.execute(
                "CREATE TABLE IF NOT EXISTS responses "
                "(key TEXT PRIMARY KEY, text TEXT NOT NULL, created_at REAL DEFAULT (strftime('%s','now')))"
            )
            self._cache.commit()

    @classmethod
    def from_config(cls, cfg: EndpointConfig, **kwargs) -> "OpenAICompatible":
        return cls(cfg.base_url, cfg.model, cfg.api_key, **kwargs)

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()
            self._cache = None

    def _cache_key(self, system: str, prompt: str) -> str:
        h = hashlib.sha256()
        for part in (self.model, system, prompt):
            h.update(part.encode("utf-8", "replace"))
            h.update(b"\x00")
        return h.hexdigest()

    def _cache_get(self, key: str) -> str | None:
        if self._cache is None:
            return None
        with self._cache_lock:
            row = self._cache.execute("SELECT text FROM responses WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _cache_put(self, key: str, text: str) -> None:
        if self._cache is None:
            return
        with self._cache_lock:
            self._cache.execute(
                "INSERT OR REPLACE INTO responses (key, text) VALUES (?, ?)", (key, text)
            )
            self._cache.commit()

    def summary(self) -> str:
        s = self.stats
        lat = s["latencies"]
        p50 = sorted(lat)[len(lat) // 2] if lat else 0.0
        return (
            f"queries={s['queries']} cache_hits={s['cache_hits']} api_errors={s['api_errors']} "
            f"tokens={s['prompt_tokens'] + s['completion_tokens']} latency_p50={p50:.2f}s"
        )

    def generate(self, system: str, prompt: str) -> Generation:
        key = self._cache_key(system, prompt)
        cached = self._cache_get(key)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return Generation(text=cached, model=self.model, cached=True)

        self.stats["queries"] += 1
        max_tokens = self.max_tokens
        # One extra attempt is reserved for length-truncated replies.
        total_attempts = self.max_retries + 2
        last_error: str | None = None
        for attempt in range(total_attempts):
            started = time.monotonic()
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self.temperature,
                    max_tokens=max_tokens,
                )
            except Exception as e:  # noqa: BLE001 — classified below
                last_error = f"{type(e).__name__}: {e}"
                if _transient(e) and attempt < total_attempts - 1:
                    time.sleep(min(30.0, (2**attempt) + random.random()))
                    continue
                break

            latency = time.monotonic() - started
            with self._cache_lock:
                self.stats["latencies"].append(latency)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    self.stats["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
                    self.stats["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0

            raw = (response.choices[0].message.content or "").strip()
            finish = response.choices[0].finish_reason
            if finish == "length" and attempt < total_attempts - 1:
                # Truncated JSON — retry with a bigger budget before giving up.
                last_error = "truncated (finish_reason=length); retried with larger max_tokens"
                max_tokens *= 2
                continue

            self._cache_put(key, raw)
            return Generation(text=raw, model=self.model, finish_reason=finish, latency=latency)

        self.stats["api_errors"] += 1
        return Generation(text="", model=self.model, error=last_error)
