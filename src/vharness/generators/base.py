"""Generator base: the model-I/O stage."""

from __future__ import annotations

from ..core import GENERATOR_REGISTRY, Generation



__all__ = ['Generator', 'register_builtin']
class Generator:
    """Turns a prompt (+ system prompt) into a Generation.

    Implementations wrap model APIs (OpenAI-compatible HTTP, local runtimes,
    replayed logs, deterministic test doubles). They must never raise on a
    model/transport failure — record it in ``Generation.error`` so the run
    continues and the failure is visible in the log.
    """

    name: str = ""
    help: str = ""

    def generate(self, system: str, prompt: str) -> Generation:
        raise NotImplementedError


def register_builtin(cls):
    return GENERATOR_REGISTRY.register(cls)
