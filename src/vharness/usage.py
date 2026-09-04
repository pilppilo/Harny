"""Aggregate locally recorded model usage from Vharness JSONL run logs.

OpenAI-compatible chat-completions APIs expose per-response token counts, but
they do not define a portable account-quota endpoint. This module therefore
reports only usage that Vharness has recorded locally.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class UsageSummary:
    """Usage for one recorded provider/model pair."""

    provider: str
    model: str
    attempts: int = 0
    completed_requests: int = 0
    cache_hits: int = 0
    api_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    responses_without_usage: int = 0
    latencies: list[float] = field(default_factory=list, repr=False)
    log_files: set[str] = field(default_factory=set, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def latency_p50(self) -> float:
        values = sorted(self.latencies)
        return values[len(values) // 2] if values else 0.0

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("latencies", None)
        data["log_files"] = sorted(self.log_files)
        data["total_tokens"] = self.total_tokens
        data["latency_p50"] = self.latency_p50
        return data


def _normal_provider(value: str | None) -> str:
    return (value or "").rstrip("/")


def read_usage(
    log_paths: list[str | Path],
    *,
    provider: str | None = None,
    model: str | None = None,
    all_models: bool = False,
) -> list[UsageSummary]:
    """Read attempt telemetry from JSONL logs.

    Newer logs contain provider/model metadata in ``run_start``. Older logs
    are matched by model only, because no reliable provider information exists
    in their attempt records.
    """
    wanted_provider = _normal_provider(provider)
    summaries: dict[tuple[str, str], UsageSummary] = {}

    for raw_path in log_paths:
        path = Path(raw_path)
        if not path.is_file():
            continue
        runs: dict[str, tuple[str, str]] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "run_start":
                runs[record.get("run_id", "")] = (
                    _normal_provider(record.get("provider")), record.get("model", ""),
                )
                continue
            if record.get("type") != "attempt":
                continue
            generation = record.get("generation")
            if not isinstance(generation, dict):
                continue
            run_provider, run_model = runs.get(record.get("run_id", ""), ("", ""))
            recorded_model = generation.get("model") or run_model
            if not all_models:
                if model and recorded_model != model:
                    continue
                if wanted_provider and run_provider and run_provider != wanted_provider:
                    continue
            key = (run_provider or "(unknown provider)", recorded_model or "(unknown model)")
            summary = summaries.setdefault(key, UsageSummary(*key))
            summary.attempts += 1
            summary.log_files.add(str(path))
            if generation.get("cached"):
                summary.cache_hits += 1
                continue
            prompt_tokens = int(generation.get("prompt_tokens") or 0)
            completion_tokens = int(generation.get("completion_tokens") or 0)
            summary.prompt_tokens += prompt_tokens
            summary.completion_tokens += completion_tokens
            latency = generation.get("latency")
            if isinstance(latency, (int, float)) and latency > 0:
                summary.latencies.append(float(latency))
            if generation.get("error"):
                summary.api_errors += 1
                continue
            summary.completed_requests += 1
            if not prompt_tokens and not completion_tokens:
                summary.responses_without_usage += 1

    return sorted(summaries.values(), key=lambda item: (item.provider, item.model))
