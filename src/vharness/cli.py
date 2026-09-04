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
from pathlib import Path

from . import VERSION
from .config import ConfigError, resolve_endpoint
from .core import (
    DETECTOR_REGISTRY,
    EVALUATOR_REGISTRY,
    GENERATOR_REGISTRY,
    PROBE_REGISTRY,
    load_entry_points,
    normalize_names,
)
from .log import log, setup as log_setup
from .runner import Runner
from .skills import SkillError, load_skills
from .workspace import (
    WorkspaceError,
    create_run,
    initialize_project,
    list_runs,
    resolve_project,
    update_run,
)

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

    def summary_if_initialized(self) -> str:
        if self._inner is None:
            return ""
        summary = getattr(self._inner, "summary", None)
        return summary() if callable(summary) else ""


def _runner(args) -> Runner:
    generator = _LazyGenerator(args)
    detectors = normalize_names(getattr(args, "_detector_names", None), ["json-verdict"])
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
    return kw


def _normalize_workflow(args) -> None:
    """Resolve CLI selections once for execution and persisted provenance."""
    try:
        probes = normalize_names(getattr(args, "probes", None), [], field="probes")
        detectors = normalize_names(
            getattr(args, "detectors", None), ["json-verdict"], field="detectors"
        )
        evaluators = normalize_names(
            getattr(args, "evaluators", None), ["summary"], field="evaluators"
        )
    except ValueError as exc:
        raise CLIError(str(exc)) from exc
    if getattr(args, "skip_corpus", False):
        probes = [name for name in probes if name != "corpus"]
    if not probes:
        raise CLIError("no probes selected")
    args._probe_names = probes
    args._detector_names = detectors
    args._evaluator_names = evaluators


def _project_inputs(args, workflow: str) -> dict:
    """Persist only non-secret, normalized launch context in project metadata."""
    fields = (
        "targets", "analyzers", "format", "dataset", "corpus_dir", "limit",
        "exclude", "generator", "model", "profile", "dry_run", "workers",
    )
    inputs = {field: getattr(args, field) for field in fields if getattr(args, field, None) is not None}
    inputs["probes"] = list(args._probe_names)
    inputs["detectors"] = list(args._detector_names)
    inputs["evaluators"] = list(args._evaluator_names)
    inputs["skip_corpus"] = bool(getattr(args, "skip_corpus", False))
    inputs["workflow"] = workflow
    return inputs


def _begin_project_run(args, workflow: str):
    project_path = getattr(args, "project", None)
    if not project_path:
        return None
    launch_cwd = Path.cwd().resolve()
    try:
        project = resolve_project(project_path)
        if not getattr(args, "profile", None) and project.default_profile:
            args.profile = project.default_profile
        run = create_run(project, workflow, _project_inputs(args, workflow))
    except WorkspaceError as exc:
        raise CLIError(str(exc)) from exc

    explicit_outputs = {
        field: str(getattr(args, field))
        for field in ("log_file", "out", "sarif_out", "markdown_out", "json_out", "metrics_out")
        if getattr(args, field, None)
    }
    # Project mode owns only defaults. Explicit output paths remain untouched.
    if not getattr(args, "no_log", False) and not getattr(args, "log_file", None):
        args.log_file = str(run.events_path)
    if not getattr(args, "out", None):
        args.out = str(run.reports_dir / "report")
    if not getattr(args, "metrics_out", None):
        args.metrics_out = str(run.reports_dir / "eval_metrics.json")

    def provenance(requested: str, ownership: str) -> dict[str, str]:
        candidate = Path(requested).expanduser()
        absolute = candidate if candidate.is_absolute() else launch_cwd / candidate
        resolved = absolute.resolve(strict=False)
        if ownership != "project_default":
            try:
                resolved.relative_to(project.root.resolve())
            except ValueError:
                ownership = "explicit_external"
            else:
                ownership = "explicit_project"
        return {"requested": requested, "resolved": str(resolved), "ownership": ownership}

    outputs: dict[str, object] = {
        "run_dir": str(run.path),
        "reports_dir": str(run.reports_dir),
        "launch_cwd": str(launch_cwd),
        "output_provenance": {},
    }
    for field in ("log_file", "out", "sarif_out", "markdown_out", "json_out", "metrics_out"):
        value = getattr(args, field, None)
        if value:
            outputs[field] = str(value)
            requested = explicit_outputs.get(field)
            outputs["output_provenance"][field] = provenance(
                requested or str(value),
                "explicit_external" if requested is not None else "project_default",
            )
    try:
        update_run(run, status="running", outputs=outputs)
    except WorkspaceError as exc:  # pragma: no cover - filesystem failures are platform-specific
        raise CLIError(str(exc)) from exc
    log.info("project %s: run %s (%s)", project.name, run.run_id, workflow)
    return run


