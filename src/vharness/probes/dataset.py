"""Dataset probes: labeled corpora with ground-truth verdicts/CWEs."""

from __future__ import annotations

import json
import os
import re

from ..core import Attempt, Finding
from .base import Probe, register_builtin

_LANGUAGE_SYSTEM_ROLES = {
    "c": "Analyze this C function for memory-safety and injection vulnerabilities.",
    "cpp": "Analyze this C++ function for memory-safety and injection vulnerabilities.",
    "js": "Analyze this JavaScript code for web vulnerabilities.",
    "ts": "Analyze this TypeScript code for web vulnerabilities.",
    "jsx": "Analyze this JSX code for web vulnerabilities.",
    "tsx": "Analyze this TSX code for web vulnerabilities.",
    "php": "Analyze this PHP code for web vulnerabilities.",
    "python": "Analyze this Python code for web vulnerabilities.",
    "py": "Analyze this Python code for web vulnerabilities.",
    "qml": "Analyze this QML code for injection and unsafe-eval vulnerabilities.",
    "shell": "Analyze this shell script for command injection and unsafe-download issues.",
    "bash": "Analyze this bash script for command injection and unsafe-download issues.",
    "sh": "Analyze this shell script for command injection and unsafe-download issues.",
    "sudoers": "Analyze this sudoers drop-in from an OS-hardening perspective.",
    "systemd": "Analyze this systemd unit from an OS-hardening perspective.",
    "udev": "Analyze this udev rule from an OS-hardening perspective.",
    "sysctl": "Analyze this sysctl drop-in from an OS-hardening perspective.",
    "pacman-hook": "Analyze this pacman hook from an OS-hardening perspective.",
}
_FALLBACK_ROLE = "Analyze this code for security vulnerabilities."
_CWE_RE = re.compile(r"CWE-\d+")

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "eval_corpus")


def _system_for(language: str) -> str:
    from .scan import build_system_prompt

    return build_system_prompt(_LANGUAGE_SYSTEM_ROLES.get(language, _FALLBACK_ROLE))


def _ground_truth(vulnerable: bool, cwes: set[str], language: str) -> list[Finding]:
    if not vulnerable:
        return []
    return [
        Finding(cwe=c, severity="High", sink="", explanation="expected", file="", line=0, function="")
        for c in sorted(cwes)
    ] or [
        Finding(cwe="CWE-0", severity="High", sink="", explanation="expected (unlabeled)", file="", line=0, function="")
    ]


def load_corpus_files(corpus_dir: str) -> list[dict]:
    records: list[dict] = []
    for fn in sorted(os.listdir(corpus_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(corpus_dir, fn), encoding="utf-8") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else data.get("samples", [data])
        for i, entry in enumerate(items):
            entry = dict(entry)
            entry.setdefault("id", f"{fn[:-5]}:{i}")
            records.append(entry)
    return records


@register_builtin
class CorpusProbe(Probe):
    """The harness's hand-labeled corpus (vulnerable + clean, all domains)."""

    name = "corpus"
    help = "built-in labeled corpus (~35 vulnerable + clean samples)"

    def attempts(self, **kwargs) -> list[Attempt]:
        corpus_dir = kwargs.get("corpus_dir") or os.path.normpath(CORPUS_DIR)
        limit = kwargs.get("limit")
        out: list[Attempt] = []
        for entry in load_corpus_files(corpus_dir):
            if limit is not None and len(out) >= limit:
                break
            cwes = {c if str(c).startswith("CWE-") else f"CWE-{c}" for c in entry.get("cwes", [])}
            vulnerable = bool(entry["vulnerable"])
            code = entry["code"]
            out.append(
                Attempt(
                    prompt=f"Analyze this code:\n\n```\n{code}\n```\n\nReturn the JSON verdict now.",
                    system=_system_for(entry.get("language", "")),
                    probe=self.name,
                    source=entry["id"],
                    context={"language": entry.get("language", ""), "sample_id": entry["id"]},
                    expected_verdict="vulnerable" if vulnerable else "clean",
                    expected_findings=_ground_truth(vulnerable, cwes, entry.get("language", "")),
                )
            )
        return out


_CWE_RE_GLOBAL = re.compile(r"CWE-\d+")
_LANG_RE = re.compile(
    r"language[:\s]+(c\+\+|c|python|javascript|typescript|php|java|go|bash|shell|solidity)", re.IGNORECASE
)


@register_builtin
class ChatDatasetProbe(Probe):
    """Code-analysis samples extracted from a chat-format JSONL dataset.

    Records use the OpenAI "messages" schema: code in the user turn,
    vulnerability/CWE labels in the assistant turn. Non-code Q&A records are
    skipped (no code, no label). Ground truth: any record kept is assumed
    vulnerable; assistant-turn CWEs become expected labels.
    """

    name = "chat-dataset"
    help = "code samples + labels from an OpenAI-messages JSONL file"

    def attempts(self, **kwargs) -> list[Attempt]:
        path = kwargs.get("path")
        if not path:
            raise ValueError("chat-dataset probe requires path=<jsonl>")
        limit = kwargs.get("limit")
        out: list[Attempt] = []
        total = 0
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                total += 1
                if limit is not None and len(out) >= limit:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msgs = rec.get("messages", [])
                user = next((m["content"] for m in msgs if m["role"] == "user"), "")
                asst = next((m["content"] for m in msgs if m["role"] == "assistant"), "")
                if len(user) < 60 or "\n" not in user:
                    continue
                code_like = bool(
                    re.search(r"[;{}]\s*$|^\s*(?:def|function|class|#include|import|package)\b", user, re.MULTILINE)
                )
                if not code_like:
                    continue
                has_label = bool(_CWE_RE_GLOBAL.search(asst)) or bool(re.search(r"\bvulnerab", asst, re.IGNORECASE))
                if not has_label:
                    continue
                lang_m = _LANG_RE.search(user[:400])
                lang = lang_m.group(1).lower() if lang_m else "unknown"
                cwes = set(_CWE_RE_GLOBAL.findall(asst)[:3])
                out.append(
                    Attempt(
                        prompt=f"Analyze this code:\n\n```\n{user}\n```\n\nReturn the JSON verdict now.",
                        system=_system_for("c" if lang == "c" else lang if lang in _LANGUAGE_SYSTEM_ROLES else ""),
                        probe=self.name,
                        source=f"sample-{total}",
                        context={"language": lang, "record": total},
                        expected_verdict="vulnerable",
                        expected_findings=_ground_truth(True, cwes, lang),
                    )
                )
        return out
