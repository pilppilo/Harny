"""Project manifests and local run-state management for Vharness."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


MANIFEST_NAME = "vharness.project.toml"
STATE_DIR_NAME = ".vharness"
RUNS_DIR_NAME = "runs"
MANIFEST_SCHEMA_VERSION = 1


class WorkspaceError(ValueError):
    """A project manifest or local project-state error safe to show to users."""


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    source_roots: tuple[str, ...]
    default_profile: str | None = None
    schema_version: int = MANIFEST_SCHEMA_VERSION

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_NAME

    @property
    def state_dir(self) -> Path:
        return self.root / STATE_DIR_NAME

    @property
    def runs_dir(self) -> Path:
        return self.state_dir / RUNS_DIR_NAME


@dataclass(frozen=True)
class Run:
    project: Project
    run_id: str
    workflow: str
    path: Path

    @property
    def metadata_path(self) -> Path:
        return self.path / "run.json"

    @property
    def events_path(self) -> Path:
        return self.path / "events.jsonl"

    @property
    def reports_dir(self) -> Path:
        return self.path / "reports"


def _resolve_dir(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise WorkspaceError(f"project directory does not exist: {candidate}")
    if not candidate.is_dir():
        raise WorkspaceError(f"project path is not a directory: {candidate}")
    return candidate.resolve()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_source_roots(root: Path, source_roots: Any) -> tuple[str, ...]:
    if not isinstance(source_roots, list) or not source_roots:
        raise WorkspaceError("manifest source_roots must be a non-empty array of relative paths")
    validated: list[str] = []
    for item in source_roots:
        if not isinstance(item, str) or not item or Path(item).is_absolute():
            raise WorkspaceError("manifest source_roots entries must be non-empty relative paths")
        resolved = (root / item).resolve()
        if not _is_within(resolved, root):
            raise WorkspaceError(f"manifest source root escapes project directory: {item}")
        validated.append(item)
    return tuple(validated)


def _validate_state_dir(project: Project, *, create: bool) -> Path:
    state = project.state_dir
    if create:
        state.mkdir(mode=0o700, exist_ok=True)
    if state.exists():
        resolved = state.resolve()
        if not _is_within(resolved, project.root):
            raise WorkspaceError("project state directory must remain inside the project root")
    return state


def _validate_runs_dir(project: Project, *, create: bool) -> Path:
    state = _validate_state_dir(project, create=create)
    runs = project.runs_dir
    if create:
        runs.mkdir(mode=0o700, exist_ok=True)
    if runs.exists():
        resolved_state = state.resolve()
        resolved_runs = runs.resolve()
        if not _is_within(resolved_runs, resolved_state):
            raise WorkspaceError("project run directory must remain inside the project state directory")
    return runs


def _validate_run_path(run: Run) -> None:
    """Reject links or paths that could escape the project-owned run directory."""
    runs_dir = _validate_runs_dir(run.project, create=False)
    if run.path.is_symlink() or run.path.resolve().parent != runs_dir.resolve():
        raise WorkspaceError(f"project run directory escapes local state: {run.path}")
    if run.metadata_path.is_symlink() or run.metadata_path.resolve().parent != run.path.resolve():
        raise WorkspaceError(f"project run metadata escapes local state: {run.metadata_path}")


def resolve_project(path: str | Path) -> Project:
    """Load and validate one explicit project directory."""
    root = _resolve_dir(path)
    manifest = root / MANIFEST_NAME
    if not manifest.is_file():
        raise WorkspaceError(f"project manifest not found: {manifest}")
    try:
        with manifest.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise WorkspaceError(f"invalid project manifest: {manifest}: {exc}") from exc
    if not isinstance(data, dict):  # pragma: no cover - tomllib always returns dict
        raise WorkspaceError("project manifest must contain a TOML table")
    version = data.get("schema_version")
    if version != MANIFEST_SCHEMA_VERSION:
        raise WorkspaceError(
            f"unsupported project manifest schema_version {version!r}; expected {MANIFEST_SCHEMA_VERSION}"
        )
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WorkspaceError("manifest name must be a non-empty string")
    profile = data.get("default_profile")
    if profile is not None and (not isinstance(profile, str) or not profile.strip()):
        raise WorkspaceError("manifest default_profile must be a non-empty string when set")
    project = Project(
        root=root,
        name=name.strip(),
        source_roots=_validate_source_roots(root, data.get("source_roots")),
        default_profile=profile.strip() if isinstance(profile, str) else None,
        schema_version=version,
    )
    _validate_state_dir(project, create=False)
    return project


def _toml_string(value: str) -> str:
    return json.dumps(value)


def initialize_project(
    path: str | Path,
    *,
    name: str | None = None,
    source_roots: list[str] | None = None,
    default_profile: str | None = None,
    add_gitignore: bool = True,
) -> Project:
    """Create a new manifest and private local-state directory without replacing files."""
    root_path = Path(path).expanduser()
    root_path.mkdir(parents=True, exist_ok=True)
    root = _resolve_dir(root_path)
    manifest = root / MANIFEST_NAME
    if manifest.exists():
        raise WorkspaceError(f"project manifest already exists: {manifest}")
    project_name = (name or root.name).strip()
    if not project_name:
        raise WorkspaceError("project name must be a non-empty string")
    roots = source_roots or ["."]
    _validate_source_roots(root, roots)
    if default_profile is not None and not default_profile.strip():
        raise WorkspaceError("default profile must be a non-empty string when set")
    lines = [
        f"schema_version = {MANIFEST_SCHEMA_VERSION}",
        f"name = {_toml_string(project_name)}",
        "source_roots = [" + ", ".join(_toml_string(item) for item in roots) + "]",
    ]
    if default_profile:
        lines.append(f"default_profile = {_toml_string(default_profile.strip())}")
    _atomic_write(manifest, "\n".join(lines) + "\n")
    project = resolve_project(root)
    _validate_state_dir(project, create=True)
    if add_gitignore:
        _add_gitignore_rule(root)
    return project


def _add_gitignore_rule(root: Path) -> None:
    path = root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rules = {line.strip() for line in existing.splitlines()}
    if STATE_DIR_NAME + "/" in rules or STATE_DIR_NAME in rules:
        return
    suffix = "" if not existing or existing.endswith("\n") else "\n"
    _atomic_write(path, existing + suffix + "# Vharness local run state\n.vharness/\n")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def _read_metadata(run: Run) -> dict[str, Any]:
    _validate_run_path(run)
    try:
        data = json.loads(run.metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"invalid run metadata: {run.metadata_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"invalid run metadata: {run.metadata_path}")
    return data


def _write_metadata(run: Run, data: dict[str, Any]) -> None:
    _validate_run_path(run)
    _atomic_write(run.metadata_path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def create_run(project: Project, workflow: str, normalized_inputs: dict[str, Any]) -> Run:
    """Allocate a project-local run directory and persist immutable inputs."""
    if workflow not in {"run", "scan", "eval", "assess"}:
        raise WorkspaceError(f"unsupported project workflow: {workflow}")
    _validate_state_dir(project, create=True)
    runs_dir = _validate_runs_dir(project, create=True)
    for _ in range(10):
        run_id = uuid.uuid4().hex[:12]
        path = runs_dir / run_id
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:  # pragma: no cover - UUID collision is extraordinarily unlikely
            continue
        run = Run(project=project, run_id=run_id, workflow=workflow, path=path)
        run.reports_dir.mkdir(mode=0o700)
        now = time.time()
        _write_metadata(run, {
            "schema_version": 1,
            "run_id": run_id,
            "workflow": workflow,
            "status": "created",
            "created_at": now,
            "project": {
                "name": project.name,
                "root": str(project.root),
                "manifest_schema_version": project.schema_version,
            },
            "inputs": normalized_inputs,
            "outputs": {},
        })
        return run
    raise WorkspaceError("could not allocate a unique project run ID")


def update_run(run: Run, *, status: str | None = None, outputs: dict[str, str] | None = None,
               exit_code: int | None = None, stop_reason: str | None = None) -> dict[str, Any]:
    """Atomically update mutable run lifecycle fields."""
    data = _read_metadata(run)
    if status is not None:
        if status not in {"created", "running", "completed", "failed", "cancelled"}:
            raise WorkspaceError(f"invalid run status: {status}")
        data["status"] = status
        data[f"{status}_at"] = time.time()
    if outputs is not None:
        data["outputs"] = dict(outputs)
    if exit_code is not None:
        data["exit_code"] = exit_code
    if stop_reason is not None:
        data["stop_reason"] = stop_reason
    _write_metadata(run, data)
    return data


def list_runs(project: Project) -> list[dict[str, Any]]:
    """Return newest-first run metadata, retaining corrupt entries as diagnostics."""
    runs_dir = _validate_runs_dir(project, create=False)
    if not runs_dir.exists():
        return []
    entries: list[dict[str, Any]] = []
    for path in runs_dir.iterdir():
        if not path.is_dir():
            continue
        run = Run(project=project, run_id=path.name, workflow="unknown", path=path)
        try:
            data = _read_metadata(run)
        except WorkspaceError as exc:
            entries.append({"run_id": path.name, "status": "corrupt", "error": str(exc)})
        else:
            entries.append(data)
    return sorted(entries, key=lambda item: item.get("created_at", 0), reverse=True)