def _finish_project_run(run, code: int, *, stop_reason: str | None = None) -> None:
    if run is None:
        return
    status = "completed" if code == 0 else "failed"
    try:
        update_run(run, status=status, exit_code=code, stop_reason=stop_reason)
    except WorkspaceError as exc:  # pragma: no cover - filesystem failures are platform-specific
        log.error("could not update project run %s: %s", run.run_id, exc)


def cmd_run(args) -> int:
    workflow = getattr(args, "command", "run")
    _normalize_workflow(args)
    if workflow == "run" and not getattr(args, "project", None):
        args.log_file = args.log_file or "scan_log.jsonl"
    project_run = _begin_project_run(args, workflow) if workflow in {"run", "scan", "eval"} else None
    try:
        code = _cmd_run(args)
    except KeyboardInterrupt:
        if project_run is not None:
            try:
                update_run(project_run, status="cancelled", stop_reason="operator_interrupt")
            except WorkspaceError as exc:  # pragma: no cover - filesystem failures are platform-specific
                log.error("could not update cancelled project run %s: %s", project_run.run_id, exc)
        raise
    except Exception:
        _finish_project_run(project_run, 1, stop_reason="error")
        raise
    _finish_project_run(
        project_run,
        code,
        stop_reason="dry_run" if getattr(args, "dry_run", False) else ("fail_on_findings" if code else "complete"),
    )
    return code


