"""Verified content-addressed artifact publication."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .errors import IntegrityError, PersistenceError
from .models import ArtifactRef


class ArtifactStore:
    """Owns local bytes addressed by SHA-256 below one configured directory."""

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def put(self, data: bytes, *, media_type: str, provenance: str) -> ArtifactRef:
        """Atomically publish bytes after hashing and verifying the final object."""
        digest = hashlib.sha256(data).hexdigest()
        target = self._path_for(digest)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if target.exists():
            self._verify(target, digest, len(data))
            return ArtifactRef(digest, len(data), media_type, provenance)
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".pending-", dir=target.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            self._verify(temporary, digest, len(data))
            try:
                os.link(temporary, target)
            except FileExistsError:
                self._verify(target, digest, len(data))
            finally:
                temporary.unlink(missing_ok=True)
            self._sync_directory(target.parent)
        except OSError as exc:
            raise PersistenceError(
                f"could not publish artifact {digest}: {exc}"
            ) from exc
        return ArtifactRef(digest, len(data), media_type, provenance)

    def read(self, reference: ArtifactRef) -> bytes:
        """Read and verify a required artifact before returning its bytes."""
        path = self._path_for(reference.digest)
        if not path.is_file():
            raise IntegrityError(f"required artifact is missing: {reference.digest}")
        self._verify(path, reference.digest, reference.size)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise PersistenceError(
                f"could not read artifact {reference.digest}: {exc}"
            ) from exc

    def _path_for(self, digest: str) -> Path:
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise IntegrityError("invalid artifact digest")
        return self._root / digest[:2] / digest[2:]

    @staticmethod
    def _verify(path: Path, digest: str, size: int) -> None:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PersistenceError(f"could not verify artifact {path}: {exc}") from exc
        actual = hashlib.sha256(data).hexdigest()
        if actual != digest or len(data) != size:
            raise IntegrityError(f"artifact verification failed: {path}")

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
