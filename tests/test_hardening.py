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
    ("10000", None), ("0", None), ("-1", None), ("release 42 notes", None),
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


def test_entry_point_failure_rolls_back_partial_registration_and_can_retry(monkeypatch):
    import vharness.core as core

    registry = PluginRegistry("test")
    should_fail = True

    class Component:
        name = "partial-component"

    Component.registry = registry

    class Plugin:
        @staticmethod
        def register_plugins():
            registry.register(Component)
            registry.instantiate(Component.name)
            if should_fail:
                raise RuntimeError("after registration")

    class EntryPoint:
        group = "vharness.plugins"
        name = "partial"
        value = "partial:plugin"

        def load(self):
            return Plugin

    monkeypatch.setattr("importlib.metadata.entry_points", lambda **_kwargs: [EntryPoint()])
    core._LOADED_ENTRY_POINTS.clear()
    load_entry_points()
    assert registry.names() == []
    assert not hasattr(registry, "_instances")
    should_fail = False
    load_entry_points()
    assert registry.names() == ["partial-component"]
    core._LOADED_ENTRY_POINTS.clear()


def test_entry_point_activation_is_serialized_across_concurrent_loaders(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    import vharness.core as core

    registry = PluginRegistry("test")
    activations = []

    class Component:
        name = "concurrent-component"

    Component.registry = registry

    class Plugin:
        @staticmethod
        def register_plugins():
            activations.append(True)
            registry.register(Component)

    class EntryPoint:
        group = "vharness.plugins"
        name = "concurrent"
        value = "concurrent:plugin"

        def load(self):
            return Plugin

    monkeypatch.setattr("importlib.metadata.entry_points", lambda **_kwargs: [EntryPoint()])
    core._LOADED_ENTRY_POINTS.clear()
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: load_entry_points(), range(8)))
    assert registry.names() == ["concurrent-component"]
    assert len(activations) == 1
    core._LOADED_ENTRY_POINTS.clear()


def test_list_discovers_entry_point_plugins(monkeypatch, capsys):
    import vharness.core as core
    from vharness.cli import main
    from vharness.core import DETECTOR_REGISTRY

    class Component:
        name = "listed-entry-point"
        registry = DETECTOR_REGISTRY
        help = "listed test plugin"

    class EntryPoint:
        group = "vharness.plugins"
        name = "listed"
        value = "listed:component"

        def load(self):
            return Component

    monkeypatch.setattr("importlib.metadata.entry_points", lambda **_kwargs: [EntryPoint()])
    core._LOADED_ENTRY_POINTS.clear()
    try:
        assert main(["list"]) == 0
        assert "listed-entry-point" in capsys.readouterr().out
    finally:
        DETECTOR_REGISTRY._items.pop("listed-entry-point", None)
        core._LOADED_ENTRY_POINTS.clear()


def test_project_generic_run_uses_run_local_outputs_and_effective_inputs(tmp_path, monkeypatch):
    from vharness.cli import main
    from vharness.workspace import initialize_project, list_runs

    project = initialize_project(tmp_path / "project", add_gitignore=False)
    monkeypatch.chdir(tmp_path)
    assert main([
        "run", "--project", str(project.root), "--probes", " corpus , ", "--limit", "1",
        "--evaluators", " json , sarif , markdown , metrics ", "--detectors", " json-verdict ", "--generator", "mock",
    ]) == 0
    run = list_runs(project)[0]
    run_dir = project.runs_dir / run["run_id"]
    assert (run_dir / "reports" / "report.json").is_file()
    assert (run_dir / "reports" / "report.sarif").is_file()
    assert (run_dir / "reports" / "report.md").is_file()
    assert (run_dir / "reports" / "eval_metrics.json").is_file()
    assert (run_dir / "events.jsonl").is_file()
    assert not (tmp_path / "report.json").exists()
    assert not (tmp_path / "eval_metrics.json").exists()
    metadata = json.loads((run_dir / "run.json").read_text())
    assert metadata["inputs"]["probes"] == ["corpus"]
    assert metadata["inputs"]["detectors"] == ["json-verdict"]
    assert metadata["inputs"]["evaluators"] == ["json", "sarif", "markdown", "metrics"]


def test_project_output_provenance_records_canonical_ownership(tmp_path, monkeypatch):
    from vharness.cli import main
    from vharness.workspace import initialize_project, list_runs

    project = initialize_project(tmp_path / "project", add_gitignore=False)
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "linked-output").symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    assert main([
        "run", "--project", str(project.root), "--probes", "corpus", "--limit", "1",
        "--evaluators", "json", "--generator", "mock", "--out", "project/custom/report",
    ]) == 0
    first = json.loads((project.runs_dir / list_runs(project)[0]["run_id"] / "run.json").read_text())
    first_out = first["outputs"]["output_provenance"]["out"]
    assert first_out == {
        "requested": "project/custom/report",
        "resolved": str((project.root / "custom" / "report").resolve()),
        "ownership": "explicit_project",
    }
    assert first["outputs"]["launch_cwd"] == str(tmp_path.resolve())

    assert main([
        "run", "--project", str(project.root), "--probes", "corpus", "--limit", "1",
        "--evaluators", "json", "--generator", "mock", "--out", str(project.root / "linked-output" / "report"),
    ]) == 0
    second = json.loads((project.runs_dir / list_runs(project)[0]["run_id"] / "run.json").read_text())
    second_out = second["outputs"]["output_provenance"]["out"]
    assert second_out["ownership"] == "explicit_external"
    assert second_out["resolved"] == str((outside / "report").resolve())

    explicit = {
        "log_file": outside / "events.jsonl",
        "out": outside / "base" / "report",
        "sarif_out": outside / "report.sarif",
        "markdown_out": outside / "report.md",
        "json_out": outside / "report.json",
        "metrics_out": outside / "metrics.json",
    }
    assert main([
        "run", "--project", str(project.root), "--probes", "corpus", "--limit", "1",
        "--evaluators", "json,sarif,markdown,metrics", "--generator", "mock",
        "--log-file", str(explicit["log_file"]), "--out", str(explicit["out"]),
        "--sarif-out", str(explicit["sarif_out"]), "--markdown-out", str(explicit["markdown_out"]),
        "--json-out", str(explicit["json_out"]), "--metrics-out", str(explicit["metrics_out"]),
    ]) == 0
    third = json.loads((project.runs_dir / list_runs(project)[0]["run_id"] / "run.json").read_text())
    for field, path in explicit.items():
        assert third["outputs"]["output_provenance"][field] == {
            "requested": str(path), "resolved": str(path.resolve()), "ownership": "explicit_external",
        }


