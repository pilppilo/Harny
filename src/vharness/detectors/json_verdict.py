"""JSONVerdict detector: parses and validates the model's JSON verdict."""

from __future__ import annotations

import json
import re

from ..core import Attempt, Finding
from ..textutil import extract_json_block, strip_code_fences
from .base import Detector, register_builtin

_SEVERITY_MAP = {
    "critical": "High", "high": "High",
    "moderate": "Medium", "medium": "Medium",
    "low": "Low", "info": "Low", "informational": "Low", "none": "Low",
}
_CWE_CANONICAL_RE = re.compile(r"^CWE[- ]?(\d+)(?:\s+.*)?$", re.IGNORECASE)
_CWE_NUMERIC_RE = re.compile(r"^\d+$")
_MIN_CWE = 1
_MAX_CWE = 9999


def _normalize_cwe(raw) -> str | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return f"CWE-{raw}" if _MIN_CWE <= raw <= _MAX_CWE else None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if _CWE_NUMERIC_RE.fullmatch(value):
        number = int(value)
    else:
        match = _CWE_CANONICAL_RE.fullmatch(value)
        if match is None:
            return None
        number = int(match.group(1))
    return f"CWE-{number}" if _MIN_CWE <= number <= _MAX_CWE else None


def _normalize_severity(raw) -> str | None:
    if not isinstance(raw, str):
        return None
    return _SEVERITY_MAP.get(raw.strip().lower())


def _optional_text(raw) -> str:
    """Keep optional report fields textual; null and malformed values are empty."""
    return raw.strip() if isinstance(raw, str) else ""


@register_builtin
class JSONVerdict(Detector):
    """Parses ``{has_vulnerability, vulnerabilities[]}`` into Findings.

    Sets verdict "vulnerable"/"clean" and status "parse_error" when the
    model's reply isn't usable JSON — parse failures are recorded, never
    silently treated as "clean".
    """

    name = "json-verdict"
    help = "parse/validate {has_vulnerability, vulnerabilities[]} model replies"

    def detect(self, attempt: Attempt) -> None:
        gen = attempt.generation
        if gen is None:
            attempt.status = "skipped"
            attempt.verdict = "no_generation"
            return
        if gen.error:
            attempt.verdict = "error"
            return

        text = strip_code_fences(gen.text or "")
        block = extract_json_block(text)
        if block is None:
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append("no JSON object found in model output")
            return
        try:
            data = json.loads(block)
        except json.JSONDecodeError as e:
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append(f"invalid JSON: {e}")
            return
        if not isinstance(data, dict):
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append("JSON is not an object")
            return

        has = data.get("has_vulnerability")
        if isinstance(has, bool):
            vulnerable = has
        elif isinstance(data.get("vulnerabilities"), list) and data["vulnerabilities"]:
            vulnerable = True
            attempt.detector_notes.append("missing has_vulnerability flag; inferred from list")
        else:
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append("missing has_vulnerability flag")
            return

        vulns = data.get("vulnerabilities", [])
        if not vulnerable and vulns != []:
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append(
                "has_vulnerability=false requires vulnerabilities to be absent or an empty list"
            )
            return
        if not isinstance(vulns, list):
            attempt.detector_notes.append("vulnerabilities is not a list; ignored")
            vulns = []

        for i, v in enumerate(vulns):
            if not isinstance(v, dict):
                attempt.detector_notes.append(f"vulnerability #{i} is not an object; dropped")
                continue
            cwe = _normalize_cwe(v.get("cwe"))
            severity = _normalize_severity(v.get("severity")) or "Medium"
            explanation = v.get("explanation")
            if cwe is None:
                attempt.detector_notes.append(f"vulnerability #{i} invalid cwe {v.get('cwe')!r}; dropped")
                continue
            if not isinstance(explanation, str) or not explanation.strip():
                attempt.detector_notes.append(f"vulnerability #{i} empty explanation; dropped")
                continue
            f = Finding(
                cwe=cwe, severity=severity,
                sink=_optional_text(v.get("sink")),
                explanation=explanation.strip(),
                patch=_optional_text(v.get("patch")),
                file=attempt.context.get("file", attempt.source),
                line=attempt.context.get("line", 0),
                function=attempt.context.get("function", ""),
            )
            attempt.findings.append(f)
            if severity == "Medium" and _normalize_severity(v.get("severity")) is None:
                attempt.detector_notes.append(f"vulnerability #{i} invalid severity; defaulted Medium")

        if vulnerable and not attempt.findings:
            attempt.status = "parse_error"
            attempt.verdict = "unparseable"
            attempt.detector_notes.append("vulnerability asserted but no valid findings were supplied")
            return
        attempt.verdict = "vulnerable" if attempt.findings else "clean"
