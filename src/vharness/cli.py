"""vharness CLI.

Two levels:
  * ``vharness run``     — compose any probes × generator × detectors × evaluators
  * ``vharness scan`` / ``vharness eval`` — opinionated presets over `run`
  * ``vharness replay``  — re-run detectors on a previous JSONL run log
Plus ``vharness list`` to enumerate registered plugins.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import VERSION
from .config import ConfigError, resolve_endpoint
from .core import (
    DETECTOR_REGISTRY,
    EVALUATOR_REGISTRY,
    GENERATOR_REGISTRY,
    PROBE_REGISTRY,
)
from .log import log, setup as log_setup
from .runner import Runner
from .skills import SkillError, load_skills

#: Probes used by the ``scan`` preset (filesystem code scanning).
SCAN_PROBES = ["ccpp", "web", "shell", "distroconf"]


class CLIError(RuntimeError):
    """User-facing CLI failure; main() prints it and exits 2."""


def _make_generator(args):
    name = getattr(args, "generator", None) or "openai"
    if name == "mock":
        from .generators.mock import Mock

        script = {}
        if getattr(args, "mock_script", None):
            for pair in args.mock_script:
                k, _, v = pair.partition("=")
                script[k] = v.replace("\\n", "\n")
        return Mock(script=script)
    if name == "openai":
        try:
            cfg, src = resolve_endpoint(
                args.base_url, args.api_key, args.model,
                profile=getattr(args, "profile", None),
                config_file=getattr(args, "config_file", None),
            )
        except ConfigError as e:
            raise CLIError(str(e)) from e
        try:
            from .generators.openai_compat import OpenAICompatible
        except ModuleNotFoundError:
            raise CLIError(
                "the 'openai' package is not installed; "
                "run `uv sync` or `pip install openai` (or use --generator mock offline)"
            ) from None
        log.info("endpoint: %s  (from %s)", cfg.describe(), src)
        cache = None
        if not getattr(args, "no_cache", False):
            cache = getattr(args, "cache_file", None) or os.path.expanduser("~/.cache/vharness.sqlite3")
            os.makedirs(os.path.dirname(cache), exist_ok=True)
        return OpenAICompatible.from_config(
            cfg,
            timeout=args.timeout,
            max_retries=args.max_retries,
            max_tokens=args.max_tokens,
            cache_path=cache,
        )
    try:
        return GENERATOR_REGISTRY.instantiate(name)
    except KeyError as e:
        raise CLIError(str(e)) from e


class _LazyGenerator:
    """Defers real generator construction until first use (dry runs never pay)."""

    def __init__(self, args):
        self._args = args
        self._inner = None

    def _get(self):
        if self._inner is None:
            self._inner = _make_generator(self._args)
        return self._inner

    def __getattr__(self, item):
        return getattr(self._get(), item)

    def generate(self, system: str, prompt: str):
        return self._get().generate(system, prompt)


def _runner(args) -> Runner:
    generator = _LazyGenerator(args)
    detectors = getattr(args, "detectors", None) or ["json-verdict"]
    log_file = None if getattr(args, "no_log", False) else getattr(args, "log_file", None)
    try:
        skills = load_skills(getattr(args, "skill", None))
    except (SkillError, OSError, UnicodeError) as e:
        raise CLIError(str(e)) from e
    return Runner(
        generator,
        detectors=detectors,
        workers=args.workers,
        log_file=log_file,
        log_raw=getattr(args, "log_raw", False),
        skills=skills,
        verbose=getattr(args, "verbose", 0),
        show_findings=getattr(args, "show_findings", False),
    )


def _probe_kwargs(args, probe_names: list[str]) -> dict:
    kw: dict = {}
    if getattr(args, "targets", None):
        kw["targets"] = list(args.targets)
    if getattr(args, "exclude", None):
        kw["exclude"] = list(args.exclude)
    if getattr(args, "corpus_dir", None):
        kw["corpus_dir"] = args.corpus_dir
    if getattr(args, "dataset", None):
        kw["path"] = args.dataset
    if getattr(args, "limit", None):
        kw["limit"] = args.limit
    if getattr(args, "skip_corpus", False):
        probe_names[:] = [p for p in probe_names if p != "corpus"]
    return kw


def cmd_run(args) -> int:
    probe_names = [p.strip() for p in args.probes.split(",") if p.strip()]
    for p in probe_names:
        try:
            PROBE_REGISTRY.get(p)
        except KeyError as e:
            raise CLIError(str(e)) from e
    runner = _runner(args)
    probe_kwargs = _probe_kwargs(args, probe_names)

    evaluators = [e.strip() for e in (args.evaluators or "").split(",") if e.strip()]
    evaluator_names = evaluators or ["summary"]
    run_info_extra = {
        "out": getattr(args, "out", None),
        "sarif_out": getattr(args, "sarif_out", None),
        "markdown_out": getattr(args, "markdown_out", None),
        "json_out": getattr(args, "json_out", None),
        "metrics_out": getattr(args, "metrics_out", None),
        "generator_summary": (
            runner.generator.summary()
            if not isinstance(runner.generator, _LazyGenerator)
            else ""
        ),
    }

    attempts, info = runner.run(
        probe_names, probe_kwargs,
        dry_run=getattr(args, "dry_run", False),
    )
    if getattr(args, "dry_run", False):
        log.info("DRY RUN: %d attempt(s) would be generated across probes: %s", len(attempts), probe_names)
        for a in attempts[:50]:
            log.info("  would query %s:%s (%s)", a.source, a.context.get("line", ""), a.probe)
        if len(attempts) > 50:
            log.info("  … and %d more", len(attempts) - 50)
        return 0

    import dataclasses
    run_info = dataclasses.asdict(info) | run_info_extra | {"run_info": info}
    runner.evaluate(attempts, run_info, evaluator_names)
    if getattr(args, "fail_on_findings", False) and any(a.findings for a in attempts):
        log.info("fail-on-findings: %d finding(s) present — exiting 1", sum(len(a.findings) for a in attempts))
        return 1
    return 0


def cmd_scan(args) -> int:
    args.probes = ",".join(SCAN_PROBES)
    if getattr(args, "analyzers", None):
        args.probes = args.analyzers
    args.evaluators = args.format
    return cmd_run(args)


def cmd_eval(args) -> int:
    args.probes = "corpus"
    if getattr(args, "dataset", None):
        args.probes = "corpus,chat-dataset"
    if getattr(args, "skip_corpus", False):
        args.probes = "chat-dataset"
    args.evaluators = "metrics,summary"
    args.log_file = args.log_file or "eval_log.jsonl"
    return cmd_run(args)


def cmd_list(args) -> int:
    regs = [
        ("probes", PROBE_REGISTRY),
        ("generators", GENERATOR_REGISTRY),
        ("detectors", DETECTOR_REGISTRY),
        ("evaluators", EVALUATOR_REGISTRY),
    ]
    width = max(len(n) for _, reg in regs for n in reg.names()) or 1
    for label, reg in regs:
        print(f"{label}:")
        for name in reg.names():
            print(f"  {name:<{width}}  {reg.help_for(name)}")
        print()
    return 0


def cmd_list_skills(args) -> int:
    """List valid skills from explicit directories or their child directories."""
    roots = args.paths or ["."]
    found = []
    for root in roots:
        path = os.path.abspath(os.path.expanduser(root))
        candidates = [path]
        if os.path.isdir(path):
            candidates.extend(os.path.join(path, n) for n in sorted(os.listdir(path)))
        for candidate in candidates:
            try:
                skill = load_skills([candidate])[0]
            except (SkillError, OSError, UnicodeError):
                continue
            if skill.path not in {s.path for s in found}:
                found.append(skill)
    for skill in found:
        print(f"{skill.name}\t{skill.description}\t{skill.path}")
    return 0


def cmd_replay(args) -> int:
    """Re-apply detectors to a previous run log — no model calls.

    Attempts are reconstructed from `type: attempt` records (raw text needed
    for re-detection: requires a log written with --log-raw). Attempts whose
    log record lacks `generation_text` are reported as skipped.
    """
    from .core import Attempt, Finding, Generation
    from .runner import RunInfo
    from vharness.detectors.json_verdict import JSONVerdict

    attempts: list[Attempt] = []
    skipped = 0
    try:
        fh = open(args.log_path, encoding="utf-8")
    except OSError as e:
        raise CLIError(f"log file not found or unreadable: {args.log_path}") from e

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("type") != "attempt":
                continue
            if args.run_id and rec.get("run_id") != args.run_id:
                continue
            gen_data = rec.get("generation") or {}
            if not rec.get("generation_text") and not gen_data.get("error"):
                skipped += 1
                continue
            a = Attempt(
                prompt=rec.get("prompt", ""),
                system=rec.get("system_prompt", ""),
                probe=rec.get("probe", ""),
                source=rec.get("source", ""),
                context=rec.get("context", {}),
                status="pending",
            )
            a.id = rec.get("id", a.id)
            a.record(Generation(
                text=rec.get("generation_text", ""),
                model=gen_data.get("model", ""),
                finish_reason=gen_data.get("finish_reason", ""),
                error=gen_data.get("error"),
            ))
            if rec.get("expected_verdict"):
                a.expected_verdict = rec["expected_verdict"]
                a.expected_findings = [
                    Finding(cwe=c, severity="High", sink="", explanation="expected")
                    for c in rec.get("expected_cwes", [])
                ]
            attempts.append(a)

    if skipped:
        log.warning("%s attempt(s) skipped: no generation_text in log (write with --log-raw)", skipped)
    if not attempts:
        raise CLIError(f"no replayable attempts found in {args.log_path}")

    detector = JSONVerdict()
    for a in attempts:
        detector.detect(a)

    ok = sum(a.status == "ok" for a in attempts)
    parse_errors = sum(a.status == "parse_error" for a in attempts)
    api_errors = sum(a.status == "api_error" for a in attempts)
    findings = sum(len(a.findings) for a in attempts)

    run_info_obj = RunInfo(
        run_id=args.run_id or "replay",
        probes=["replay"],
        generator="replay",
        model="replay",
        attempts_total=len(attempts),
        ok=ok,
        parse_errors=parse_errors,
        api_errors=api_errors,
        skipped=skipped,
        findings=findings,
        dry_run=False,
    )

    import dataclasses
    run_info = dataclasses.asdict(run_info_obj) | {
        "run_info": run_info_obj,
        "out": args.out,
        "sarif_out": getattr(args, "sarif_out", None),
        "markdown_out": getattr(args, "markdown_out", None),
        "json_out": getattr(args, "json_out", None),
        "metrics_out": getattr(args, "metrics_out", None),
    }
    log.info("replayed %d attempt(s): ok=%d parse_errors=%d api_errors=%d findings=%d (skipped=%d)",
             len(attempts), ok, parse_errors, api_errors, findings, skipped)
    evaluator_names = [e.strip() for e in (args.evaluators or "metrics,summary").split(",") if e.strip()]
    runner = Runner(_NeverGenerate(), log_file=None)
    runner.evaluate(attempts, run_info, evaluator_names)
    if getattr(args, "fail_on_findings", False) and any(a.findings for a in attempts):
        return 1
    return 0


class _NeverGenerate:
    """Placeholder generator: replay never generates."""

    name = "replay"
    model = "replay"

    def generate(self, system: str, prompt: str):  # pragma: no cover
        raise RuntimeError("replay must not generate")


def _common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--fail-on-findings", action="store_true",
                   help="exit 1 if any findings were produced (for CI)")
    p.add_argument("-v", "--verbose", action="count", default=0,
                   help="verbosity: -v shows recon breakdown & inline findings, -vv debug triage (repeatable)")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress log output (errors still exit non-zero)")
    p.add_argument("--show-findings", action="store_true",
                   help="print inline finding details as they are discovered (implied by -v)")


def _generator_args(p: argparse.ArgumentParser, include_model: bool = True) -> None:
    p.add_argument("--generator", default="openai", help="openai | mock | any registered generator")
    if include_model:
        p.add_argument("--base-url", help="OpenAI-compatible endpoint (env VHARNESS_BASE_URL, config profile)")
        p.add_argument("--api-key", help="API key (env VHARNESS_API_KEY / OPENAI_API_KEY, config profile)")
        p.add_argument("--model", help="model name (env VHARNESS_MODEL, config profile)")
        p.add_argument("--profile", default=None, help="named section in the config file (e.g. ollama, openrouter)")
        p.add_argument("--config", dest="config_file", default=None,
                       help="config file path (default: $VHARNESS_CONFIG, ~/.config/vharness/config.toml, ./vharness.toml)")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--cache-file", default=None)
    p.add_argument("--log-file", default=None, help="JSONL run log path")
    p.add_argument("--log-raw", action="store_true", help="include prompts and raw model text in the JSONL log")
    p.add_argument("--no-log", action="store_true")
    p.add_argument("--skill", action="append", default=[], metavar="DIR",
                   help="local skill directory containing SKILL.md (repeatable)")
    p.add_argument("--mock-script", action="append", default=[], metavar="KEY=REPLY",
                   help="mock generator: exact-substring key → canned reply (repeatable)")
    _common_args(p)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vharness", description="pluggable LLM security harness")
    parser.add_argument("--version", action="version", version=f"vharness {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="compose probes × generator × detectors × evaluators")
    run_p.add_argument("targets", nargs="*", help="files/dirs (for filesystem probes)")
    run_p.add_argument("--probes", required=True, help="comma list of probe names (see `vharness list`)")
    run_p.add_argument("--evaluators", default=None, help="comma list (default: summary)")
    run_p.add_argument("--detectors", default=None, help="comma list (default: json-verdict)")
    run_p.add_argument("--dataset", default=None, help="JSONL path for dataset probes")
    run_p.add_argument("--corpus-dir", default=None, help="labeled corpus dir (default: built-in)")
    run_p.add_argument("--limit", type=int, default=None)
    run_p.add_argument("--exclude", action="append", default=[], help="dir name to skip (repeatable)")
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--out", default=None, help="base path for report outputs")
    run_p.add_argument("--sarif-out", default=None)
    run_p.add_argument("--markdown-out", default=None)
    run_p.add_argument("--json-out", default=None)
    run_p.add_argument("--metrics-out", default=None)
    _generator_args(run_p)
    run_p.set_defaults(func=cmd_run, log_file="scan_log.jsonl")

    scan_p = sub.add_parser("scan", help="preset: scan code with all code-domain probes")
    scan_p.add_argument("targets", nargs="+")
    scan_p.add_argument("--analyzers", default=None, help="restrict to comma list (ccpp,web,shell,distroconf)")
    scan_p.add_argument("--format", default="sarif,markdown", help="comma list: sarif,markdown,json,summary")
    scan_p.add_argument("--out", default="report")
    scan_p.add_argument("--dry-run", action="store_true")
    scan_p.add_argument("--exclude", action="append", default=[], help="dir name to skip (repeatable)")
    _generator_args(scan_p)
    scan_p.set_defaults(func=cmd_scan, log_file="scan_log.jsonl")

    eval_p = sub.add_parser("eval", help="preset: score a model on labeled data")
    eval_p.add_argument("--corpus-dir", default=None)
    eval_p.add_argument("--dataset", default=None, help="chat-format JSONL with code samples")
    eval_p.add_argument("--limit", type=int, default=None)
    eval_p.add_argument("--skip-corpus", action="store_true")
    eval_p.add_argument("--metrics-out", default="eval_metrics.json")
    _generator_args(eval_p)
    eval_p.set_defaults(func=cmd_eval, log_file="eval_log.jsonl")

    replay_p = sub.add_parser("replay", help="re-run detectors on a previous JSONL run log (no model calls)")
    replay_p.add_argument("log_path", help="JSONL run log (must have been written with --log-raw to re-detect)")
    replay_p.add_argument("--run-id", default=None, help="only replay attempts from this run")
    replay_p.add_argument("--evaluators", default="metrics,summary")
    replay_p.add_argument("--out", default="replay_report")
    replay_p.add_argument("--sarif-out", default=None)
    replay_p.add_argument("--markdown-out", default=None)
    replay_p.add_argument("--json-out", default=None)
    replay_p.add_argument("--metrics-out", default=None)
    _common_args(replay_p)
    replay_p.set_defaults(func=cmd_replay)

    list_p = sub.add_parser("list", help="list registered plugins")
    list_p.set_defaults(func=cmd_list)

    skills_p = sub.add_parser("list-skills", help="list valid local SKILL.md directories")
    skills_p.add_argument("paths", nargs="*", help="skill directories or directories to search")
    skills_p.set_defaults(func=cmd_list_skills)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_setup(getattr(args, "verbose", 0), getattr(args, "quiet", False))
    try:
        return args.func(args)
    except (CLIError, ConfigError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
