import json

from vharness.eval import (
    EvalRecord,
    EvalSample,
    compute_metrics,
    load_chat_dataset,
    load_corpus,
)


def _rec(vuln, pred, cwes=None, pred_cwes=None):
    return EvalRecord(
        sample=EvalSample(sample_id="x", language="c", code="", vulnerable=vuln, cwes=set(cwes or [])),
        predicted_vulnerable=pred,
        predicted_cwes=set(pred_cwes or []),
    )


def test_metrics_perfect():
    m = compute_metrics([_rec(True, True, ["CWE-78"], ["CWE-78"]), _rec(False, False)])
    assert (m.tp, m.fp, m.tn, m.fn) == (1, 0, 1, 0)
    assert m.precision == 1.0 and m.recall == 1.0 and m.f1 == 1.0
    assert m.fp_rate_clean == 0.0
    assert m.cwe_accuracy == 1.0


def test_metrics_counts():
    m = compute_metrics([
        _rec(True, True, ["CWE-78"], ["CWE-89"]),   # TP, wrong CWE
        _rec(True, False, ["CWE-78"]),               # FN
        _rec(False, True),                            # FP
        _rec(False, False),                           # TN
    ])
    assert (m.tp, m.fn, m.fp, m.tn) == (1, 1, 1, 1)
    assert m.precision == 0.5 and m.recall == 0.5
    assert m.fp_rate_clean == 0.5
    assert m.cwe_accuracy == 0.0  # predicted CWE didn't match
    assert m.per_cwe_recall == {"CWE-78": 0.0}


def test_corpus_loads_and_is_balanced():
    import os

    corpus_dir = os.path.join(os.path.dirname(vh_file()), "eval_corpus")
    samples = load_corpus(corpus_dir)
    assert len(samples) >= 30
    langs = {s.language for s in samples}
    assert {"c", "js", "ts", "php", "python", "shell", "qml", "sudoers", "systemd", "udev", "sysctl"} <= langs
    assert any(not s.vulnerable for s in samples), "corpus must contain clean samples for FP-rate"
    assert all(s.cwes for s in samples if s.vulnerable), "vulnerable samples must carry CWE labels"


def vh_file():
    import vharness.eval as e

    return e.__file__


def test_chat_dataset_loader_filters_prose(tmp_path):
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
    p.write_text(json.dumps(q) + "\n" + json.dumps(code) + "\n", encoding="utf-8")
    samples, total = load_chat_dataset(str(p))
    assert total == 2
    assert len(samples) == 1
    assert samples[0].cwes == {"CWE-787"}
