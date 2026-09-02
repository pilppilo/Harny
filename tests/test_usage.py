import json

from vharness.usage import read_usage


def _write_log(path):
    records = [
        {"type": "run_start", "run_id": "one", "provider": "https://one.example/v1", "model": "alpha"},
        {"type": "attempt", "run_id": "one", "generation": {
            "model": "alpha", "prompt_tokens": 10, "completion_tokens": 4, "latency": 0.4,
        }},
        {"type": "attempt", "run_id": "one", "generation": {
            "model": "alpha", "cached": True, "prompt_tokens": 0, "completion_tokens": 0,
        }},
        {"type": "attempt", "run_id": "one", "generation": {
            "model": "alpha", "error": "rate limited",
        }},
        {"type": "run_start", "run_id": "two", "provider": "https://two.example/v1", "model": "beta"},
        {"type": "attempt", "run_id": "two", "generation": {
            "model": "beta", "prompt_tokens": 7, "completion_tokens": 3, "latency": 0.2,
        }},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n")


def test_read_usage_filters_current_provider_and_model(tmp_path):
    log = tmp_path / "run.jsonl"
    _write_log(log)

    summaries = read_usage([log], provider="https://one.example/v1/", model="alpha")

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.provider == "https://one.example/v1"
    assert summary.model == "alpha"
    assert summary.attempts == 3
    assert summary.completed_requests == 1
    assert summary.cache_hits == 1
    assert summary.api_errors == 1
    assert summary.prompt_tokens == 10
    assert summary.completion_tokens == 4
    assert summary.total_tokens == 14
    assert summary.latency_p50 == 0.4


def test_read_usage_all_models(tmp_path):
    log = tmp_path / "run.jsonl"
    _write_log(log)

    summaries = read_usage([log], provider="https://one.example/v1", model="alpha", all_models=True)

    assert [(summary.provider, summary.model) for summary in summaries] == [
        ("https://one.example/v1", "alpha"),
        ("https://two.example/v1", "beta"),
    ]


def test_usage_command_reports_local_usage(tmp_path, capsys):
    log = tmp_path / "run.jsonl"
    _write_log(log)
    config = tmp_path / "vharness.toml"
    config.write_text('[default]\nbase_url = "https://one.example/v1"\nmodel = "alpha"\n')

    from vharness.cli import main

    assert main(["usage", "--config", str(config), "--log-file", str(log)]) == 0
    output = capsys.readouterr().out
    assert "Current provider: https://one.example/v1" in output
    assert "tokens=14 (prompt=10, completion=4)" in output
    assert "Account quota/remaining credits: unavailable" in output
