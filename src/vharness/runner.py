"""Runner: orchestrates probe → generator → detector with concurrency + a JSONL log."""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from .core import (
    DETECTOR_REGISTRY,
    EVALUATOR_REGISTRY,
    PROBE_REGISTRY,
    Attempt,
    load_entry_points,
)
from .generators.base import Generator

# Built-ins register when the stage packages are imported.
from . import detectors  # noqa: F401,E402
from . import evaluators  # noqa: F401,E402
from . import generators  # noqa: F401,E402
from . import probes  # noqa: F401,E402


@dataclasses.dataclass
class RunInfo:
    run_id: str
    probes: list[str]
    generator: str
    model: str = ""
    detectors: list[str] | None = None
    evaluators: list[str] | None = None
    targets: list[str] | None = None
    dry_run: bool = False
    started_at: float = 0.0
    wall_seconds: float = 0.0
    attempts_total: int = 0
    ok: int = 0
    parse_errors: int = 0
    api_errors: int = 0
    skipped: int = 0
    findings: int = 0


class Runner:
    def __init__(
        self,
        generator: Generator,
        *,
        detectors: list[str] | None = None,
        workers: int = 4,
        log_file: str | None = None,
    ) -> None:
        load_entry_points()  # third-party plugins, idempotent
        self.generator = generator
        self.detector_names = detectors or ["json-verdict"]
        self.workers = workers
        self.log_file = log_file
        self._log_lock = threading.Lock()
        if log_file:
            os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

    # ---- public API ------------------------------------------------------
    def run(
        self,
        probe_names: list[str],
        probe_kwargs: dict | None = None,
        *,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> tuple[list[Attempt], RunInfo]:
        """Execute a full pipeline pass; returns (attempts, run_info)."""
        probe_kwargs = probe_kwargs or {}
        attempts: list[Attempt] = []
        for name in probe_names:
            probe = PROBE_REGISTRY.instantiate(name)
            got = probe.attempts(**probe_kwargs)
            for a in got:
                a.probe = name
            attempts.extend(got)

        info = RunInfo(
            run_id=run_id or uuid.uuid4().hex[:12],
            probes=list(probe_names),
            generator="pending",  # filled after construction (dry runs never construct)
            model="",
            detectors=list(self.detector_names),
            targets=probe_kwargs.get("targets") or probe_kwargs.get("path"),
            dry_run=dry_run,
            started_at=time.time(),
            attempts_total=len(attempts),
        )

        if dry_run:
            info.wall_seconds = time.time() - info.started_at
            return attempts, info

        # Real run — the generator gets constructed here (first .generate call).
        info.generator = getattr(self.generator, "name", "custom")
        info.model = getattr(self.generator, "model", "")
        detectors = [DETECTOR_REGISTRY.instantiate(n) for n in self.detector_names]

        def work(attempt: Attempt) -> Attempt:
            gen = self.generator.generate(attempt.system, attempt.prompt)
            attempt.record(gen)
            for d in detectors:
                d.detect(attempt)
            self._log(attempt, info)
            return attempt

        done: list[Attempt] = []
        with ThreadPoolExecutor(max_workers=max(1, self.workers)) as pool:
            futures = [pool.submit(work, a) for a in attempts]
            for fut in as_completed(futures):
                done.append(fut.result())

        for a in done:
            info.ok += a.status == "ok"
            info.parse_errors += a.status == "parse_error"
            info.api_errors += a.status == "api_error"
            info.skipped += a.status == "skipped"
            info.findings += len(a.findings)
        info.wall_seconds = time.time() - info.started_at
        return done, info

    def evaluate(self, attempts: list[Attempt], run_info: dict, evaluator_names: list[str]) -> None:
        """Run evaluators; run_info is passed through as-is (cli adds out paths)."""
        for name in evaluator_names:
            ev = EVALUATOR_REGISTRY.instantiate(name)
            ev.evaluate(attempts, run_info)

    # ---- logging ---------------------------------------------------------
    def _log(self, attempt: Attempt, info: RunInfo) -> None:
        if not self.log_file:
            return
        rec = {
            "run_id": info.run_id,
            "ts": time.time(),
            "probe": attempt.probe,
            "source": attempt.source,
            "context": attempt.context,
            "id": attempt.id,
            "status": attempt.status,
            "verdict": attempt.verdict,
            "findings": [dataclasses.asdict(f) for f in attempt.findings],
            "notes": attempt.detector_notes,
            "expected_verdict": attempt.expected_verdict,
            "expected_cwes": [f.cwe for f in (attempt.expected_findings or [])],
            "prompt_chars": len(attempt.prompt),
            "generation": attempt.generation and {
                "model": attempt.generation.model,
                "finish_reason": attempt.generation.finish_reason,
                "latency": attempt.generation.latency,
                "error": attempt.generation.error,
                "cached": attempt.generation.cached,
                "prompt_tokens": attempt.generation.prompt_tokens,
                "completion_tokens": attempt.generation.completion_tokens,
            },
        }
        line = json.dumps(rec, default=str)
        with self._log_lock:
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
