"""Deterministic mock generator for tests and offline demos."""

from __future__ import annotations

import re
import urllib.parse

from ..core import Generation
from .base import Generator, register_builtin


def _script_response(prompt: str) -> str:
    """Heuristic 'model': flags the pipe/eval patterns the corpus exercises."""
    findings = []
    if re.search(r"curl[^|\n]*\|\s*(?:ba|z)?sh", prompt):
        findings.append({"cwe": "CWE-494", "severity": "High", "sink": "curl|sh",
                         "explanation": "Remote code executed without verification.", "patch": ""})
    if re.search(r"\beval\s+", prompt):
        findings.append({"cwe": "CWE-95", "severity": "High", "sink": "eval",
                         "explanation": "eval on untrusted input.", "patch": ""})
    if re.search(r"rm\s+-rf|/\$\{?[A-Z_]", prompt):
        findings.append({"cwe": "CWE-78", "severity": "Medium", "sink": "rm -rf",
                         "explanation": "Unquoted expansion in destructive command.", "patch": ""})
    if re.search(r"CWE-", prompt) and not findings:
        pass
    if not findings:
        return '{"has_vulnerability": false, "vulnerabilities": []}'
    return json_response(findings)


def json_response(findings: list[dict]) -> str:
    import json

    return json.dumps({"has_vulnerability": bool(findings), "vulnerabilities": findings})


@register_builtin
class Mock(Generator):
    """Replies with canned JSON keyed off the prompt; supports ?cwe= hints."""

    name = "mock"
    help = "offline deterministic generator for tests and demos"

    def __init__(self, script: dict[str, str] | None = None) -> None:
        self.script = script or {}

    def generate(self, system: str, prompt: str) -> Generation:
        # Exact-match script first (tests pin behavior this way)
        for key, reply in self.script.items():
            if key in prompt:
                return Generation(text=reply, model="mock", latency=0.0)
        if url := re.search(r"vharness-hint:\s*(\S+)", prompt):
            hint = urllib.parse.unquote(url.group(1))
            return Generation(text=hint, model="mock", latency=0.0)
        return Generation(text=_script_response(prompt), model="mock", latency=0.0)
