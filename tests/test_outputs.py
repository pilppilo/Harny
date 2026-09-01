"""SARIF output tests (ported to core.Finding)."""

import json

from vharness.core import Finding
from vharness.sarif import build_sarif


def _finding(**kw):
    base = dict(cwe="CWE-78", severity="High", sink="system()", explanation="cmd injection",
                patch="", file="src/main.c", line=12, function="run")
    base.update(kw)
    return Finding(**base)


def test_schema_uri_has_no_markdown_brackets():
    sarif = build_sarif([_finding()])
    assert sarif["$schema"].startswith("https://")
    assert "[" not in sarif["$schema"] and "]" not in sarif["$schema"]


def test_sarif_rules_levels_fingerprints():
    findings = [
        _finding(),
        _finding(severity="Medium", cwe="CWE-79", file="web/app.js"),
        _finding(severity="Low", cwe="CWE-79", file="web/app.js", sink="innerHTML"),
    ]
    sarif = build_sarif(findings)
    run = sarif["runs"][0]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["CWE-78", "CWE-79"]
    levels = [r["level"] for r in run["results"]]
    assert levels == ["error", "warning", "note"]
    fps = {r["partialFingerprints"]["primaryLocationLineHash"] for r in run["results"]}
    assert len(fps) == 3  # all distinct
    assert sarif["version"] == "2.1.0"
    assert json.dumps(sarif)  # serializable


def test_sarif_helpuri_points_at_mitre():
    sarif = build_sarif([_finding()])
    rule = sarif["runs"][0]["tool"]["driver"]["rules"][0]
    assert rule["helpUri"].endswith("/78.html")


def test_tool_version_tracks_package():
    from vharness.core import VERSION
    from vharness.sarif import TOOL_VERSION

    assert TOOL_VERSION == VERSION
