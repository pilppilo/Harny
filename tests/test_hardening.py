"""Regression coverage for the 2026-09-03 hardening milestone."""

import json

import pytest

from vharness.core import Attempt, Finding, Generation, PluginRegistry, load_entry_points
from vharness.detectors.json_verdict import JSONVerdict, _normalize_cwe
from vharness.sarif import build_sarif, write_sarif


def _attempt(reply: str) -> Attempt:
    attempt = Attempt(prompt="p", source="source.py")
    attempt.record(Generation(text=reply))
    JSONVerdict().detect(attempt)
    return attempt


def test_vulnerable_verdict_requires_a_valid_finding():
    empty = _attempt('{"has_vulnerability": true, "vulnerabilities": []}')
    invalid = _attempt('{"has_vulnerability": true, "vulnerabilities": [{"cwe": "nope"}]}')
    mixed = _attempt('{"has_vulnerability": true, "vulnerabilities": [{"cwe": "nope"}, {"cwe": 78, "explanation": "x"}]}')
    clean = _attempt('{"has_vulnerability": false, "vulnerabilities": []}')

    assert (empty.status, empty.verdict, empty.findings) == ("parse_error", "unparseable", [])
    assert (invalid.status, invalid.verdict, invalid.findings) == ("parse_error", "unparseable", [])
    assert mixed.status == "ok" and mixed.verdict == "vulnerable" and len(mixed.findings) == 1
    assert clean.status == "ok" and clean.verdict == "clean"


@pytest.mark.parametrize("value, expected", [
    (78, "CWE-78"), ("78", "CWE-78"), ("CWE-79", "CWE-79"),
    ("CWE 89 SQL injection", "CWE-89"), (0, None), (-1, None), (10000, None),
    (True, None), (1.0, None), (None, None), ("not-a-cwe", None),
])
def test_cwe_normalization(value, expected):
    assert _normalize_cwe(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, ""), ("", ""), (42, ""), ([], ""), ({}, ""), ("  value  ", "value"),
])
def test_optional_finding_text_is_not_stringified(value, expected):
    reply = json.dumps({"has_vulnerability": True, "vulnerabilities": [{
        "cwe": "CWE-78", "explanation": "x", "sink": value, "patch": value,
    }]})
    finding = _attempt(reply).findings[0]
    assert finding.sink == expected and finding.patch == expected


def _finding(cwe, severity):
    return Finding(cwe=cwe, severity=severity, sink="x", explanation="x", file="x", line=1)


def test_sarif_rule_indices_and_unknown_severity_are_stable(tmp_path):
    findings = [_finding("CWE-79", "Low"), _finding("CWE-22", "unknown"), _finding("CWE-79", "High")]
    sarif = build_sarif(findings)
    rules = sarif["runs"][0]["tool"]["driver"]["rules"]
    results = sarif["runs"][0]["results"]
    assert [rule["id"] for rule in rules] == ["CWE-22", "CWE-79"]
    assert all(rules[result["ruleIndex"]]["id"] == result["ruleId"] for result in results)
    assert rules[0]["properties"]["security-severity"] == "5.0"
    assert rules[1]["properties"]["security-severity"] == "9.0"
    path = tmp_path / "nested" / "report.sarif"
    write_sarif(findings, str(path))
    assert path.is_file()


