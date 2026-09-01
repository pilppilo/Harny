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
