from vharness.findings import parse_model_output


def test_parse_clean_output():
    raw = '{"has_vulnerability": true, "vulnerabilities": [{"cwe": "CWE-78", "severity": "High", "sink": "system()", "explanation": "cmd injection", "patch": "use execv"}]}'
    r = parse_model_output(raw)
    assert r.has_vulnerability
    assert len(r.findings) == 1
    assert r.findings[0].cwe == "CWE-78"
    assert r.findings[0].level == "error"


def test_parse_fenced_with_prose():
    raw = 'Analysis follows.\n```json\n{"has_vulnerability": false, "vulnerabilities": []}\n```\nHope this helps.'
    r = parse_model_output(raw)
    assert not r.has_vulnerability
    assert r.findings == []


def test_parse_normalizes_cwe_and_severity():
    raw = '{"has_vulnerability": true, "vulnerabilities": [{"cwe": "cwe 79", "severity": "critical", "explanation": "xss"}]}'
    r = parse_model_output(raw)
    assert r.findings[0].cwe == "CWE-79"
    assert r.findings[0].severity == "High"


def test_parse_drops_invalid_entries():
    raw = '{"has_vulnerability": true, "vulnerabilities": [{"cwe": "nope", "explanation": "x"}, {"cwe": "CWE-89", "explanation": "sqli"}]}'
    r = parse_model_output(raw)
    assert len(r.findings) == 1
    assert any("cwe" in w for w in r.warnings)


def test_parse_garbage_records_warning():
    r = parse_model_output("I cannot analyze this code, sorry.")
    assert not r.has_vulnerability
    assert r.warnings and "no JSON" in r.warnings[0]


def test_findings_list_implies_vulnerable():
    raw = '{"vulnerabilities": [{"cwe": "CWE-120", "severity": "Medium", "explanation": "overflow"}]}'
    r = parse_model_output(raw)
    assert r.has_vulnerability
    assert any("has_vulnerability" in w for w in r.warnings)
