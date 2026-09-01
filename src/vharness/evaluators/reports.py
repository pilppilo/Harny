"""Report evaluators: SARIF, Markdown, JSON. Each is independently selectable."""

from __future__ import annotations

import hashlib
import json
import os

from ..core import Attempt
from ..sarif import build_sarif
from .base import Evaluator, register_builtin

_SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def _all_findings(attempts: list[Attempt]):
    for a in attempts:
        yield from a.findings


def _out_path(run_info: dict, default: str, requested: str | None, ext: str) -> str:
    """Resolve output path: explicit per-format arg > base 'out' + ext > default."""
    if requested:
        return requested
    base = run_info.get("out")
    if base:
        return base if base.endswith(f".{ext}") else f"{base}.{ext}"
    return default


@register_builtin
class SarifReport(Evaluator):
    name = "sarif"
    help = "write a SARIF 2.1.0 report (GitHub code-scanning compatible)"

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        path = _out_path(run_info, "report.sarif", run_info.get("sarif_out"), "sarif")
        sarif = build_sarif(list(_all_findings(attempts)))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sarif, fh, indent=2)
        print(f"[+] SARIF: {path}")


@register_builtin
class MarkdownReport(Evaluator):
    name = "markdown"
    help = "write a human-readable Markdown issue report"

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        path = _out_path(run_info, "report.md", run_info.get("markdown_out"), "md")
        findings = sorted(_all_findings(attempts), key=lambda f: (_SEV_ORDER.get(f.severity, 3), f.file, f.line))
        out: list[str] = [
            f"# Security scan report",
            "",
            f"**{len(findings)} findings** across {len({f.file for f in findings})} file(s).",
            "",
        ]
        by_file: dict[str, list] = {}
        for f in findings:
            by_file.setdefault(f.file, []).append(f)
        for file in sorted(by_file):
            out += [f"## `{file}`", ""]
            for f in by_file[file]:
                out += [
                    f"### {f.severity} · {f.cwe} — `{f.function or 'n/a'}` (line {f.line})",
                    "",
                    f"**Sink:** `{f.sink or 'n/a'}`",
                    "",
                    f.explanation,
                ]
                if f.patch:
                    out += ["", "**Suggested patch** (advisory — review before applying):", "", "```", f.patch, "```"]
                out.append("")
        if not findings:
            out.append("_No findings._")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out))
        print(f"[+] Markdown: {path}")


@register_builtin
class JsonReport(Evaluator):
    name = "json"
    help = "write findings as flat JSON"

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        path = _out_path(run_info, "report.json", run_info.get("json_out"), "json")
        data = [
            {
                "file": f.file, "line": f.line, "function": f.function, "cwe": f.cwe,
                "severity": f.severity, "sink": f.sink, "explanation": f.explanation, "patch": f.patch,
            }
            for f in _all_findings(attempts)
        ]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        print(f"[+] JSON: {path}")


@register_builtin
class Summary(Evaluator):
    name = "summary"
    help = "print the run summary to stdout"

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        info = run_info.get("run_info")
        if info is not None:
            print(
                f"\n[*] run {info.run_id}: probes={info.probes} attempts={info.attempts_total} "
                f"ok={info.ok} parse_errors={info.parse_errors} api_errors={info.api_errors} "
                f"findings={info.findings} wall={info.wall_seconds:.1f}s"
            )
        gen = run_info.get("generator_summary")
        if gen:
            print(f"[*] generator: {gen}")
        errs = [a for a in attempts if a.status == "api_error"]
        if errs:
            print(f"[!] {len(errs)} attempt(s) failed at the endpoint (first 3):")
            for a in errs[:3]:
                print(f"    {a.source}: {a.generation.error if a.generation else '?'}")
