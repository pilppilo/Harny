"""Scan engine: file discovery, triage, concurrent analysis, run stats."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .analyzers import Analyzer, get_analyzer_for
from .findings import Finding
from .llm import LLMClient

DEFAULT_EXCLUDES = {
    ".git", "node_modules", "vendor", "build", "dist", "out", "__pycache__",
    ".cache", ".venv", "venv", "target", ".idea", ".vscode",
}
MAX_FILE_BYTES = 1_000_000  # skip files larger than 1 MB


@dataclass
class RunStats:
    files_seen: int = 0
    files_no_analyzer: int = 0
    files_too_big: int = 0
    files_gated_out: int = 0
    files_analyzed: int = 0
    chunks_total: int = 0
    chunks_interesting: int = 0
    chunks_oversize: int = 0
    findings: int = 0
    duplicates_dropped: int = 0
    wall_seconds: float = 0.0
    by_severity: dict = field(default_factory=dict)
    by_cwe: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def inc(self, name: str, n: int = 1) -> None:
        with self._lock:
            setattr(self, name, getattr(self, name) + n)

    def record(self, message: str) -> None:
        with self._lock:
            self.errors.append(message)

    def note_finding(self, f: Finding) -> None:
        self.findings += 1
        self.by_severity[f.severity] = self.by_severity.get(f.severity, 0) + 1
        self.by_cwe[f.cwe] = self.by_cwe.get(f.cwe, 0) + 1

    def summary(self) -> str:
        cwes = ", ".join(f"{k}×{v}" for k, v in sorted(self.by_cwe.items(), key=lambda kv: -kv[1]))
        return (
            f"files: {self.files_seen} seen / {self.files_analyzed} analyzed "
            f"({self.files_gated_out} triaged clean, {self.files_no_analyzer} no analyzer, {self.files_too_big} too big)\n"
            f"chunks: {self.chunks_interesting}/{self.chunks_total} audited ({self.chunks_oversize} oversize skipped)\n"
            f"findings: {self.findings} "
            f"(by severity: {self.by_severity or {}})\n"
            f"by CWE: {cwes or 'none'}\n"
            f"dedup dropped: {self.duplicates_dropped} | wall: {self.wall_seconds:.1f}s"
        )


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    stats: RunStats = field(default_factory=RunStats)
    dry_run_plan: list[tuple[str, str, int]] | None = None  # (file, chunk, line)


def discover_files(roots: list[str], extra_excludes: list[str] | None = None) -> list[str]:
    excludes = DEFAULT_EXCLUDES | set(extra_excludes or [])
    found: list[str] = []
    for root in roots:
        if os.path.isfile(root):
            found.append(root)
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in excludes and not d.startswith(".git")]
            for fn in filenames:
                found.append(os.path.join(dirpath, fn))
    return sorted(found)


def _scan_one(
    path: str,
    analyzer: Analyzer,
    client: LLMClient | None,
    stats: RunStats,
    root: str,
    plan: list[tuple[str, str, int]] | None,
) -> list[Finding]:
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_FILE_BYTES + 1)
    except OSError as e:
        stats.record(f"{path}: {e}")
        return []
    if len(raw) > MAX_FILE_BYTES:
        stats.inc("files_too_big")
        return []
    first_bytes = raw[:256]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("utf-8", "replace")

    if not analyzer.file_is_interesting(content):
        stats.inc("files_gated_out")
        return []
    stats.inc("files_analyzed")

    findings: list[Finding] = []
    for chunk in analyzer.chunk(content, path):
        stats.inc("chunks_total")
        if len(chunk.code) > analyzer.max_chunk_chars:
            stats.inc("chunks_oversize")
            continue
        if not analyzer.chunk_is_interesting(chunk.code):
            continue
        stats.inc("chunks_interesting")
        display = os.path.relpath(path, root) if root else path
        if plan is not None:
            plan.append((display, chunk.name, chunk.line))
            continue
        assert client is not None
        result = client.analyze(analyzer.system_prompt, analyzer.user_prompt(chunk))
        for f in result.parsed.findings:
            f.file, f.line, f.function = display, chunk.line, chunk.name
            findings.append(f)
        if result.error:
            stats.record(f"{display}:{chunk.line}: {result.error}")
    return findings


def scan(
    roots: list[str],
    client: LLMClient | None,
    *,
    workers: int = 4,
    extra_excludes: list[str] | None = None,
    only_analyzers: set[str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> ScanResult:
    result = ScanResult()
    started = time.monotonic()
    plan: list[tuple[str, str, int]] | None = [] if dry_run else None

    paths = discover_files(roots, extra_excludes)
    tasks: list[tuple[str, Analyzer]] = []
    for path in paths:
        result.stats.files_seen += 1
        try:
            with open(path, "rb") as f:
                head = f.read(256)
        except OSError:
            head = b""
        analyzer = get_analyzer_for(path, head)
        if analyzer is None:
            result.stats.files_no_analyzer += 1
            continue
        if only_analyzers and analyzer.name not in only_analyzers:
            result.stats.files_no_analyzer += 1
            continue
        tasks.append((path, analyzer))

    root0 = roots[0] if len(roots) == 1 and os.path.isdir(roots[0]) else None
    all_findings: list[Finding] = []
    if dry_run:
        for path, analyzer in tasks:
            all_findings.extend(_scan_one(path, analyzer, None, result.stats, root0, plan))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_scan_one, path, analyzer, client, result.stats, root0, None): path
                for path, analyzer in tasks
            }
            for future in as_completed(futures):
                all_findings.extend(future.result())

    # Dedup by (file, cwe, function, line) — models sometimes repeat a finding,
    # but distinct top-level segments of one file must stay separate.
    seen: set[tuple[str, str, str, int]] = set()
    for f in all_findings:
        key = (f.file, f.cwe, f.function, f.line)
        if key in seen:
            result.stats.duplicates_dropped += 1
            continue
        seen.add(key)
        result.findings.append(f)
        result.stats.note_finding(f)

    result.stats.wall_seconds = time.monotonic() - started
    result.dry_run_plan = plan
    if verbose and plan is not None:
        for display, name, line in plan[:50]:
            print(f"  [would query] {display}:{line} {name}")
        if len(plan) > 50:
            print(f"  … and {len(plan) - 50} more")
    return result
