"""SARIF 2.1.0 export (GitHub code-scanning compatible)."""

from __future__ import annotations

import hashlib
import json

from .core import VERSION, Finding

SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"
TOOL_NAME = "vharness"
TOOL_VERSION = VERSION


def _fingerprint(f: Finding) -> str:
    return hashlib.sha256(f"{f.file}|{f.cwe}|{f.function}|{f.sink}".encode()).hexdigest()[:16]


def build_sarif(findings: list[Finding], tool_name: str = TOOL_NAME) -> dict:
    rules: dict[str, dict] = {}
    results: list[dict] = []
    for f in findings:
        if f.cwe not in rules:
            rules[f.cwe] = {
                "id": f.cwe,
                "name": f.cwe,
                "shortDescription": {"text": f"{f.cwe} finding by {tool_name}"},
                "helpUri": f"https://cwe.mitre.org/data/definitions/{f.cwe.split('-')[-1]}.html",
                "properties": {"security-severity": {"High": "9.0", "Medium": "5.0", "Low": "2.5"}[f.severity]},
            }
        results.append(
            {
                "ruleId": f.cwe,
                "ruleIndex": sorted(rules).index(f.cwe),
                "level": f.level,
                "message": {"text": f"{f.explanation} (sink: {f.sink or 'n/a'})"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.file, "uriBaseId": "%SRCROOT%"},
                            "region": {"startLine": max(1, f.line)},
                        }
                    }
                ],
                "partialFingerprints": {"primaryLocationLineHash": _fingerprint(f)},
                "properties": {"function": f.function, "severity": f.severity, "patch": f.patch},
            }
        )
    return {
        "$schema": SCHEMA_URI,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": tool_name,
                        "version": TOOL_VERSION,
                        "informationUri": "https://cwe.mitre.org/",
                        "rules": [rules[cwe] for cwe in sorted(rules)],
                    }
                },
                "originalUriBaseIds": {"%SRCROOT%": {"uri": "file:///"}},
                "results": results,
            }
        ],
    }


def write_sarif(findings: list[Finding], output_file: str, tool_name: str = TOOL_NAME) -> None:
    with open(output_file, "w", encoding="utf-8") as fh:
        json.dump(build_sarif(findings, tool_name), fh, indent=2)
