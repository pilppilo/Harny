"""Artifact publication checks."""

import pytest

from vharness.agent.artifacts import ArtifactStore
from vharness.agent.errors import IntegrityError
from vharness.agent.models import ArtifactRef


def test_artifact_store_publishes_and_verifies_content(tmp_path):
    store = ArtifactStore(tmp_path / "objects")
    reference = store.put(b"evidence", media_type="text/plain", provenance="fixture")

    assert store.read(reference) == b"evidence"
    assert (
        store.put(b"evidence", media_type="text/plain", provenance="fixture")
        == reference
    )


def test_artifact_store_rejects_missing_or_changed_required_evidence(tmp_path):
    store = ArtifactStore(tmp_path / "objects")
    reference = ArtifactRef("f" * 64, 1, "text/plain", "fixture")

    with pytest.raises(IntegrityError, match="missing"):
        store.read(reference)
