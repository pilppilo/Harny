# Harny (vharness) — a pluggable LLM security harness

An SDK-shaped harness for security work with LLMs: **probe → generator →
detector → evaluator**. Point it at any OpenAI-compatible endpoint, scan code
across domains, score models against labeled data, and extend every stage with
one-file plugins — from installed packages, without touching this repo.

Built for (but not limited to) fine-tuned security models: measure whether a
fine-tune actually beats its base model, with a scanner that runs the same
pipeline in production.

## The pipeline

| Stage | Role | Built-ins |
|---|---|---|
| **Probe** | finds units of work (code chunks, dataset samples) | `ccpp`, `web`, `shell`, `distroconf`, `corpus`, `chat-dataset` |
| **Generator** | model I/O for any OpenAI-compatible endpoint | `openai` (retry + SQLite cache + usage stats), `mock` |
| **Detector** | judges the reply, never silently swallows failures | `json-verdict` (fenced/prose-tolerant JSON parsing + schema validation) |
| **Runner** | concurrency, per-attempt JSONL run log, dry-run | — |
| **Evaluator** | reports & metrics | `sarif`, `markdown`, `json`, `metrics`, `summary` |

Every attempt (prompt, generation, verdict, findings, ground truth, tokens,
latency) lands in a JSONL run log — runs are auditable and replayable.

## Quick start

```bash
uv sync                       # deps: just openai
uv run pytest                 # 44 tests, offline

# Offline demo of the full pipeline (mock generator, zero API calls):
uv run python -m vharness scan ~/my-repo --generator mock
uv run python -m vharness eval --generator mock

# List every registered plugin:
uv run python -m vharness list
```

## Real runs — any OpenAI-compatible endpoint

```bash
export VHARNESS_BASE_URL="http://localhost:11434/v1"   # Ollama; vLLM: :8000/v1; any hosted API
export VHARNESS_API_KEY="..."                          # only if required
export VHARNESS_MODEL="your-model"

# What would be queried — tune triage before paying for tokens:
uv run python -m vharness scan ~/my-repo --dry-run

# Scan → SARIF (GitHub code-scanning), Markdown, JSON reports:
uv run python -m vharness scan ~/my-repo --format sarif,markdown --out report

# Restrict to domains:
uv run python -m vharness scan ~/my-repo --analyzers shell,distroconf

# Score a model on the labeled corpus (P/R/F1, FP-rate on clean, CWE accuracy):
uv run python -m vharness eval

# Score on your own chat-format dataset (code in user turn, CWE labels in assistant turn):
uv run python -m vharness eval --dataset ~/data/val.jsonl --skip-corpus
```

## Compose freely with `run`

The presets are just compositions. `run` exposes the pipeline directly:

```bash
# one probe, one evaluator, custom concurrency:
uv run python -m vharness run ~/my-repo --probes shell --evaluators markdown,summary --workers 8

# corpus + dataset together, JSON verdicts with a full run log:
uv run python -m vharness run --probes corpus,chat-dataset --dataset val.jsonl \
    --evaluators metrics,json --log-file eval_log.jsonl
```

## Extending — third-party plugins

Plugins register via the `vharness.plugins` entry-point group, so a pip /
uv-installed package can add probes, generators, detectors, or evaluators
without forking. Minimal plugin package:

```toml
# my_plugins/pyproject.toml
[project.entry-points."vharness.plugins"]
my_plugins = "my_plugins"
```

```python
# my_plugins/__init__.py — import modules; their decorators register
from . import rust  # noqa: F401
```

```python
# my_plugins/rust.py
from vharness.probes.base import Probe, register_builtin

@register_builtin
class RustProbe(Probe):
    name = "rust"
    help = "unsafe Rust review"
    # FileProbe-style: extensions, strong_sinks, sinks, role, chunk()…
```

`vharness list` will then show `rust`. The same hook accepts generators
(implement `.generate(system, prompt) -> Generation`), detectors
(`.detect(attempt)`), and evaluators (`.evaluate(attempts, run_info)`).

**In-repo** domains are one file too: drop a module under
`src/vharness/probes/` following `domains.py`, import it in
`probes/__init__.py`.

## Optional: Inspect AI integration

With `pip install vharness[inspect]` (or `uv sync --extra inspect`), corpus
and dataset probes are exposed as [Inspect AI](https://inspect.aisi.org.uk)
tasks — you get Inspect's metrics, log viewer, and `eval_set` A/B machinery:

```python
from inspect_ai import eval
from vharness.inspect_adapter import corpus_task
eval(corpus_task(), model="openai/your-model")
```

## Design notes

- **No silent false negatives** — parse failures and API errors are statuses
  on the attempt (`ok`/`parse_error`/`api_error`), visible in every summary.
- **Cache-first** — SQLite response cache keyed by model+prompt; re-runs are
  free, `--no-cache` bypasses.
- **Dry-run everything** — `--dry-run` runs probes (discovery, triage,
  chunking) with zero model calls and no endpoint configured.
- **Untrusted input** — all code prompts carry an injection guard: analyzed
  content is data, never instructions; suggested patches are advisory.

## Layout

```
src/vharness/
  core.py            Attempt/Generation/Finding + registries + entry-point loading
  runner.py          orchestration, concurrency, JSONL run log
  cli.py             run/scan/eval/list
  probes/            base + FileProbe, domain probes, corpus & chat-dataset
  generators/        openai-compatible (retry/cache/stats), mock
  detectors/         json-verdict
  evaluators/        sarif, markdown, json, metrics, summary
  analyzers/         per-language chunkers & sink triage (used by probes)
  textutil.py        fence-stripping, balanced-JSON extraction, string masks
  sarif.py           SARIF 2.1.0 builder (CWE rules, fingerprints)
  inspect_adapter.py optional Inspect AI bridge
  eval_corpus/       ~35 hand-labeled samples (vulnerable + clean, all domains)
tests/               44 tests: pipeline, registry, chunkers, parsing, SARIF, metrics
```

The scanner grew out of a single-file SAST harness; the analyzers that chunk
C/C++, web languages, shell, and distro configs are still there — now driving
probes instead of being the whole app.
