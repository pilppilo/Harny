"""JSONVerdict detector parsing tests (ported from legacy findings.py tests)."""

from vharness.core import Attempt, Generation
from vharness.detectors.json_verdict import JSONVerdict


def _detect(raw: str):
    a = Attempt(prompt="p", system="s")
    a.record(Generation(text=raw, model="test"))
    JSONVerdict().detect(a)
    return a


def test_parse_clean_output():
    a = _detect(
        '{"has_vulnerability": true, "vulnerabilities": [{"cwe": "CWE-78", "severity": "High", '
        '"sink": "system()", "explanation": "cmd injection", "patch": "use execv"}]}'
    )
    assert a.verdict == "vulnerable"
    assert len(a.findings) == 1
    assert a.findings[0].cwe == "CWE-78"
    assert a.findings[0].level == "error"


def test_parse_fenced_with_prose():
    a = _detect('Analysis follows.\n```json\n{"has_vulnerability": false, "vulnerabilities": []}\n```\nHope this helps.')
    assert a.verdict == "clean"
    assert a.findings == []


def test_parse_normalizes_cwe_and_severity():
    a = _detect('{"has_vulnerability": true, "vulnerabilities": [{"cwe": "cwe 79", "severity": "critical", "explanation": "xss"}]}')
    assert a.findings[0].cwe == "CWE-79"
    assert a.findings[0].severity == "High"


def test_parse_drops_invalid_entries():
    a = _detect('{"has_vulnerability": true, "vulnerabilities": [{"cwe": "nope", "explanation": "x"}, {"cwe": "CWE-89", "explanation": "sqli"}]}')
    assert len(a.findings) == 1
    assert any("cwe" in w for w in a.detector_notes)


def test_parse_garbage_records_parse_error():
    a = _detect("I cannot analyze this code, sorry.")
    assert a.status == "parse_error"
    assert a.verdict == "unparseable"
    assert a.detector_notes and "no JSON" in a.detector_notes[0]


def test_findings_list_implies_vulnerable():
    a = _detect('{"vulnerabilities": [{"cwe": "CWE-120", "severity": "Medium", "explanation": "overflow"}]}')
    assert a.verdict == "vulnerable"
    assert any("has_vulnerability" in w for w in a.detector_notes)


def test_no_generation_is_skipped():
    a = Attempt(prompt="p", system="s")
    JSONVerdict().detect(a)
    assert a.status == "skipped"
    assert a.verdict == "no_generation"
