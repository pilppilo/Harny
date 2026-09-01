"""End-to-end pipeline tests using the offline Mock generator."""

from vharness.core import Attempt, Generation
from vharness.detectors.json_verdict import JSONVerdict
from vharness.evaluators.metrics import compute
from vharness.generators.mock import Mock
from vharness.probes.dataset import CorpusProbe


def _run_probe_with_mock():
    probe = CorpusProbe()
    attempts = probe.attempts()
    mock = Mock()
    detector = JSONVerdict()
    for a in attempts:
        a.record(mock.generate(a.system, a.prompt))
        detector.detect(a)
    return attempts


def test_corpus_probe_yields_labeled_attempts():
    attempts = _run_probe_with_mock()
    assert len(attempts) >= 30
    assert all(a.expected_verdict in ("vulnerable", "clean") for a in attempts)
    vuln = [a for a in attempts if a.expected_verdict == "vulnerable"]
    clean = [a for a in attempts if a.expected_verdict == "clean"]
    assert vuln and clean
    assert all(a.verdict in ("vulnerable", "clean", "unparseable") for a in attempts)


def test_mock_detects_corpus_patterns_end_to_end():
    attempts = _run_probe_with_mock()
    # The mock flags the curl|sh sample: it must come back vulnerable.
    curl = [a for a in attempts if a.source == "sh-curl-pipe-sh"]
    assert curl, "corpus must contain the curl|sh sample"
    assert all(a.verdict == "vulnerable" and a.findings for a in curl)


def test_metrics_compute_on_mock_run():
    attempts = _run_probe_with_mock()
    m = compute(attempts)
    assert m["labeled"] == len(attempts)
    assert m["tp"] + m["fp"] + m["tn"] + m["fn"] == m["labeled"]
    assert 0.0 <= m["precision"] <= 1.0 and 0.0 <= m["recall"] <= 1.0
    assert m["labeled"] > 0


def test_detector_marks_unparseable_as_never_clean():
    a = Attempt(prompt="p", system="s", expected_verdict="clean")
    a.record(Generation(text="I cannot analyze this, sorry.", model="mock"))
    JSONVerdict().detect(a)
    assert a.status == "parse_error"
    assert a.verdict == "unparseable"
    assert a.findings == []


def test_generation_error_path():
    a = Attempt(prompt="p", system="s")
    a.record(Generation(text="", model="mock", error="boom"))
    JSONVerdict().detect(a)
    assert a.status == "api_error"
    assert a.verdict == "error"
