# Harny — LLM vulnerability scanner + fine-tune eval harness

Extendable harness for security-tuned LLMs: scan code across domains
(C/C++, web languages, shell, distro configs), export SARIF/Markdown reports,
and **eval** a model against labeled samples to measure whether fine-tuning
actually helps.

Works with any OpenAI-compatible endpoint: Ollama, vLLM, llama.cpp, LM
Studio, or any hosted provider that speaks the chat-completions API.

## Setup

```bash
uv sync            # creates .venv with deps
uv run pytest      # unit tests, no network needed
```

## Configuration

Point it at any OpenAI-compatible server:

```bash
export VHARNESS_BASE_URL="http://localhost:11434/v1"   # Ollama (vLLM: http://localhost:8000/v1)
export VHARNESS_API_KEY="..."                          # only if your server requires one
export VHARNESS_MODEL="your-model-name"
```

CLI flags `--base-url/--api-key/--model` override the env vars.

## Scan

```bash
# See what would be queried — zero API cost (tune triage before paying):
uv run python -m vharness scan ~/my-distro --dry-run

# Full scan of a distro repo (shell + configs + UI):
uv run python -m vharness scan ~/my-distro --format sarif,markdown --out report

# Just the web/JS layer:
uv run python -m vharness scan ~/my-distro/shell --analyzers web

# A C/C++ project:
uv run python -m vharness scan ~/myproject --analyzers ccpp

# Old entry point still works:
uv run python harny.py --dir ~/myproject --out report.sarif
```

Outputs: `report.sarif` (GitHub code-scanning compatible, with CWE rules and
stable fingerprints), `report.md` (human-readable, grouped by file/severity —
the "issues report" for the distro), `report.json`.

Triage: files without strong sink patterns are skipped; chunks within a file
are filtered again. Query failures are **never** silently treated as
"no vulnerability" — they surface in the summary and the cache makes re-runs
free.

## Eval — does the fine-tune actually work?

```bash
# Built-in labeled corpus (~35 vulnerable + clean samples across all domains):
uv run python -m vharness eval

# Compare two endpoints (e.g. fine-tune vs its base model):
uv run python -m vharness eval \
  --base-url http://localhost:8000/v1 --model my-fine-tune \
  --compare-base-url http://localhost:8000/v1 --compare-model base-model

# Pull code samples out of a chat-format JSONL dataset (OpenAI "messages" format):
uv run python -m vharness eval --from-dataset ~/data/val.jsonl --limit 100
```

Reports precision/recall/F1, false-positive rate on clean code, CWE-label
accuracy, per-CWE recall, latency and token cost. Writes `eval_report.md` plus
a per-sample detail JSON for error analysis. Dataset samples must have code in
the user turn and vulnerability/CWE labels in the assistant turn — non-code
Q&A records are skipped automatically.

## Adding a domain analyzer (one file)

Create `src/vharness/analyzers/<name>.py`:

```python
import re
from .base import Analyzer, Chunk, register

@register
class RustAnalyzer(Analyzer):
    name = "rust"
    extensions = (".rs",)
    strong_sinks = re.compile(r"unsafe\b|transmute|Command::new")
    system_prompt = Analyzer.build_system_prompt("Analyze this Rust code for …")

    def chunk(self, content: str, path: str = "") -> list[Chunk]:
        return [Chunk(name="file_scope", line=1, code=content)]
```

Import it in `src/vharness/analyzers/__init__.py` — the registry picks it up
everywhere (scan dispatch, `--analyzers`, eval language mapping).

## Layout

```
src/vharness/
  analyzers/   ccpp · web (js/ts/php/py/qml) · shell · distroconf (+ base/registry)
  scanner.py   discovery, triage, concurrency, dry-run, run stats
  llm.py       retries, truncation handling, JSON validation, SQLite cache
  eval.py      labeled-corpus + chat-dataset loaders, metrics, A/B compare
  sarif.py report.py   SARIF / Markdown / JSON outputs
  eval_corpus/ ~35 hand-labeled samples (vulnerable + clean) per domain
tests/         unit tests (chunkers, parsing, SARIF, metrics, registry)
```
