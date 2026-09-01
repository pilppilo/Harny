"""Runner: orchestrates probe → generator → detector with concurrency + a JSONL log."""

from __future__ import annotations

import dataclasses
import hashlib
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
from .log import log
from .skills import Skill, render_skill_instructions

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
    internal_errors: int = 0
    skipped: int = 0
    findings: int = 0
    skills: list[dict] | None = None


class Runner:
    def __init__(
        self,
        generator: Generator,
        *,
        detectors: list[str] | None = None,
        workers: int = 4,
        log_file: str | None = None,
        log_raw: bool = False,
        skills: list[Skill] | None = None,
    ) -> None:
        load_entry_points()  # third-party plugins, idempotent
        self.generator = generator
        self.detector_names = detectors or ["json-verdict"]
        self.workers = workers
        self.log_file = log_file
        self.log_raw = log_raw
        self.skills = list(skills or [])
        self._skill_instructions = render_skill_instructions(self.skills)
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
        self._fh = open(self.log_file, "a", encoding="utf-8") if self.log_file else None
        try:
            return self._run_impl(probe_names, probe_kwargs, dry_run=dry_run, run_id=run_id)
        finally:
            if getattr(self, "_fh", None) is not None:
                self._fh.close()
                self._fh = None

    def _run_impl(
        self,
        probe_names: list[str],
        probe_kwargs: dict | None = None,
        *,
        dry_run: bool = False,
        run_id: str | None = None,
    ) -> tuple[list[Attempt], RunInfo]:
        probe_kwargs = probe_kwargs or {}
        attempts: list[Attempt] = []
        for name in probe_names:
            probe = PROBE_REGISTRY.instantiate(name)
            got = probe.attempts(**probe_kwargs)
            for a in got:
                a.probe = name
                if self._skill_instructions:
                    a.system = (a.system.rstrip() + self._skill_instructions)
                    a.context = dict(a.context)
                    a.context["skills"] = [s.metadata() for s in self.skills]
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
            skills=[s.metadata() for s in self.skills] or None,
        )
        self._log_event({"type": "run_start", "run_id": info.run_id, "ts": time.time(),
                         "probes": info.probes, "targets": info.targets,
                         "attempts": len(attempts), "dry_run": dry_run,
                         "detectors": info.detectors, "skills": info.skills})
        if dry_run:
            info.wall_seconds = time.time() - info.started_at
            self._log_event({"type": "run_end", "run_id": info.run_id, "ts": time.time(),
                             "status": "dry_run", "attempts": len(attempts)})
            return attempts, info

        # Real run — the generator gets constructed here (first .generate call).
        info.generator = getattr(self.generator, "name", "custom")
        info.model = getattr(self.generator, "model", "")
        detectors = [DETECTOR_REGISTRY.instantiate(n) for n in self.detector_names]

        def work(attempt: Attempt) -> Attempt:
            try:
                gen = self.generator.generate(attempt.system, attempt.prompt)
                attempt.record(gen)
                for d in detectors:
                    d.detect(attempt)
            except Exception as e:  # noqa: BLE001 — a detector/generator bug must not kill the run
                log.exception("internal error on attempt %s (%s)", attempt.source, attempt.id)
                attempt.status = "internal_error"
                attempt.verdict = "error"
                attempt.detector_notes.append(f"internal error: {e}")
            self._log(attempt, info)
            return attempt

        done: list[Attempt] = []
        total = len(attempts)
        with ThreadPoolExecutor(max_workers=max(1, self.workers)) as pool:
            futures = [pool.submit(work, a) for a in attempts]
            for i, fut in enumerate(as_completed(futures), 1):
                try:
                    a = fut.result()
                except Exception:  # noqa: BLE001 — belt & braces around work()
                    log.exception("worker future failed (%d/%d)", i, total)
                    continue
                done.append(a)
                if a.status == "ok":
                    log.info("[%d/%d] %s → %s (%d findings)", i, total, a.source, a.verdict, len(a.findings))
                else:
                    log.info("[%d/%d] %s → %s (%s)", i, total, a.source, a.verdict or "?", a.status)

        for a in done:
            info.ok += a.status == "ok"
            info.parse_errors += a.status == "parse_error"
            info.api_errors += a.status == "api_error"
            info.internal_errors += a.status == "internal_error"
            info.skipped += a.status == "skipped"
            info.findings += len(a.findings)
        info.wall_seconds = time.time() - info.started_at
        self._log_event({"type": "run_end", "run_id": info.run_id, "ts": time.time(),
                         "status": "complete", "attempts": info.attempts_total,
                         "ok": info.ok, "parse_errors": info.parse_errors,
                         "api_errors": info.api_errors, "internal_errors": info.internal_errors,
                         "findings": info.findings, "wall_seconds": info.wall_seconds})
        return done, info

    def evaluate(self, attempts: list[Attempt], run_info: dict, evaluator_names: list[str]) -> None:
        """Run evaluators; run_info is passed through as-is (cli adds out paths)."""
        for name in evaluator_names:
            ev = EVALUATOR_REGISTRY.instantiate(name)
            ev.evaluate(attempts, run_info)

    # ---- logging ---------------------------------------------------------
    def _log_event(self, record: dict) -> None:
        if not hasattr(self, "_fh") or self._fh is None:
            return
        with self._log_lock:
            self._fh.write(json.dumps(record, default=str) + "\n")
            self._fh.flush()

    def _log(self, attempt: Attempt, info: RunInfo) -> None:
        if not hasattr(self, "_fh") or self._fh is None:
            return
        rec = {
            "type": "attempt",
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
            "prompt_sha256": hashlib.sha256(
                (attempt.system + "\x00" + attempt.prompt).encode("utf-8", "replace")
            ).hexdigest(),
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
        if self.log_raw:
            rec["prompt"] = attempt.prompt
            rec["system_prompt"] = attempt.system
            if attempt.generation is not None:
                rec["generation_text"] = attempt.generation.text
        line = json.dumps(rec, default=str)
        with self._log_lock:
            self._fh.write(line + "\n")
            self._fh.flush()
