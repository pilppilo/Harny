"""Eval mode: score the fine-tune against labeled samples (the missing loop)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .analyzers import all_analyzers
from .llm import LLMClient

LANGUAGE_TO_ANALYZER = {
    "c": "ccpp", "cpp": "ccpp", "ccpp": "ccpp",
    "js": "web", "javascript": "web", "ts": "web", "typescript": "web",
    "jsx": "web", "tsx": "web", "php": "web", "python": "web", "py": "web", "qml": "web",
    "shell": "shell", "bash": "shell", "sh": "shell",
    "sudoers": "distroconf", "systemd": "distroconf", "udev": "distroconf",
    "sysctl": "distroconf", "pacman-hook": "distroconf", "distroconf": "distroconf",
}


@dataclass
class EvalSample:
    sample_id: str
    language: str
    code: str
    vulnerable: bool
    cwes: set[str] = field(default_factory=set)


@dataclass
class EvalRecord:
    sample: EvalSample
    predicted_vulnerable: bool = False
    predicted_cwes: set[str] = field(default_factory=set)
    error: str | None = None
    latency: float = 0.0


def _analyzers_by_name() -> dict:
    return {a.name: a for a in all_analyzers()}


def load_corpus(corpus_dir: str) -> list[EvalSample]:
    samples: list[EvalSample] = []
    for fn in sorted(os.listdir(corpus_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(corpus_dir, fn), encoding="utf-8") as fh:
            data = json.load(fh)
        items = data if isinstance(data, list) else data.get("samples", [data])
        for i, entry in enumerate(items):
            cwes = {c if c.startswith("CWE-") else f"CWE-{c}" for c in entry.get("cwes", [])}
            samples.append(
                EvalSample(
                    sample_id=entry.get("id", f"{fn}:{i}"),
                    language=entry["language"],
                    code=entry["code"],
                    vulnerable=bool(entry["vulnerable"]),
                    cwes=cwes,
                )
            )
    return samples


_CWE_RE = re.compile(r"CWE-\d+")


def load_chat_dataset(path: str, limit: int | None = None) -> tuple[list[EvalSample], int]:
    """Extract code-analysis samples from a chat-format JSONL.

    Records use the OpenAI "messages" schema (system/user/assistant turns):
    code in the user turn, vulnerability/CWE labels in the assistant turn.
    Returns (usable_samples, total_records). Non-code Q&A records are
    skipped — they have no code to analyze and no CWE label.
    """
    samples: list[EvalSample] = []
    total = 0
    lang_re = re.compile(r"language[:\s]+(c\+\+|c|python|javascript|typescript|php|java|go|bash|shell|solidity)", re.IGNORECASE)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            total += 1
            if limit is not None and len(samples) >= limit:
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
            code_like = bool(re.search(r"[;{}]\s*$|^\s*(?:def|function|class|#include|import|package)\b", user, re.MULTILINE))
            if not code_like:
                continue
            has_label = bool(_CWE_RE.search(asst)) or re.search(r"\bvulnerab", asst, re.IGNORECASE)
            if not has_label:
                continue
            lang_m = lang_re.search(user[:400])
            lang = lang_m.group(1).lower() if lang_m else "unknown"
            samples.append(
                EvalSample(
                    sample_id=f"dataset-{total}",
                    language=lang,
                    code=user,
                    vulnerable=True,  # dataset is biased to vulnerable examples
                    cwes=set(_CWE_RE.findall(asst)[:3]),
                )
            )
    return samples, total


def run_eval(client: LLMClient, samples: list[EvalSample]) -> list[EvalRecord]:
    by_name = _analyzers_by_name()
    records: list[EvalRecord] = []
    for s in samples:
        analyzer_name = LANGUAGE_TO_ANALYZER.get(s.language)
        if analyzer_name is None or analyzer_name not in by_name:
            records.append(EvalRecord(sample=s, error=f"no analyzer for language {s.language!r}"))
            continue
        analyzer = by_name[analyzer_name]
        result = client.analyze(analyzer.system_prompt, analyzer.user_prompt(type("C", (), {"code": s.code})()))
        rec = EvalRecord(
            sample=s,
            predicted_vulnerable=result.parsed.has_vulnerability,
            predicted_cwes={f.cwe for f in result.parsed.findings},
            error=result.error,
            latency=result.latency,
        )
        records.append(rec)
    return records


@dataclass
class Metrics:
    total: int = 0
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    accuracy: float = 0.0
    clean_total: int = 0
    fp_rate_clean: float = 0.0
    cwe_labeled: int = 0
    cwe_match: int = 0
    cwe_accuracy: float = 0.0
    errors: int = 0
    per_cwe_recall: dict = field(default_factory=dict)

    def as_table_row(self, label: str) -> str:
        return (
            f"| {label} | {self.total} | {self.precision:.2f} | {self.recall:.2f} | "
            f"{self.f1:.2f} | {self.fp_rate_clean:.2f} | {self.cwe_accuracy:.2f} | {self.errors} |"
        )


def compute_metrics(records: list[EvalRecord]) -> Metrics:
    m = Metrics()
    cwe_expected_count: dict[str, int] = {}
    cwe_caught: dict[str, int] = {}
    for r in records:
        m.total += 1
        if r.error and not r.predicted_vulnerable:
            m.errors += 1
        expected, predicted = r.sample.vulnerable, r.predicted_vulnerable
        if expected and predicted:
            m.tp += 1
        elif expected and not predicted:
            m.fn += 1
        elif not expected and predicted:
            m.fp += 1
        else:
            m.tn += 1
        if not expected:
            m.clean_total += 1
        for cwe in r.sample.cwes:
            cwe_expected_count[cwe] = cwe_expected_count.get(cwe, 0) + 1
            if predicted and cwe in r.predicted_cwes:
                cwe_caught[cwe] = cwe_caught.get(cwe, 0) + 1
        if expected and predicted and r.sample.cwes:
            m.cwe_labeled += 1
            if r.predicted_cwes & r.sample.cwes:
                m.cwe_match += 1
    denom_p = m.tp + m.fp
    denom_r = m.tp + m.fn
    m.precision = m.tp / denom_p if denom_p else 0.0
    m.recall = m.tp / denom_r if denom_r else 0.0
    m.f1 = 2 * m.precision * m.recall / (m.precision + m.recall) if (m.precision + m.recall) else 0.0
    m.accuracy = (m.tp + m.tn) / m.total if m.total else 0.0
    m.fp_rate_clean = m.fp / m.clean_total if m.clean_total else 0.0
    m.cwe_accuracy = m.cwe_match / m.cwe_labeled if m.cwe_labeled else 0.0
    m.per_cwe_recall = {
        cwe: cwe_caught.get(cwe, 0) / n for cwe, n in sorted(cwe_expected_count.items())
    }
    return m


def eval_markdown(label: str, m: Metrics, per_sample: list[EvalRecord] | None = None) -> str:
    lines = [
        f"## Eval — {label}",
        "",
        f"Samples: {m.total} (clean: {m.clean_total}, vulnerable: {m.tp + m.fn})",
        "",
        "| endpoint | n | precision | recall | F1 | FP-rate(clean) | CWE acc | errors |",
        "|---|---|---|---|---|---|---|---|",
        m.as_table_row(label),
        "",
        f"Confusion: TP={m.tp} FP={m.fp} TN={m.tn} FN={m.fn}",
        "",
        "Per-CWE recall:",
        "",
    ]
    if m.per_cwe_recall:
        for cwe, r in m.per_cwe_recall.items():
            lines.append(f"- `{cwe}`: {r:.0%}")
    else:
        lines.append("- (no labeled CWEs)")
    if per_sample:
        lines += ["", "### Missed (FN) / false alarms (FP)", ""]
        for r in per_sample:
            if r.sample.vulnerable and not r.predicted_vulnerable:
                lines.append(f"- FN `{r.sample.sample_id}` (expected {sorted(r.sample.cwes) or 'vuln'}) {r.error or ''}")
            elif not r.sample.vulnerable and r.predicted_vulnerable:
                lines.append(f"- FP `{r.sample.sample_id}` predicted {sorted(r.predicted_cwes)}")
    return "\n".join(lines)


def write_eval_report(path: str, records: list[EvalRecord], m: Metrics) -> None:
    data = {
        "metrics": {
            "total": m.total, "tp": m.tp, "fp": m.fp, "tn": m.tn, "fn": m.fn,
            "precision": m.precision, "recall": m.recall, "f1": m.f1,
            "accuracy": m.accuracy, "fp_rate_clean": m.fp_rate_clean,
            "cwe_accuracy": m.cwe_accuracy, "errors": m.errors,
            "per_cwe_recall": m.per_cwe_recall,
        },
        "samples": [
            {
                "id": r.sample.sample_id,
                "language": r.sample.language,
                "expected_vulnerable": r.sample.vulnerable,
                "expected_cwes": sorted(r.sample.cwes),
                "predicted_vulnerable": r.predicted_vulnerable,
                "predicted_cwes": sorted(r.predicted_cwes),
                "error": r.error,
            }
            for r in records
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
