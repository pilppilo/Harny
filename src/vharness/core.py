"""Core data model: Attempts, Generations, Findings, and the plugin registry.

The harness is a five-stage pipeline:

    Probe        yields Attempts (units of work: a prompt + context)
    Generator    turns an Attempt's prompt into a Generation (model I/O)
    Detector     judges a Generation, emitting Findings/verdicts
    Runner       orchestrates the above with concurrency + a JSONL run log
    Evaluator    consumes the run to produce reports/metrics

Plugins are discovered from installed packages via the ``vharness.plugins``
entry-point group, so third parties can extend the harness without touching
this codebase. Every stage is also usable standalone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

VERSION = "0.2.0"

# Plugin discovery group: packages declare
# [project.entry-points."vharness.plugins"] my_thing = "pkg.mod:MyThing"
ENTRY_POINT_GROUP = "vharness.plugins"

SEVERITIES = ("High", "Medium", "Low")
LEVEL_MAP = {"High": "error", "Medium": "warning", "Low": "note"}


@dataclass
class Finding:
    """A security issue attached to an Attempt's source context."""

    cwe: str
    severity: str
    sink: str
    explanation: str
    patch: str = ""
    file: str = ""
    line: int = 0
    function: str = ""

    @property
    def level(self) -> str:
        return LEVEL_MAP.get(self.severity, "warning")


@dataclass
class Generation:
    """A single model response with transport metadata."""

    text: str
    model: str = ""
    finish_reason: str = ""
    latency: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None
    cached: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class Attempt:
    """Unit of work: a prompt bound to its source context.

    ``context`` carries probe-specific metadata (file/line/function for scan
    attempts; ground-truth labels for eval attempts). ``findings`` and
    ``verdict`` are filled by detectors. Everything serializes to the run log,
    so runs are replayable and auditable after the fact.
    """

    prompt: str
    system: str = ""
    probe: str = ""
    source: str = ""  # file path or sample id
    context: dict = field(default_factory=dict)

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    generation: "Generation | None" = None
    findings: list[Finding] = field(default_factory=list)
    verdict: str = ""  # detector-set: e.g. "vulnerable"/"clean", "correct"/"incorrect"
    status: str = "pending"  # pending | ok | parse_error | api_error | skipped
    detector_notes: list[str] = field(default_factory=list)

    # Ground-truth fields (dataset probes); None = unlabeled (scan mode)
    expected_findings: list[Finding] | None = None
    expected_verdict: str | None = None

    def record(self, generation: "Generation") -> None:
        self.generation = generation
        if generation.error:
            self.status = "api_error"
        else:
            self.status = "ok"


class PluginRegistry:
    """Registry for one pipeline stage (probes, generators, detectors, evaluators)."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._items: dict[str, type] = {}

    def register(self, cls):
        if not getattr(cls, "name", None):
            raise ValueError(f"{cls.__name__} must define a 'name' attribute")
        if cls.name in self._items:
            raise ValueError(f"duplicate {self.stage} name: {cls.name!r}")
        self._items[cls.name] = cls
        return cls

    def get(self, name: str):
        try:
            return self._items[name]
        except KeyError:
            raise KeyError(
                f"unknown {self.stage} {name!r}; known: {sorted(self._items)}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._items)

    def instantiate(self, name: str, *args, **kwargs):
        """Create and cache one shared instance (stateless stages)."""
        if not hasattr(self, "_instances"):
            self._instances: dict[str, object] = {}
        if name not in self._instances:
            self._instances[name] = self.get(name)(*args, **kwargs)
        return self._instances[name]

    def help_for(self, name: str) -> str:
        """Human help without instantiating (some plugins need ctor args)."""
        return getattr(self.get(name), "help", "")

    def all_instances(self) -> list:
        return [self.instantiate(name) for name in self.names()]


def load_entry_points() -> None:
    """Merge plugins advertised by installed packages (idempotent).

    Two conventions are honored:
      * a class with a ``registry`` attribute → registered into that registry
      * a module/callable with ``register_plugins()`` → called; it registers
        whatever it wants (most flexible)
    """
    try:
        from importlib.metadata import entry_points
    except ImportError:  # py<3.10
        return
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            obj = ep.load()
        except Exception as e:  # noqa: BLE001 — a broken plugin shouldn't kill the app
            print(f"[!] plugin {ep.name} failed to load: {e}")
            continue
        if hasattr(obj, "register_plugins") and callable(obj.register_plugins):
            obj.register_plugins()
            continue
        reg = getattr(obj, "registry", None)
        if reg is not None and hasattr(reg, "register"):
            reg.register(obj)


PROBE_REGISTRY: PluginRegistry = PluginRegistry("probe")
GENERATOR_REGISTRY: PluginRegistry = PluginRegistry("generator")
DETECTOR_REGISTRY: PluginRegistry = PluginRegistry("detector")
EVALUATOR_REGISTRY: PluginRegistry = PluginRegistry("evaluator")
ALL_REGISTRIES = [PROBE_REGISTRY, GENERATOR_REGISTRY, DETECTOR_REGISTRY, EVALUATOR_REGISTRY]
