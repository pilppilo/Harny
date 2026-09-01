"""Detector base: judges a Generation and annotates the Attempt."""

from __future__ import annotations

from ..core import Attempt, DETECTOR_REGISTRY


class Detector:
    """Judges an Attempt's Generation.

    Detectors set ``attempt.verdict`` (free-form, e.g. "vulnerable" /
    "correct") and may append ``Finding`` objects and ``detector_notes``.
    They must be cheap, deterministic, and never perform model I/O —
    model-graded detectors belong in a future Generator-backed stage.
    """

    name: str = ""
    help: str = ""

    def detect(self, attempt: Attempt) -> None:
        raise NotImplementedError


def register_builtin(cls):
    return DETECTOR_REGISTRY.register(cls)
