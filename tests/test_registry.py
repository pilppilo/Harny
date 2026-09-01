"""Plugin registry behavior."""

import pytest

from vharness.core import (
    DETECTOR_REGISTRY,
    EVALUATOR_REGISTRY,
    GENERATOR_REGISTRY,
    PROBE_REGISTRY,
    PluginRegistry,
)


def test_builtin_registrations_loaded():
    import vharness.probes  # noqa: F401
    import vharness.generators  # noqa: F401
    import vharness.detectors  # noqa: F401
    import vharness.evaluators  # noqa: F401

    for name in ("ccpp", "web", "shell", "distroconf", "corpus", "chat-dataset"):
        assert name in PROBE_REGISTRY.names()
    assert "openai" in GENERATOR_REGISTRY.names()
    assert "mock" in GENERATOR_REGISTRY.names()
    assert "json-verdict" in DETECTOR_REGISTRY.names()
    for name in ("sarif", "markdown", "json", "summary", "metrics"):
        assert name in EVALUATOR_REGISTRY.names()


def test_registry_rejects_duplicates():
    reg = PluginRegistry("test")
    reg.register(type("A", (), {"name": "x"}))
    with pytest.raises(ValueError):
        reg.register(type("B", (), {"name": "x"}))


def test_registry_rejects_unnamed():
    reg = PluginRegistry("test")
    with pytest.raises(ValueError):
        reg.register(type("NoName", (), {}))


def test_registry_get_unknown_raises_with_names():
    reg = PluginRegistry("test")
    reg.register(type("A", (), {"name": "x"}))
    with pytest.raises(KeyError) as e:
        reg.get("nope")
    assert "known" in str(e.value)
