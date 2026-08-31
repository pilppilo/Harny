"""CLI: ``python -m vharness scan|eval``."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .analyzers import all_analyzers
from .config import ConfigError, resolve_endpoint
from .eval import (
    compute_metrics,
    eval_markdown,
    load_chat_dataset,
    load_corpus,
    run_eval,
    write_eval_report,
)
from .llm import LLMClient
from .report import terminal_summary, write_json, write_markdown
from .sarif import write_sarif
from .scanner import scan

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "eval_corpus")


def _endpoint_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-url", help="OpenAI-compatible endpoint (env VHARNESS_BASE_URL)")
    parser.add_argument("--api-key", help="API key (env VHARNESS_API_KEY, OPENAI_API_KEY)")
    parser.add_argument("--model", help="model name (env VHARNESS_MODEL)")
    parser.add_argument("--workers", type=int, default=4, help="concurrent queries (default 4)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--no-cache", action="store_true", help="bypass the response cache")
    parser.add_argument("--cache-file", default=None, help="cache path (default ~/.cache/vharness.sqlite3)")


def cmd_scan(args: argparse.Namespace) -> int:
    analyzers = {a.name for a in all_analyzers()}
    only: set[str] | None = None
    if args.analyzers:
        only = {s.strip() for s in args.analyzers.split(",") if s.strip()}
        unknown = only - analyzers
        if unknown:
            print(f"error: unknown analyzers {sorted(unknown)}; available: {sorted(analyzers)}", file=sys.stderr)
            return 2

    client: LLMClient | None = None
    if not args.dry_run:
        try:
            cfg = resolve_endpoint(args.base_url, args.api_key, args.model)
        except ConfigError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        cache = None if args.no_cache else (args.cache_file or os.path.expanduser("~/.cache/vharness.sqlite3"))
        if cache:
            os.makedirs(os.path.dirname(cache), exist_ok=True)
        client = LLMClient(cfg, timeout=args.timeout, max_retries=args.max_retries,
                           max_tokens=args.max_tokens, cache_path=cache)
        print(f"[*] Endpoint: {cfg.describe()}")

    print(f"[*] Scanning: {', '.join(args.targets)}  {'(dry run — no queries)' if args.dry_run else ''}")
    result = scan(
        args.targets, client,
        workers=args.workers,
        extra_excludes=args.exclude,
        only_analyzers=only,
        dry_run=args.dry_run,
        verbose=True,
    )

    if args.dry_run:
        plan = result.dry_run_plan or []
        print(f"\n[DRY RUN] {len(plan)} chunk(s) would be queried across {result.stats.files_analyzed} file(s).")
        return 0

    formats = [f.strip() for f in args.format.split(",") if f.strip()]
    for fmt in formats:
        if fmt == "sarif":
            out = args.out if len(formats) == 1 else args.out + ".sarif"
            write_sarif(result.findings, out)
        elif fmt == "markdown":
            out = args.out if len(formats) == 1 else args.out + ".md"
            write_markdown(result.findings, result.stats, out, title=f"vharness scan — {', '.join(args.targets)}")
        elif fmt == "json":
            out = args.out if len(formats) == 1 else args.out + ".json"
            write_json(result.findings, out)
        else:
            print(f"warning: unknown format {fmt!r} skipped", file=sys.stderr)
            continue
        print(f"[+] Wrote {out}")

    print(terminal_summary(result.findings, result.stats, client.stats.summary() if client else None))
    if result.stats.errors:
        print(f"\n[!] {len(result.stats.errors)} error(s) during scan (first 5):")
        for e in result.stats.errors[:5]:
            print(f"    {e}")
    if client:
        client.close()
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    samples = []
    if args.from_dataset:
        got, total = load_chat_dataset(args.from_dataset, args.limit)
        print(f"[*] dataset {args.from_dataset}: {total} records, {len(got)} usable code-analysis samples")
        samples.extend(got)
    if not args.skip_corpus:
        corpus_dir = args.corpus or CORPUS_DIR
        got = load_corpus(corpus_dir)
        print(f"[*] corpus {corpus_dir}: {len(got)} samples")
        samples.extend(got)
    if args.limit:
        samples = samples[: args.limit]
    if not samples:
        print("error: no eval samples found", file=sys.stderr)
        return 2

    try:
        cfg = resolve_endpoint(args.base_url, args.api_key, args.model)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    cache = None if args.no_cache else (args.cache_file or os.path.expanduser("~/.cache/vharness-eval.sqlite3"))
    client = LLMClient(cfg, timeout=args.timeout, max_retries=args.max_retries,
                       max_tokens=args.max_tokens, cache_path=cache)
    print(f"[*] Evaluating {len(samples)} samples against {cfg.describe()}")
    records = run_eval(client, samples)
    metrics = compute_metrics(records)
    print("\n" + eval_markdown(args.model or "fine-tuned", metrics, records))
    print(f"\n[*] endpoint stats: {client.stats.summary()}")

    sections = [eval_markdown(args.model or "fine-tuned", metrics, records)]

    if args.compare_base_url or args.compare_model:
        try:
            cfg2 = resolve_endpoint(args.compare_base_url, args.compare_api_key, args.compare_model)
        except ConfigError as e:
            print(f"error (compare): {e}", file=sys.stderr)
            return 2
        client2 = LLMClient(cfg2, timeout=args.timeout, max_retries=args.max_retries,
                            max_tokens=args.max_tokens, cache_path=cache)
        print(f"[*] Comparing against {cfg2.describe()}")
        records2 = run_eval(client2, samples)
        metrics2 = compute_metrics(records2)
        sections.append(eval_markdown(args.compare_model or "base", metrics2, records2))
        print("\n" + eval_markdown(args.compare_model or "base", metrics2))
        client2.close()

    report_path = args.report
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("# vharness eval\n\n" + "\n\n".join(sections))
    write_eval_report(report_path.replace(".md", "") + "_detail.json", records, metrics)
    print(f"\n[+] Wrote {report_path} and detail JSON")
    client.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vharness", description="LLM-powered vulnerability scanner + eval harness")
    parser.add_argument("--version", action="version", version=f"vharness {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_p = sub.add_parser("scan", help="scan directories for vulnerabilities")
    scan_p.add_argument("targets", nargs="+", help="directories or files to scan")
    scan_p.add_argument("--format", default="sarif,markdown", help="comma list: sarif,markdown,json (default sarif,markdown)")
    scan_p.add_argument("--out", default="report", help="output path/prefix (default 'report')")
    scan_p.add_argument("--analyzers", default=None, help="comma list to restrict domains (ccpp,web,shell,distroconf)")
    scan_p.add_argument("--dry-run", action="store_true", help="show what would be queried, make no API calls")
    scan_p.add_argument("--exclude", action="append", default=[], help="extra dir name to skip (repeatable)")
    scan_p.add_argument("-v", "--verbose", action="store_true")
    _endpoint_args(scan_p)
    scan_p.set_defaults(func=cmd_scan)

    eval_p = sub.add_parser("eval", help="score the endpoint on labeled samples")
    eval_p.add_argument("--corpus", default=None, help="labeled corpus dir (default: built-in)")
    eval_p.add_argument("--from-dataset", default=None, help="chat-format JSONL (OpenAI 'messages' schema) with code samples")
    eval_p.add_argument("--limit", type=int, default=None)
    eval_p.add_argument("--skip-corpus", action="store_true", help="only use --from-dataset samples")
    eval_p.add_argument("--report", default="eval_report.md")
    eval_p.add_argument("--compare-base-url", default=None, help="second endpoint for A/B (e.g. base model)")
    eval_p.add_argument("--compare-api-key", default=None)
    eval_p.add_argument("--compare-model", default=None)
    _endpoint_args(eval_p)
    eval_p.set_defaults(func=cmd_eval)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
