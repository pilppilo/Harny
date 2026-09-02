"""Runner behaviors: run log records, worker safety, replay."""

import json

import pytest

from vharness.core import Attempt, Generation
from vharness.generators.mock import Mock
from vharness.runner import Runner


def test_run_log_has_start_and_end_records(tmp_path):
    log_file = tmp_path / "run.jsonl"
    r = Runner(Mock(), workers=2, log_file=str(log_file), log_raw=True)
    attempts, info = r.run(["corpus"], {})
    records = [json.loads(line) for line in log_file.read_text().splitlines()]

    types = [rec["type"] for rec in records]
    assert types[0] == "run_start"
    assert types[-1] == "run_end"
    assert types.count("attempt") == len(attempts)

    start = records[0]
    assert start["probes"] == ["corpus"] and start["attempts"] == len(attempts)
    end = records[-1]
    assert end["status"] == "complete" and end["run_id"] == info.run_id
    assert end["findings"] == sum(len(a.findings) for a in attempts)

    # log_raw=True: raw text + prompt hash present for replay
    first_attempt = records[1]
    assert first_attempt["generation_text"] is not None
    assert len(first_attempt["prompt_sha256"]) == 64


def test_run_log_without_raw_omits_text(tmp_path):
    log_file = tmp_path / "run.jsonl"
    r = Runner(Mock(), workers=1, log_file=str(log_file), log_raw=False)
    r.run(["corpus"], {"limit": 2})
    rec = json.loads(log_file.read_text().splitlines()[1])
    assert "generation_text" not in rec
    assert "prompt_sha256" in rec


def test_worker_exception_becomes_internal_error(tmp_path):
    class Boom(Mock):
        def generate(self, system, prompt):
            raise RuntimeError("generator exploded")

    r = Runner(Boom(), workers=1, log_file=None)
    attempts, info = r.run(["corpus"], {"limit": 3})
    assert attempts and all(a.status == "internal_error" for a in attempts)
    assert all("internal error" in " ".join(a.detector_notes) for a in attempts)
    assert info.ok == 0 and info.parse_errors == 0


def test_bad_detector_does_not_kill_run(tmp_path):
    from vharness.detectors.base import Detector, register_builtin

    class Bad(Detector):
        name = "bad-detector-x"
        help = "raises"

        def detect(self, attempt):
            raise RuntimeError("nope")

    register_builtin(Bad)
    try:
        r = Runner(Mock(), detectors=["bad-detector-x", "json-verdict"], workers=2, log_file=None)
        attempts, info = r.run(["corpus"], {"limit": 3})
        assert attempts
        # The run survived the broken detector; the exception surfaces per-attempt.
        assert all(a.status == "internal_error" for a in attempts)
    finally:
        from vharness.core import DETECTOR_REGISTRY
        del DETECTOR_REGISTRY._items["bad-detector-x"]
        DETECTOR_REGISTRY._instances.pop("bad-detector-x", None)


def test_replay_from_log(tmp_path, capsys):
    # write a log with raw text
    log_file = tmp_path / "run.jsonl"
    r = Runner(Mock(), workers=1, log_file=str(log_file), log_raw=True)
    r.run(["corpus"], {"limit": 4})

    from vharness.cli import main

    rc = main(["replay", str(log_file), "--evaluators", "metrics,summary", "-q",
               "--metrics-out", str(tmp_path / "m.json")])
    assert rc == 0
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["metrics"]["labeled"] > 0


def test_log_verbosity_levels():
    from vharness.log import get_verbosity, setup
    setup(0)
    assert get_verbosity() == 0
    setup(1)
    assert get_verbosity() == 1
    setup(2)
    assert get_verbosity() == 2
    setup(quiet=True)
    assert get_verbosity() == -1
    setup(0)  # reset


def test_runner_recon_and_verbose_logging(tmp_path, caplog):
    import logging
    from vharness.core import Finding
    from vharness.runner import _format_location, _format_telemetry

    # Test format helpers
    a_fn = Attempt(prompt="p", source="app.py", context={"file": "app.py", "function": "greet", "line": 55})
    assert _format_location(a_fn) == "app.py:greet:55"
    a_file = Attempt(prompt="p", source="static/js/app.js", context={"file": "static/js/app.js", "function": "<file>", "line": 1})
    assert _format_location(a_file) == "static/js/app.js"

    a_fn.generation = Generation(text="{}", cached=True)
    assert _format_telemetry(a_fn) == " [cached]"
    a_fn.generation = Generation(text="{}", latency=0.85, prompt_tokens=100, completion_tokens=25)
    assert _format_telemetry(a_fn) == " [0.85s, 100+25 toks]"

    # Test runner with verbose logging
    class VulnMock(Mock):
        def generate(self, system, prompt):
            return Generation(text="{}", latency=0.1)

    from vharness.detectors.base import Detector, register_builtin

    class CustomDetector(Detector):
        name = "test-finding-detector"
        help = "emits a finding"

        def detect(self, attempt):
            attempt.status = "ok"
            attempt.verdict = "vulnerable"
            attempt.findings = [
                Finding(cwe="CWE-78", severity="High", sink="os.system()",
                        explanation="Command injection via user input", file="app.py", line=55, function="greet")
            ]

    register_builtin(CustomDetector)
    try:
        with caplog.at_level(logging.INFO, logger="vharness"):
            r = Runner(VulnMock(), detectors=["test-finding-detector"], workers=1, verbose=1)
            attempts, info = r.run(["corpus"], {"limit": 2})

            log_text = caplog.text
            assert "[recon] Triaged" in log_text
            assert "chunk(s) across" in log_text
            assert "↳ [High] CWE-78 in os.system() (line 55): Command injection via user input" in log_text
    finally:
        from vharness.core import DETECTOR_REGISTRY
        del DETECTOR_REGISTRY._items["test-finding-detector"]
        DETECTOR_REGISTRY._instances.pop("test-finding-detector", None)


def test_runner_error_logging(caplog):
    import logging

    class ErrorMock(Mock):
        def generate(self, system, prompt):
            return Generation(text="", error="rate limit exceeded (HTTP 429)")

    with caplog.at_level(logging.INFO, logger="vharness"):
        r = Runner(ErrorMock(), workers=1, verbose=0)
        attempts, info = r.run(["corpus"], {"limit": 1})
        assert any("↳ error: rate limit exceeded (HTTP 429)" in record.message for record in caplog.records)