def test_project_scan_and_eval_record_effective_workflows(tmp_path):
    from vharness.cli import main
    from vharness.workspace import initialize_project, list_runs

    project = initialize_project(tmp_path / "project", add_gitignore=False)
    source = tmp_path / "sample.py"
    source.write_text("print('hello')\n")
    assert main(["scan", str(source), "--project", str(project.root), "--generator", "mock", "--format", "json", "-q"]) == 0
    assert main(["eval", "--project", str(project.root), "--generator", "mock", "--limit", "1", "-q"]) == 0
    runs = {run["workflow"]: run for run in list_runs(project)}
    assert runs["scan"]["inputs"]["probes"] == ["ccpp", "web", "shell", "distroconf"]
    assert runs["scan"]["inputs"]["evaluators"] == ["json"]
    assert runs["eval"]["inputs"]["probes"] == ["corpus"]
    assert runs["eval"]["inputs"]["skip_corpus"] is False


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


def test_runner_surfaces_attempt_log_failure_as_run_failure(tmp_path):
    from vharness.generators.mock import Mock
    from vharness.runner import RunPersistenceError, Runner

    runner = Runner(Mock(), workers=1, log_file=str(tmp_path / "run.jsonl"))
    original_log = runner._log
    seen = []

    def fail_once(attempt, info, attempt_index):
        if not seen:
            seen.append("failed")
            raise OSError("disk full")
        seen.append(attempt.status)
        original_log(attempt, info, attempt_index)

    runner._log = fail_once
    with pytest.raises(RunPersistenceError, match="durably record"):
        runner.run(["corpus"], {"limit": 1})
    assert seen == ["failed", "internal_error"]


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
    with pytest.raises(ValueError, match="detectors must contain only strings"):
        normalize_names(["json-verdict", 42], ["json-verdict"], field="detectors")
    with pytest.raises(ValueError, match="probes must be"):
        normalize_names({"corpus": True}, [], field="probes")


def test_false_verdict_rejects_nonempty_or_nonlist_vulnerabilities():
    invalid = _attempt('{"has_vulnerability": false, "vulnerabilities": [{"cwe": "nope"}]}')
    nonlist = _attempt('{"has_vulnerability": false, "vulnerabilities": {}}')
    assert (invalid.status, invalid.verdict) == ("parse_error", "unparseable")
    assert (nonlist.status, nonlist.verdict) == ("parse_error", "unparseable")


def test_cli_rejects_unknown_detector_and_evaluator(capsys):
    from vharness.cli import main

    assert main(["run", "--probes", "corpus", "--detectors", "missing", "--generator", "mock"]) == 2
    assert "unknown detector" in capsys.readouterr().err
    assert main(["run", "--probes", "corpus", "--evaluators", "missing", "--generator", "mock"]) == 2
    assert "unknown evaluator" in capsys.readouterr().err


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


def test_openai_generation_accumulates_retry_telemetry_on_terminal_error(monkeypatch):
    from types import SimpleNamespace

    import vharness.generators.openai_compat as module

    class Completions:
        def __init__(self):
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("second request failed")
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3),
                choices=[SimpleNamespace(message=SimpleNamespace(content="partial"), finish_reason="length")],
            )

    class Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(module, "OpenAI", Client)
    generator = module.OpenAICompatible("https://example/v1", "model", max_retries=0)
    result = generator.generate("system", "prompt")
    assert result.error == "RuntimeError: second request failed"
    assert (result.prompt_tokens, result.completion_tokens) == (2, 3)
    assert result.latency > 0
    assert (generator.stats["prompt_tokens"], generator.stats["completion_tokens"]) == (2, 3)


def test_openai_generation_accumulates_multiple_length_retries(monkeypatch):
    from types import SimpleNamespace

    import vharness.generators.openai_compat as module

    class Completions:
        def __init__(self):
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            tokens = self.calls
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=tokens, completion_tokens=tokens + 1),
                choices=[SimpleNamespace(
                    message=SimpleNamespace(content=f"response-{tokens}"),
                    finish_reason="stop" if self.calls == 3 else "length",
                )],
            )

    class Client:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(module, "OpenAI", Client)
    generator = module.OpenAICompatible("https://example/v1", "model", max_retries=1)
    result = generator.generate("system", "prompt")
    assert result.ok and result.text == "response-3"
    assert (result.prompt_tokens, result.completion_tokens) == (6, 9)
    assert (generator.stats["prompt_tokens"], generator.stats["completion_tokens"]) == (6, 9)
