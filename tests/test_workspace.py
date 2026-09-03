import json

import pytest

from vharness.workspace import (
    WorkspaceError,
    create_run,
    initialize_project,
    list_runs,
    resolve_project,
    update_run,
)


def test_initialize_project_writes_manifest_state_and_ignore_rule(tmp_path):
    project = initialize_project(tmp_path, name="Demo", default_profile="local")

    assert project.name == "Demo"
    assert project.manifest_path.exists()
    assert project.state_dir.is_dir()
    assert (tmp_path / ".gitignore").read_text() == "# Vharness local run state\n.vharness/\n"

    loaded = resolve_project(tmp_path)
    assert loaded == project
    with pytest.raises(WorkspaceError, match="already exists"):
        initialize_project(tmp_path)


def test_project_rejects_source_root_that_escapes_root(tmp_path):
    (tmp_path / "vharness.project.toml").write_text(
        'schema_version = 1\nname = "bad"\nsource_roots = ["../outside"]\n'
    )
    with pytest.raises(WorkspaceError, match="escapes"):
        resolve_project(tmp_path)


def test_run_lifecycle_is_persisted_and_listed_newest_first(tmp_path):
    project = initialize_project(tmp_path, add_gitignore=False)
    first = create_run(project, "scan", {"targets": ["src"]})
    update_run(first, status="running", outputs={"log_file": str(first.events_path)})
    update_run(first, status="completed", exit_code=0, stop_reason="complete")

    second = create_run(project, "eval", {"limit": 2})
    runs = list_runs(project)

    assert [item["run_id"] for item in runs] == [second.run_id, first.run_id]
    first_data = json.loads(first.metadata_path.read_text())
    assert first_data["status"] == "completed"
    assert first_data["exit_code"] == 0
    assert first_data["outputs"]["log_file"] == str(first.events_path)


def test_list_runs_marks_symlinked_run_as_corrupt_without_reading_it(tmp_path):
    project = initialize_project(tmp_path, add_gitignore=False)
    project.runs_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "run.json").write_text('{"status": "completed", "secret": "outside"}')
    (project.runs_dir / "linked-run").symlink_to(outside, target_is_directory=True)

    runs = list_runs(project)

    assert runs[0]["run_id"] == "linked-run"
    assert runs[0]["status"] == "corrupt"
    assert "escapes local state" in runs[0]["error"]


def test_project_scoped_scan_uses_isolated_defaults_and_preserves_standalone(tmp_path, capsys):
    source = tmp_path / "sample.py"
    source.write_text("print('hello')\n")
    project = initialize_project(tmp_path, add_gitignore=False)

    from vharness.cli import main

    assert main([
        "scan", "--project", str(tmp_path), str(source), "--generator", "mock",
        "--format", "json", "-q",
    ]) == 0
    capsys.readouterr()

    runs = list_runs(project)
    assert len(runs) == 1
    run = runs[0]
    run_dir = project.runs_dir / run["run_id"]
    assert run["workflow"] == "scan"
    assert run["status"] == "completed"
    assert (run_dir / "events.jsonl").exists()
    assert (run_dir / "reports" / "report.json").exists()
    assert not (tmp_path / "scan_log.jsonl").exists()
    assert not (tmp_path / "report.json").exists()


def test_project_scoped_generic_run_uses_project_event_log(tmp_path, capsys):
    project = initialize_project(tmp_path, add_gitignore=False)
    from vharness.cli import main

    assert main([
        "run", "--project", str(tmp_path), "--probes", "corpus", "--limit", "1",
        "--generator", "mock", "-q",
    ]) == 0
    capsys.readouterr()

    runs = list_runs(project)
    assert len(runs) == 1
    run = runs[0]
    assert run["workflow"] == "run"
    assert run["status"] == "completed"
    assert (project.runs_dir / run["run_id"] / "events.jsonl").exists()
    assert not (tmp_path / "scan_log.jsonl").exists()


def test_standalone_scan_retains_legacy_default_outputs(tmp_path, monkeypatch):
    source = tmp_path / "sample.py"
    source.write_text("print('hello')\n")
    monkeypatch.chdir(tmp_path)

    from vharness.cli import main

    assert main(["scan", str(source), "--generator", "mock", "--format", "json", "-q"]) == 0
    assert (tmp_path / "scan_log.jsonl").exists()
    assert (tmp_path / "report.json").exists()
    assert not (tmp_path / ".vharness").exists()


def test_project_cli_init_status_and_empty_runs(tmp_path, capsys):
    root = tmp_path / "project"
    from vharness.cli import main

    assert main(["project", "init", str(root), "--name", "CLI Project"]) == 0
    assert "Initialized Vharness project: CLI Project" in capsys.readouterr().out
    assert main(["project", "status", "--project", str(root)]) == 0
    assert "Project: CLI Project" in capsys.readouterr().out
    assert main(["project", "runs", "--project", str(root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []
