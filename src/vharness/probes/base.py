"""Probe base classes: sources of Attempts."""

from __future__ import annotations

from ..core import Attempt, PROBE_REGISTRY


class Probe:
    """A source of Attempts.

    Probes find *what to analyze*: they walk a target (filesystem, dataset,
    anything), triage, chunk, and yield Attempts with prompts and context.
    They never call models — that's the Generator's job.

    Subclasses implement ``attempts(**kwargs)`` (an iterable of Attempt) and
    declare a ``name``. Register with ``@register_builtin`` (built-ins) or via
    the ``vharness.plugins`` entry point (third-party).
    """

    name: str = ""
    #: Short help shown by ``vharness list``.
    help: str = ""

    def attempts(self, **kwargs) -> list[Attempt]:
        raise NotImplementedError


def register_builtin(cls):
    """Decorator for probes shipped with the harness."""
    return PROBE_REGISTRY.register(cls)
