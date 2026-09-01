"""vharness CLI.

Two levels:
  * ``vharness run``     — compose any probes × generator × detectors × evaluators
  * ``vharness scan`` / ``vharness eval`` — opinionated presets over `run`

Plus ``vharness list`` to enumerate plugins and ``vharness replay`` to re-run
from a previous JSONL log.
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
from .runner import Runner

#: Probes used by the ``scan`` preset (filesystem code scanning).
SCAN_PROBES = ["ccpp", "web", "shell", "distroconf"]
#: Probes used by the ``eval`` preset (labeled datasets).
EVAL_PROBES = ["corpus", "chat-dataset"]
#: Evaluators used when none are named explicitly.
DEFAULT_EVALUATORS = ["summary"]


def _make_generator(args) -> object:
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
            cfg = resolve_endpoint(args.base_url, args.api_key, args.model)
        except ConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(2)
        try:
            from .generators.openai_compat import OpenAICompatible
        except ModuleNotFoundError:
            print(
                "error: the 'openai' package is not installed; "
                "run `uv sync` or `pip install openai` (or use --generator mock offline)",
                file=sys.stderr,
            )
            sys.exit(2)
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
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


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
    return Runner(generator, detectors=detectors, workers=args.workers, log_file=log_file)


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
            print(f"error: {e}", file=sys.stderr)
            return 2
    runner = _runner(args)
    probe_kwargs = _probe_kwargs(args, probe_names)

    evaluators = [e.strip() for e in (args.evaluators or "").split(",") if e.strip()]
    evaluator_names = evaluators or DEFAULT_EVALUATORS
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
        print(f"[DRY RUN] {len(attempts)} attempt(s) would be generated across probes: {probe_names}")
        for a in attempts[:50]:
            print(f"  would query {a.source}:{a.context.get('line', '')} ({a.probe})")
        if len(attempts) > 50:
            print(f"  … and {len(attempts) - 50} more")
        return 0

    run_info = vars(info) | run_info_extra | {"run_info": info}
    runner.evaluate(attempts, run_info, evaluator_names)
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


def _generator_args(p: argparse.ArgumentParser, include_model: bool = True) -> None:
    p.add_argument("--generator", default="openai", help="openai | mock | any registered generator")
    if include_model:
        p.add_argument("--base-url", help="OpenAI-compatible endpoint (env VHARNESS_BASE_URL)")
        p.add_argument("--api-key", help="API key (env VHARNESS_API_KEY / OPENAI_API_KEY)")
        p.add_argument("--model", help="model name (env VHARNESS_MODEL)")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--max-retries", type=int, default=3)
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--cache-file", default=None)
    p.add_argument("--log-file", default=None, help="JSONL run log (default: scan_log.jsonl for run, off for list)")
    p.add_argument("--no-log", action="store_true")
    p.add_argument("--mock-script", action="append", default=[], metavar="KEY=REPLY",
                   help="mock generator: exact-substring key → canned reply (repeatable)")


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
    scan_p.add_argument("--exclude", action="append", default=[])
    _generator_args(scan_p)
    scan_p.set_defaults(func=cmd_scan, log_file="scan_log.jsonl")

    eval_p = sub.add_parser("eval", help="preset: score a model on labeled data")
    eval_p.add_argument("--corpus-dir", default=None)
    eval_p.add_argument("--dataset", default=None, help="chat-format JSONL with code samples")
    eval_p.add_argument("--limit", type=int, default=None)
    eval_p.add_argument("--skip-corpus", action="store_true")
    eval_p.add_argument("--metrics-out", default="eval_metrics.json")
    _generator_args(eval_p)
    eval_p.set_defaults(func=cmd_eval)

    list_p = sub.add_parser("list", help="list registered plugins")
    list_p.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
