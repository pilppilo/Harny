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

import threading
import uuid
import weakref
from collections.abc import Sequence
from dataclasses import dataclass, field

from .log import log

VERSION = "0.2.0"

# Plugin discovery group: packages declare
# [project.entry-points."vharness.plugins"] my_thing = "pkg.mod:MyThing"
ENTRY_POINT_GROUP = "vharness.plugins"
_LOADED_ENTRY_POINTS: set[tuple[str, str, str]] = set()
# Entry-point imports may register decorators while activation is in progress.
# Keep registry access and activation in one re-entrant critical section.
_PLUGIN_LOCK = threading.RLock()

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

    _known_registries: weakref.WeakSet = weakref.WeakSet()

    def __init__(self, stage: str) -> None:
        self.stage = stage
        self._items: dict[str, type] = {}
        with _PLUGIN_LOCK:
            self._known_registries.add(self)

    def register(self, cls):
        with _PLUGIN_LOCK:
            if not getattr(cls, "name", None):
                raise ValueError(f"{cls.__name__} must define a 'name' attribute")
            if cls.name in self._items:
                raise ValueError(f"duplicate {self.stage} name: {cls.name!r}")
            self._items[cls.name] = cls
            return cls

    def get(self, name: str):
        with _PLUGIN_LOCK:
            try:
                return self._items[name]
            except KeyError:
                raise KeyError(
                    f"unknown {self.stage} {name!r}; known: {sorted(self._items)}"
                ) from None

    def names(self) -> list[str]:
        with _PLUGIN_LOCK:
            return sorted(self._items)

    def instantiate(self, name: str, *args, **kwargs):
        """Create and cache one shared instance (stateless stages)."""
        with _PLUGIN_LOCK:
            if not hasattr(self, "_instances"):
                self._instances: dict[str, object] = {}
            if name not in self._instances:
                self._instances[name] = self.get(name)(*args, **kwargs)
            return self._instances[name]

    def help_for(self, name: str) -> str:
        """Human help without instantiating (some plugins need ctor args)."""
        with _PLUGIN_LOCK:
            return getattr(self.get(name), "help", "")

    def all_instances(self) -> list:
        return [self.instantiate(name) for name in self.names()]


def _registry_snapshot() -> dict[PluginRegistry, tuple[dict[str, type], dict[str, object] | None]]:
    """Copy registry state while the shared plugin lock is held."""
    return {
        registry: (
            dict(registry._items),
            dict(registry._instances) if hasattr(registry, "_instances") else None,
        )
        for registry in list(PluginRegistry._known_registries)
    }


def _restore_registry_snapshot(snapshot: dict[PluginRegistry, tuple[dict[str, type], dict[str, object] | None]]) -> None:
    """Restore all known registries, including ones created by a failed import."""
    registries = set(PluginRegistry._known_registries) | set(snapshot)
    for registry in registries:
        items, instances = snapshot.get(registry, ({}, None))
        registry._items.clear()
        registry._items.update(items)
        if instances is None:
            if hasattr(registry, "_instances"):
                del registry._instances
        else:
            registry._instances = dict(instances)


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
    with _PLUGIN_LOCK:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            identity = (getattr(ep, "group", ENTRY_POINT_GROUP), ep.name, ep.value)
            if identity in _LOADED_ENTRY_POINTS:
                continue
            snapshot = _registry_snapshot()
            try:
                obj = ep.load()
                if hasattr(obj, "register_plugins") and callable(obj.register_plugins):
                    obj.register_plugins()
                else:
                    reg = getattr(obj, "registry", None)
                    if reg is None or not hasattr(reg, "register"):
                        raise ValueError("entry point exposes neither register_plugins() nor a registry")
                    reg.register(obj)
            except Exception as e:  # noqa: BLE001 — third-party plugin failures are contained
                _restore_registry_snapshot(snapshot)
                log.warning("plugin entry point %s (%s) failed to activate: %s", ep.name, ep.value, e)
                continue
            _LOADED_ENTRY_POINTS.add(identity)


PROBE_REGISTRY: PluginRegistry = PluginRegistry("probe")
GENERATOR_REGISTRY: PluginRegistry = PluginRegistry("generator")
DETECTOR_REGISTRY: PluginRegistry = PluginRegistry("detector")
EVALUATOR_REGISTRY: PluginRegistry = PluginRegistry("evaluator")
ALL_REGISTRIES = [PROBE_REGISTRY, GENERATOR_REGISTRY, DETECTOR_REGISTRY, EVALUATOR_REGISTRY]


def normalize_names(value, default: list[str], *, field: str = "selection") -> list[str]:
    """Normalize a comma-delimited name string or a sequence of names.

    Empty values use the caller-provided explicit default. Keeping this in core
    ensures CLI and programmatic runner callers use the same contract.
    """
    if value is None:
        return list(default)
    if isinstance(value, str):
        values = value.split(",")
    elif not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a comma-separated string or a sequence of strings; got {value!r}")
    else:
        values = value
    for item in values:
        if not isinstance(item, str):
            raise ValueError(f"{field} must contain only strings; got {item!r}")
    names = [item.strip() for item in values if item.strip()]
    return names or list(default)
