"""vharness: a pluggable LLM security harness (probe → generator → detector → evaluator)."""

from .core import (
    ALL_REGISTRIES,
    Attempt,
    DETECTOR_REGISTRY,
    EVALUATOR_REGISTRY,
    Finding,
    Generation,
    GENERATOR_REGISTRY,
    PROBE_REGISTRY,
    VERSION,
    load_entry_points,
)

__version__ = VERSION

__all__ = [
    "VERSION",
    "Attempt",
    "Finding",
    "Generation",
    "PROBE_REGISTRY",
    "GENERATOR_REGISTRY",
    "DETECTOR_REGISTRY",
    "EVALUATOR_REGISTRY",
    "ALL_REGISTRIES",
    "load_entry_points",
]
