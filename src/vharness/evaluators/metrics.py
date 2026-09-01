"""Metrics evaluator: precision/recall/F1, FP-rate, CWE accuracy, per-CWE recall."""

from __future__ import annotations

import json
import os
from collections import Counter
from dataclasses import asdict, dataclass

from ..core import Attempt
from ..log import log
from .base import Evaluator, register_builtin


@dataclass
class Confusion:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0


def _confusion(attempts: list[Attempt]) -> Confusion:
    c = Confusion()
    for a in attempts:
        if a.expected_verdict is None:
            continue  # unlabeled (scan mode) — no ground truth to score
        expected = a.expected_verdict == "vulnerable"
        predicted = a.verdict == "vulnerable"
        if expected and predicted:
            c.tp += 1
        elif expected and not predicted:
            c.fn += 1
        elif not expected and predicted:
            c.fp += 1
        else:
            c.tn += 1
    return c


def compute(attempts: list[Attempt]) -> dict:
    """All metrics over labeled attempts; empty when nothing is labeled."""
    c = _confusion(attempts)
    labeled = [a for a in attempts if a.expected_verdict is not None]
    metrics: dict = {
        "labeled": len(labeled),
        "tp": c.tp, "fp": c.fp, "tn": c.tn, "fn": c.fn,
    }
    p_den = c.tp + c.fp
    r_den = c.tp + c.fn
    precision = c.tp / p_den if p_den else 0.0
    recall = c.tp / r_den if r_den else 0.0
    metrics["precision"] = round(precision, 4)
    metrics["recall"] = round(recall, 4)
    metrics["f1"] = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0
    clean = [a for a in labeled if a.expected_verdict == "clean"]
    flagged_clean = sum(1 for a in clean if a.verdict == "vulnerable")
    metrics["clean_total"] = len(clean)
    metrics["fp_rate_clean"] = round(flagged_clean / len(clean), 4) if clean else None

    # CWE-label accuracy (on labeled vulnerable attempts the model caught)
    labeled_vuln = [a for a in labeled if a.expected_verdict == "vulnerable" and a.verdict == "vulnerable"]
    real_expected = [a for a in labeled_vuln if a.expected_findings and a.expected_findings[0].cwe != "CWE-0"]
    cwe_labeled = [a for a in real_expected if a.expected_findings]
    matched = sum(
        1 for a in cwe_labeled if {f.cwe for f in a.findings} & {f.cwe for f in a.expected_findings}
    )
    metrics["cwe_labeled"] = len(cwe_labeled)
    metrics["cwe_match"] = matched
    metrics["cwe_accuracy"] = round(matched / len(cwe_labeled), 4) if cwe_labeled else None

    per_cwe: dict[str, dict[str, int]] = {}
    for a in labeled:
        if a.expected_verdict != "vulnerable":
            continue
        for ef in a.expected_findings or []:
            if ef.cwe == "CWE-0":
                continue
            slot = per_cwe.setdefault(ef.cwe, {"expected": 0, "caught": 0})
            slot["expected"] += 1
            if a.verdict == "vulnerable" and any(f.cwe == ef.cwe for f in a.findings):
                slot["caught"] += 1
    metrics["per_cwe_recall"] = {k: round(v["caught"] / v["expected"], 4) for k, v in sorted(per_cwe.items())}
    return metrics


@register_builtin
class MetricsReport(Evaluator):
    name = "metrics"
    help = "compute + print P/R/F1, FP-rate, CWE accuracy; write eval metrics JSON"

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        m = compute(attempts)
        log.info("== metrics ==")
        if not m["labeled"]:
            log.info("no labeled attempts — run a dataset probe (corpus/chat-dataset) to score the model")
        else:
            log.info(
                "labeled=%s  P=%s R=%s F1=%s  (TP=%s FP=%s TN=%s FN=%s)",
                m["labeled"], m["precision"], m["recall"], m["f1"],
                m["tp"], m["fp"], m["tn"], m["fn"],
            )
            if m["clean_total"]:
                log.info("false-positive rate on clean code: %s", m["fp_rate_clean"])
            if m["cwe_labeled"]:
                log.info("CWE-label accuracy: %s (%s/%s)", m["cwe_accuracy"], m["cwe_match"], m["cwe_labeled"])
            if m["per_cwe_recall"]:
                log.info("per-CWE recall: %s", ", ".join(f"{k}={v}" for k, v in m["per_cwe_recall"].items()))
        out = run_info.get("metrics_out") or "eval_metrics.json"
        if run_info.get("out_dir") and not os.path.isabs(out):
            out = os.path.join(run_info["out_dir"], out)
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"metrics": m, "per_sample": [
                {
                    "id": a.id, "source": a.source, "probe": a.probe,
                    "expected": a.expected_verdict, "predicted": a.verdict,
                    "expected_cwes": [f.cwe for f in (a.expected_findings or [])],
                    "predicted_cwes": [f.cwe for f in a.findings],
                    "status": a.status, "notes": a.detector_notes,
                }
                for a in attempts if a.expected_verdict is not None
            ]}, fh, indent=2)
        log.info("wrote metrics: %s", out)