def _cmd_run(args) -> int:
    load_entry_points()
    probe_names = list(args._probe_names)
    for p in probe_names:
        try:
            PROBE_REGISTRY.get(p)
        except KeyError as e:
            raise CLIError(str(e)) from e
    detector_names = list(args._detector_names)
    for detector in detector_names:
        try:
            DETECTOR_REGISTRY.get(detector)
        except KeyError as e:
            raise CLIError(str(e)) from e
    evaluator_names = list(args._evaluator_names)
    for evaluator in evaluator_names:
        try:
            EVALUATOR_REGISTRY.get(evaluator)
        except KeyError as e:
            raise CLIError(str(e)) from e
    runner = _runner(args)
    probe_kwargs = _probe_kwargs(args, probe_names)

    run_info_extra = {
        "out": getattr(args, "out", None),
        "sarif_out": getattr(args, "sarif_out", None),
        "markdown_out": getattr(args, "markdown_out", None),
        "json_out": getattr(args, "json_out", None),
        "metrics_out": getattr(args, "metrics_out", None),
        "generator_summary": "",
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

    run_info_extra["generator_summary"] = (
        runner.generator.summary_if_initialized()
        if isinstance(runner.generator, _LazyGenerator)
        else getattr(runner.generator, "summary", lambda: "")()
    )

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
    if not args.project:
        args.out = args.out or "report"
        args.log_file = args.log_file or "scan_log.jsonl"
    return cmd_run(args)


def cmd_eval(args) -> int:
    args.probes = "corpus"
    if getattr(args, "dataset", None):
        args.probes = "corpus,chat-dataset"
    if getattr(args, "skip_corpus", False):
        args.probes = "chat-dataset"
    args.evaluators = "metrics,summary"
    if not args.project:
        args.log_file = args.log_file or "eval_log.jsonl"
        args.metrics_out = args.metrics_out or "eval_metrics.json"
    return cmd_run(args)


def cmd_project_init(args) -> int:
    try:
        project = initialize_project(
            args.path,
            name=args.name,
            default_profile=args.default_profile,
            add_gitignore=not args.no_gitignore,
        )
    except WorkspaceError as exc:
        raise CLIError(str(exc)) from exc
    print(f"Initialized Vharness project: {project.name}")
    print(f"  manifest: {project.manifest_path}")
    print(f"  local state: {project.state_dir}")
    return 0


def cmd_project_status(args) -> int:
    try:
        project = resolve_project(args.project)
        runs = list_runs(project)
    except WorkspaceError as exc:
        raise CLIError(str(exc)) from exc
    statuses: dict[str, int] = {}
    for run in runs:
        status = run.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    print(f"Project: {project.name}")
    print(f"Root:    {project.root}")
    print(f"Manifest: {project.manifest_path}")
    print(f"State:   {project.state_dir}")
    print(f"Sources: {', '.join(project.source_roots)}")
    if project.default_profile:
        print(f"Default profile: {project.default_profile}")
    suffix = " (" + ", ".join(f"{key}={value}" for key, value in sorted(statuses.items())) + ")" if runs else ""
    print(f"Runs: {len(runs)}{suffix}")
    return 0


def cmd_project_runs(args) -> int:
    try:
        project = resolve_project(args.project)
        runs = list_runs(project)
    except WorkspaceError as exc:
        raise CLIError(str(exc)) from exc
    if args.json:
        print(json.dumps(runs, indent=2))
        return 0
    if not runs:
        print("No project runs.")
        return 0
    print("RUN ID\tWORKFLOW\tSTATUS\tCREATED")
    for run in runs:
        print("\t".join(str(run.get(field, "-")) for field in ("run_id", "workflow", "status", "created_at")))
    return 0


def cmd_list(args) -> int:
    load_entry_points()
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


def cmd_usage(args) -> int:
    """Show locally recorded token usage for the resolved endpoint/model."""
    try:
        cfg, src = resolve_endpoint(
            args.base_url, args.api_key, args.model,
            profile=args.profile,
            config_file=args.config_file,
        )
    except ConfigError as e:
        raise CLIError(str(e)) from e

    from .usage import read_usage

    paths = args.log_files or [p for p in ("scan_log.jsonl", "eval_log.jsonl") if os.path.isfile(p)]
    missing = [path for path in args.log_files if not os.path.isfile(path)]
    if missing:
        raise CLIError(f"usage log not found or unreadable: {missing[0]}")
    summaries = read_usage(
        paths,
        provider=cfg.base_url,
        model=cfg.model,
        all_models=args.all_models,
    )
    payload = {
        "current_provider": cfg.base_url,
        "current_model": cfg.model,
        "config_source": src,
        "usage": [summary.to_dict() for summary in summaries],
        "account_quota": "unavailable: OpenAI-compatible APIs have no standard quota endpoint",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Current provider: {cfg.base_url}")
    print(f"Current model:    {cfg.model}")
    print(f"Config source:    {src}")
    if not paths:
        print("\nNo local run logs found. Supply --log-file PATH after running scan, eval, or run.")
    elif not summaries:
        print("\nNo recorded usage matches the current provider/model in the selected logs.")
    else:
        print("\nLocally recorded usage:")
        for summary in summaries:
            print(f"  {summary.provider}  {summary.model}")
            print(
                f"    attempts={summary.attempts} completed={summary.completed_requests} "
                f"cache_hits={summary.cache_hits} api_errors={summary.api_errors}"
            )
            print(
                f"    tokens={summary.total_tokens} "
                f"(prompt={summary.prompt_tokens}, completion={summary.completion_tokens}) "
                f"latency_p50={summary.latency_p50:.2f}s"
            )
            if summary.responses_without_usage:
                print(f"    usage unavailable in {summary.responses_without_usage} response(s)")
    print("\nAccount quota/remaining credits: unavailable through the generic OpenAI-compatible API.")
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
    run_p.add_argument("--project", help="explicit Vharness project directory")
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
    run_p.set_defaults(func=cmd_run, log_file=None)

    scan_p = sub.add_parser("scan", help="preset: scan code with all code-domain probes")
    scan_p.add_argument("targets", nargs="+")
    scan_p.add_argument("--project", help="explicit Vharness project directory")
    scan_p.add_argument("--analyzers", default=None, help="restrict to comma list (ccpp,web,shell,distroconf)")
    scan_p.add_argument("--format", default="sarif,markdown", help="comma list: sarif,markdown,json,summary")
    scan_p.add_argument("--out", default=None)
    scan_p.add_argument("--dry-run", action="store_true")
    scan_p.add_argument("--exclude", action="append", default=[], help="dir name to skip (repeatable)")
    _generator_args(scan_p)
    scan_p.set_defaults(func=cmd_scan, log_file=None)

    eval_p = sub.add_parser("eval", help="preset: score a model on labeled data")
    eval_p.add_argument("--project", help="explicit Vharness project directory")
    eval_p.add_argument("--corpus-dir", default=None)
    eval_p.add_argument("--dataset", default=None, help="chat-format JSONL with code samples")
    eval_p.add_argument("--limit", type=int, default=None)
    eval_p.add_argument("--skip-corpus", action="store_true")
    eval_p.add_argument("--metrics-out", default=None)
    _generator_args(eval_p)
    eval_p.set_defaults(func=cmd_eval, log_file=None)

    project_p = sub.add_parser("project", help="initialize and inspect local Vharness projects")
    project_sub = project_p.add_subparsers(dest="project_command", required=True)
    project_init_p = project_sub.add_parser("init", help="create a project manifest and local state directory")
    project_init_p.add_argument("path", nargs="?", default=".")
    project_init_p.add_argument("--name", default=None, help="display name (default: directory name)")
    project_init_p.add_argument("--default-profile", default=None, help="non-secret config profile name")
    project_init_p.add_argument("--no-gitignore", action="store_true", help="do not add .vharness/ to .gitignore")
    project_init_p.set_defaults(func=cmd_project_init)
    project_status_p = project_sub.add_parser("status", help="show project metadata and run counts")
    project_status_p.add_argument("--project", required=True, help="project directory")
    project_status_p.set_defaults(func=cmd_project_status)
    project_runs_p = project_sub.add_parser("runs", help="list persisted project runs")
    project_runs_p.add_argument("--project", required=True, help="project directory")
    project_runs_p.add_argument("--json", action="store_true", help="emit JSON")
    project_runs_p.set_defaults(func=cmd_project_runs)

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

    usage_p = sub.add_parser("usage", help="show locally recorded usage for the current endpoint/model")
    usage_p.add_argument("--base-url", help="OpenAI-compatible endpoint (env VHARNESS_BASE_URL, config profile)")
    usage_p.add_argument("--api-key", help="API key (only used to resolve the configured provider)")
    usage_p.add_argument("--model", help="model name (env VHARNESS_MODEL, config profile)")
    usage_p.add_argument("--profile", default=None, help="named configuration profile")
    usage_p.add_argument("--config", dest="config_file", default=None, help="configuration file path")
    usage_p.add_argument("--log-file", dest="log_files", action="append", default=[], metavar="PATH",
                         help="JSONL run log to include (repeatable; defaults to local scan/eval logs)")
    usage_p.add_argument("--all-models", action="store_true", help="show every provider/model found in selected logs")
    usage_p.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    usage_p.set_defaults(func=cmd_usage)

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
