"""OpenAI-compatible client wrapper: retries, truncation handling, SQLite cache, usage stats."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from .config import EndpointConfig
from .findings import Finding, ParsedResult, parse_model_output

DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.0


@dataclass
class QueryStats:
    queries: int = 0
    cache_hits: int = 0
    ok: int = 0
    parse_errors: int = 0
    api_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        p50 = p95 = 0.0
        if self.latencies:
            s = sorted(self.latencies)
            p50 = s[len(s) // 2]
            p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
        return (
            f"queries={self.queries} cache_hits={self.cache_hits} "
            f"ok={self.ok} parse_errors={self.parse_errors} api_errors={self.api_errors} "
            f"tokens={self.prompt_tokens + self.completion_tokens} "
            f"(prompt={self.prompt_tokens} completion={self.completion_tokens}) "
            f"latency_p50={p50:.2f}s p95={p95:.2f}s"
        )


@dataclass
class QueryResult:
    parsed: ParsedResult
    cache_hit: bool = False
    latency: float = 0.0
    error: str | None = None  # set when the query ultimately failed

    @property
    def findings(self) -> list[Finding]:
        return self.parsed.findings


def _transient(exc: Exception) -> bool:
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return False


class LLMClient:
    """Thread-safe query client. One instance can be shared across workers."""

    def __init__(
        self,
        cfg: EndpointConfig,
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        cache_path: str | None = None,
    ) -> None:
        self.cfg = cfg
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.stats = QueryStats()
        self._client = OpenAI(base_url=cfg.base_url, api_key=cfg.api_key, timeout=timeout)
        self._cache_path = cache_path
        self._cache_lock = threading.Lock()
        self._cache: sqlite3.Connection | None = None
        if cache_path:
            self._cache = sqlite3.connect(cache_path, check_same_thread=False)
            self._cache.execute(
                "CREATE TABLE IF NOT EXISTS responses "
                "(key TEXT PRIMARY KEY, json TEXT NOT NULL, created_at REAL DEFAULT (strftime('%s','now')))"
            )
            self._cache.commit()

    def close(self) -> None:
        if self._cache is not None:
            self._cache.close()
            self._cache = None

    def _cache_key(self, system: str, user: str) -> str:
        h = hashlib.sha256()
        for part in (self.cfg.base_url, self.cfg.model, system, user):
            h.update(part.encode("utf-8", "replace"))
            h.update(b"\x00")
        return h.hexdigest()

    def _cache_get(self, key: str) -> str | None:
        if self._cache is None:
            return None
        with self._cache_lock:
            row = self._cache.execute("SELECT json FROM responses WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def _cache_put(self, key: str, raw: str) -> None:
        if self._cache is None:
            return
        with self._cache_lock:
            self._cache.execute(
                "INSERT OR REPLACE INTO responses (key, json) VALUES (?, ?)", (key, json.dumps(raw))
            )
            self._cache.commit()

    def analyze(self, system: str, user: str) -> QueryResult:
        """Query the endpoint; retries transient failures, never raises."""
        key = self._cache_key(system, user)
        cached = self._cache_get(key)
        if cached is not None:
            self.stats.cache_hits += 1
            return QueryResult(parsed=parse_model_output(json.loads(cached)), cache_hit=True)

        self.stats.queries += 1
        max_tokens = self.max_tokens
        # One extra attempt is reserved for length-truncated replies.
        total_attempts = self.max_retries + 2
        last_error: str | None = None
        for attempt in range(total_attempts):
            started = time.monotonic()
            try:
                response = self._client.chat.completions.create(
                    model=self.cfg.model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=DEFAULT_TEMPERATURE,
                    max_tokens=max_tokens,
                )
            except Exception as e:  # noqa: BLE001 — we classify below
                last_error = f"{type(e).__name__}: {e}"
                if _transient(e) and attempt < total_attempts - 1:
                    time.sleep(min(30.0, (2**attempt) + random.random()))
                    continue
                break

            latency = time.monotonic() - started
            self.stats.latencies.append(latency)
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.stats.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.stats.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

            raw = (response.choices[0].message.content or "").strip()
            finish = response.choices[0].finish_reason
            if finish == "length" and attempt < total_attempts - 1:
                # Truncated JSON — retry once with a larger budget.
                last_error = "truncated (finish_reason=length), retrying with larger max_tokens"
                max_tokens *= 2
                continue

            parsed = parse_model_output(raw)
            if parsed.warnings and all("no JSON" in w or "invalid JSON" in w for w in parsed.warnings):
                self.stats.parse_errors += 1
            else:
                self.stats.ok += 1
            self._cache_put(key, raw)
            return QueryResult(parsed=parsed, latency=latency)

        self.stats.api_errors += 1
        self.stats.errors.append(last_error or "unknown error")
        return QueryResult(parsed=ParsedResult(warnings=["query failed"]), error=last_error)
