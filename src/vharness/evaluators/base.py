"""Evaluator base: turns finished runs into reports and metrics."""

from __future__ import annotations

from ..core import Attempt, EVALUATOR_REGISTRY



__all__ = ['Evaluator', 'register_builtin']
class Evaluator:
    """Consumes a completed run's Attempts to produce an artifact.

    Evaluators are sinks: SARIF/markdown/JSON report writers, metric
    calculators, threshold gates, trend updaters. They receive the full
    attempt list and a run_info dict, and write wherever they need to.
    """

    name: str = ""
    help: str = ""

    def evaluate(self, attempts: list[Attempt], run_info: dict) -> None:
        raise NotImplementedError


def register_builtin(cls):
    return EVALUATOR_REGISTRY.register(cls)
