"""Optional Inspect AI adapter: run vharness probes/detectors inside Inspect.

Import this module only when ``inspect-ai`` is installed (``pip install
vharness[inspect]``). It exposes each vharness dataset probe as an Inspect
``@task`` so you get Inspect's metrics, logging, viewer, and eval_set A/B
machinery over the same corpus.

Usage::

    python -c "from vharness.inspect_adapter import register; register()"
    inspect eval vharness.inspect_adapter:corpus_task --model openai/<name>

or programmatically::

    from inspect_ai import eval
    from vharness.inspect_adapter import corpus_task
    eval(corpus_task(), model="...")
"""

from __future__ import annotations

from .core import Finding
from .probes import dataset as _ds

try:
    from inspect_ai import Task, task
    from inspect_ai.dataset import Sample
    from inspect_ai.scorer import CORRECT, INCORRECT, Score, Scorer, Target, accuracy, scorer
    from inspect_ai.solver import TaskState, generate
except ImportError as e:  # pragma: no cover — only hit without the extra
    raise ImportError(
        "inspect-ai is not installed; install with: uv sync --extra inspect "
        "(or pip install 'vharness[inspect]')"
    ) from e


def _samples(probe_name: str, **probe_kwargs):
    probe = _ds.CorpusProbe() if probe_name == "corpus" else _ds.ChatDatasetProbe()
    attempts = probe.attempts(**probe_kwargs)
    out = []
    for i, a in enumerate(attempts):
        expected = "vulnerable" if a.expected_verdict == "vulnerable" else "clean"
        out.append(
            Sample(
                id=str(i),
                input=a.prompt,
                target=expected,
                metadata={
                    "system": a.system,
                    "source": a.source,
                    "language": a.context.get("language", ""),
                    "expected_cwes": [f.cwe for f in (a.expected_findings or []) if f.cwe != "CWE-0"],
                },
            )
        )
    return out


@scorer(metrics=[accuracy()])
def json_verdict_scorer() -> Scorer:
    """Reuse vharness's JSONVerdict detector as an Inspect scorer."""
    from .detectors.json_verdict import JSONVerdict
    from .core import Attempt as VAttempt, Generation as VGeneration

    detector = JSONVerdict()

    async def score(state: TaskState, target: Target) -> Score:
        attempt = VAttempt(prompt=state.user_prompt.text, system="")
        attempt.record(VGeneration(text=state.output.completion or "", model="inspect"))
        detector.detect(attempt)
        expected = target.text
        predicted = "vulnerable" if attempt.verdict == "vulnerable" else "clean"
        correct = predicted == expected
        return Score(
            value=CORRECT if correct else INCORRECT,
            answer=predicted,
            explanation="; ".join(attempt.detector_notes) or attempt.verdict,
        )

    return score


def _make_task(probe_name: str, **probe_kwargs) -> Task:
    return Task(
        dataset=_samples(probe_name, **probe_kwargs),
        solver=[generate()],
        scorer=json_verdict_scorer(),
    )


@task
def corpus_task() -> Task:
    """The built-in labeled corpus as an Inspect eval task."""
    return _make_task("corpus")


@task
def chat_dataset_task(path: str, limit: int | None = None) -> Task:
    """A chat-format JSONL dataset as an Inspect eval task."""
    return _make_task("chat-dataset", path=path, limit=limit)
