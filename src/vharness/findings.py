"""Finding model + robust parsing/validation of model JSON output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .textutil import extract_json_block, strip_code_fences

SEVERITIES = ("High", "Medium", "Low")
_SEVERITY_MAP = {
    "critical": "High",
    "high": "High",
    "moderate": "Medium",
    "medium": "Medium",
    "low": "Low",
    "info": "Low",
    "informational": "Low",
    "none": "Low",
}
_CWE_RE = re.compile(r"(?:cwe[ -]*)?(\d{1,4})", re.IGNORECASE)

LEVEL_MAP = {"High": "error", "Medium": "warning", "Low": "note"}


@dataclass
class Finding:
    cwe: str
    severity: str
    sink: str
    explanation: str
    patch: str = ""
    # Filled in by the scanner
    file: str = ""
    line: int = 0
    function: str = ""

    @property
    def level(self) -> str:
        return LEVEL_MAP.get(self.severity, "warning")


@dataclass
class ParsedResult:
    has_vulnerability: bool = False
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _normalize_cwe(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    m = _CWE_RE.search(raw.strip())
    if not m:
        return None
    return f"CWE-{int(m.group(1))}"


def _normalize_severity(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    return _SEVERITY_MAP.get(raw.strip().lower())


def parse_model_output(raw_text: str) -> ParsedResult:
    """Parse the model's reply into validated findings.

    Never raises: malformed entries are dropped with a recorded warning, and
    a fully unparseable reply yields an empty result with a warning so the
    caller can count it as a parse error instead of a silent "no vuln".
    """
    result = ParsedResult()
    text = strip_code_fences(raw_text or "")
    block = extract_json_block(text)
    if block is None:
        result.warnings.append("no JSON object found in model output")
        return result
    try:
        data = json.loads(block)
    except json.JSONDecodeError as e:
        result.warnings.append(f"invalid JSON: {e}")
        return result
    if not isinstance(data, dict):
        result.warnings.append("JSON is not an object")
        return result

    has = data.get("has_vulnerability")
    if isinstance(has, bool):
        result.has_vulnerability = has
    elif isinstance(data.get("vulnerabilities"), list) and data["vulnerabilities"]:
        result.has_vulnerability = True
        result.warnings.append("missing has_vulnerability flag, inferred from list")
    else:
        result.warnings.append("missing has_vulnerability flag")

    vulns = data.get("vulnerabilities", [])
    if not isinstance(vulns, list):
        result.warnings.append("vulnerabilities is not a list")
        return result

    for i, v in enumerate(vulns):
        if not isinstance(v, dict):
            result.warnings.append(f"vulnerability #{i} is not an object, dropped")
            continue
        cwe = _normalize_cwe(v.get("cwe"))
        severity = _normalize_severity(v.get("severity"))
        explanation = v.get("explanation")
        if cwe is None:
            result.warnings.append(f"vulnerability #{i} has invalid cwe {v.get('cwe')!r}, dropped")
            continue
        if severity is None:
            severity = "Medium"
            result.warnings.append(f"vulnerability #{i} has invalid severity, defaulted to Medium")
        if not isinstance(explanation, str) or not explanation.strip():
            result.warnings.append(f"vulnerability #{i} has empty explanation, dropped")
            continue
        result.findings.append(
            Finding(
                cwe=cwe,
                severity=severity,
                sink=str(v.get("sink", "")).strip(),
                explanation=explanation.strip(),
                patch=str(v.get("patch", "")).strip(),
            )
        )
    if result.findings:
        result.has_vulnerability = True
    return result