def test_entry_points_are_idempotent_and_failures_are_contained(monkeypatch, caplog):
    import vharness.core as core

    class Component:
        name = "entry-point-test"
        registry = PluginRegistry("test")

    class EntryPoint:
        group = "vharness.plugins"
        name = "test"
        value = "test:component"

        def load(self):
            return Component

    class BrokenEntryPoint(EntryPoint):
        name = "broken"
        value = "broken:component"

        def load(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("importlib.metadata.entry_points", lambda **_kwargs: [EntryPoint(), BrokenEntryPoint()])
    core._LOADED_ENTRY_POINTS.clear()
    load_entry_points()
    load_entry_points()
    assert Component.registry.names() == ["entry-point-test"]
    assert "broken" in caplog.text
    core._LOADED_ENTRY_POINTS.clear()


def test_project_generic_run_uses_run_local_outputs_and_effective_inputs(tmp_path, monkeypatch):
    from vharness.cli import main
    from vharness.workspace import initialize_project, list_runs

    project = initialize_project(tmp_path / "project", add_gitignore=False)
    monkeypatch.chdir(tmp_path)
    assert main([
        "run", "--project", str(project.root), "--probes", " corpus , ", "--limit", "1",
        "--evaluators", " json , metrics ", "--detectors", " json-verdict ", "--generator", "mock",
    ]) == 0
    run = list_runs(project)[0]
    run_dir = project.runs_dir / run["run_id"]
    assert (run_dir / "reports" / "report.json").is_file()
    assert (run_dir / "reports" / "eval_metrics.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    assert not (tmp_path / "report.json").exists()
    assert not (tmp_path / "eval_metrics.json").exists()
    metadata = json.loads((run_dir / "run.json").read_text())
    assert metadata["inputs"]["probes"] == ["corpus"]
    assert metadata["inputs"]["detectors"] == ["json-verdict"]
    assert metadata["inputs"]["evaluators"] == ["json", "metrics"]


def test_runner_keeps_discovery_order_and_logs_indices(tmp_path):
    import time

    from vharness.generators.base import Generator
    from vharness.runner import Runner
    from vharness.core import PROBE_REGISTRY

    class ReverseCompletion(Generator):
        name = "reverse"

        def generate(self, _system, prompt):
            time.sleep(0.02 if "CWE-78" in prompt else 0.0)
            return Generation(text='{"has_vulnerability": false, "vulnerabilities": []}')

    log = tmp_path / "run.jsonl"
    expected_sources = [attempt.source for attempt in PROBE_REGISTRY.instantiate("corpus").attempts(limit=4)]
    attempts, _info = Runner(ReverseCompletion(), workers=4, log_file=str(log)).run(["corpus"], {"limit": 4})
    assert [attempt.source for attempt in attempts] == expected_sources
    records = [json.loads(line) for line in log.read_text().splitlines() if '"type": "attempt"' in line]
    assert sorted(record["attempt_index"] for record in records) == list(range(4))


@pytest.mark.parametrize("offset", [300, 2000, 3900])
def test_routing_uses_full_four_kib_header(tmp_path, offset):
    from vharness.probes.domains import DistroConfProbe, route_file

    path = tmp_path / f"late-{offset}.service"
    path.write_bytes(b"#" * offset + b"\n[Unit]\nDescription=test\n")
    probe = DistroConfProbe()
    assert probe.attempts(targets=[str(path)])
    assert route_file(str(path)) == "distroconf"


def test_name_normalization_accepts_cli_and_programmatic_forms():
    from vharness.core import normalize_names
    from vharness.generators.mock import Mock
    from vharness.runner import Runner

    assert normalize_names(" a, ,b ", ["default"]) == ["a", "b"]
    assert normalize_names([" a ", "", "b"], ["default"]) == ["a", "b"]
    assert normalize_names(",,", ["default"]) == ["default"]
    attempts, _ = Runner(Mock(), detectors="json-verdict", workers=1).run(["corpus"], {"limit": 1})
    assert attempts[0].status == "ok"


def test_all_report_writers_create_nested_output_directories(tmp_path):
    from vharness.evaluators.metrics import MetricsReport
    from vharness.evaluators.reports import JsonReport, MarkdownReport, SarifReport

    attempt = Attempt(prompt="p")
    attempt.findings = [_finding("CWE-78", "High")]
    base = tmp_path / "nested" / "reports" / "report"
    info = {
        "out": str(base), "metrics_out": str(tmp_path / "nested" / "metrics" / "m.json"),
    }
    SarifReport().evaluate([attempt], info)
    MarkdownReport().evaluate([attempt], info)
    JsonReport().evaluate([attempt], info)
    MetricsReport().evaluate([attempt], info)
    assert (tmp_path / "nested" / "reports" / "report.sarif").is_file()
    assert (tmp_path / "nested" / "reports" / "report.md").is_file()
    assert (tmp_path / "nested" / "reports" / "report.json").is_file()
    assert (tmp_path / "nested" / "metrics" / "m.json").is_file()


def test_generator_summary_is_captured_after_a_real_run_and_not_for_dry_run(caplog):
    import logging
    from vharness.cli import main
    from vharness.core import GENERATOR_REGISTRY
    from vharness.generators.base import Generator

    constructed = []

    class TelemetryGenerator(Generator):
        name = "telemetry-test"
        help = "test telemetry"

        def __init__(self):
            constructed.append(True)

        def generate(self, _system, _prompt):
            return Generation(text='{"has_vulnerability": false, "vulnerabilities": []}')

        def summary(self):
            return "queries=1 tokens=12"

    GENERATOR_REGISTRY.register(TelemetryGenerator)
    try:
        with caplog.at_level(logging.INFO, logger="vharness"):
            assert main(["run", "--probes", "corpus", "--limit", "1", "--generator", "telemetry-test", "--no-log"]) == 0
        assert "generator: queries=1 tokens=12" in caplog.text
        constructed.clear()
        assert main(["run", "--probes", "corpus", "--limit", "1", "--generator", "telemetry-test", "--dry-run", "--no-log"]) == 0
        assert constructed == []
    finally:
        del GENERATOR_REGISTRY._items["telemetry-test"]
        GENERATOR_REGISTRY._instances.pop("telemetry-test", None)


def test_openai_generator_telemetry_is_exact_under_concurrency(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    import vharness.generators.openai_compat as module

    class Completions:
        def create(self, **kwargs):
            prompt = kwargs["messages"][1]["content"]
            if prompt == "bad":
                raise RuntimeError("terminal")
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3),
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"), finish_reason="stop")],
            )

    class Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(module, "OpenAI", Client)
    generator = module.OpenAICompatible("https://example/v1", "model", cache_path=str(tmp_path / "cache.sqlite3"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda prompt: generator.generate("system", prompt), [str(i) for i in range(10)] + ["bad"]))
    assert sum(result.ok for result in results) == 10
    assert generator.generate("system", "0").cached
    assert generator.stats["queries"] == 11
    assert generator.stats["cache_hits"] == 1
    assert generator.stats["api_errors"] == 1
    assert generator.stats["prompt_tokens"] == 20
    assert generator.stats["completion_tokens"] == 30
    assert "queries=11 cache_hits=1 api_errors=1 tokens=50" in generator.summary()
    generator.close()
