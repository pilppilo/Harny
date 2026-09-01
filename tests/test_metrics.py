"""Metrics computation (ported/expanded from legacy eval tests)."""

from vharness.core import Attempt, Finding
from vharness.evaluators.metrics import compute
from vharness.probes.dataset import ChatDatasetProbe


def _attempt(expected, predicted, expected_cwes=(), predicted_cwes=(), status="ok"):
    a = Attempt(prompt="p", system="s", status=status,
                expected_verdict="vulnerable" if expected else "clean",
                expected_findings=[Finding(cwe=c, severity="High", sink="", explanation="x") for c in expected_cwes] if expected else [])
    a.verdict = "vulnerable" if predicted else "clean"
    a.findings = [Finding(cwe=c, severity="High", sink="", explanation="y") for c in predicted_cwes]
    return a


def test_metrics_perfect():
    m = compute([
        _attempt(True, True, ["CWE-78"], ["CWE-78"]),
        _attempt(False, False),
    ])
    assert (m["tp"], m["fp"], m["tn"], m["fn"]) == (1, 0, 1, 0)
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert m["fp_rate_clean"] == 0.0
    assert m["cwe_accuracy"] == 1.0
    assert m["per_cwe_recall"] == {"CWE-78": 1.0}


def test_metrics_counts():
    m = compute([
        _attempt(True, True, ["CWE-78"], ["CWE-89"]),   # TP, wrong CWE
        _attempt(True, False, ["CWE-78"]),               # FN
        _attempt(False, True),                            # FP
        _attempt(False, False),                            # TN
    ])
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    assert m["fp_rate_clean"] == 0.5
    assert m["cwe_accuracy"] == 0.0  # predicted CWE didn't match
    assert m["per_cwe_recall"] == {"CWE-78": 0.0}


def test_unlabeled_attempts_ignored():
    a = Attempt(prompt="p", system="s")  # no expected_verdict → scan mode
    m = compute([a])
    assert m["labeled"] == 0
    assert m["tp"] + m["fp"] + m["tn"] + m["fn"] == 0


def test_chat_dataset_loader(tmp_path):
    q = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "How do defenders hunt ransomware? Give steps.\nLine two."},
            {"role": "assistant", "content": "Use EDR and SIEM correlation across the kill chain."},
        ]
    }
    code = {
        "messages": [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "Analyze this C code:\n\nvoid f(char *s) {\n  char b[8];\n  strcpy(b, s);\n}\n"},
            {"role": "assistant", "content": "CWE-787 buffer overflow via strcpy; use bounded copy."},
        ]
    }
    p = tmp_path / "val.jsonl"
    p.write_text(__import__("json").dumps(q) + "\n" + __import__("json").dumps(code) + "\n", encoding="utf-8")
    got = ChatDatasetProbe().attempts(path=str(p))
    assert len(got) == 1
    assert got[0].expected_verdict == "vulnerable"
    assert "CWE-787" in [f.cwe for f in got[0].expected_findings]
