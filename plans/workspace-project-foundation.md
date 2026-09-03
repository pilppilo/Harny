# Workspace and project foundation: v0

> Status: implemented in commit `2b7e6e4` (`Add project workspace foundation`).
> Verified with 84 passing tests.

## Delivered v0

- `vharness project init`, `project status`, and `project runs` manage explicit
  local projects.
- `vharness run`, `scan`, and `eval` accept `--project PATH` while retaining
  their standalone behavior when it is omitted.
- Project-scoped runs receive an isolated ID, lifecycle metadata, default event
  log/report paths, and a `.vharness/runs/<run-id>/` home.
- Manifest, run-state, and symlink-confinement validation are covered by unit
  and CLI integration tests.

Dynamic assessments and the TUI remain unimplemented. They can now depend on
the project/run service instead of inventing their own storage layout.

## Objective

Introduce a small, local project/workspace model before dynamic assessments or
the TUI are implemented. A project gives runs, reports, assessment sessions,
and evidence one predictable home while preserving Vharness's existing
standalone CLI behavior.

This is the prerequisite foundation for `dynamic-safe-method-assessment.md`
and `tui-operator-console.md`.

## Scope

A project is a directory containing a tracked, non-secret manifest:

```text
project-root/
  vharness.project.toml       # tracked project metadata
  .vharness/                  # ignored local run state and artifacts
```

Initial manifest schema:

```toml
schema_version = 1
name = "example-service"
source_roots = ["."]
default_profile = "local"
```

`default_profile` is only a profile name. Endpoint URLs, API keys,
authorization headers, target credentials, assessment allowlists, and policy
grants are never stored in this file.

The local state layout is:

```text
.vharness/
  runs/
    <run-id>/
      run.json                # lifecycle metadata and immutable inputs
      events.jsonl            # core-produced run/event export when available
      reports/                # generated Markdown, JSON, SARIF, metrics, etc.
      assessment.sqlite3      # dynamic sessions only
      artifacts/              # dynamic evidence only
```

The project initializer adds `.vharness/` to the project's ignore rules when
appropriate. It must not overwrite an existing ignore file, manifest, source
tree, or run data without an explicit operator choice.

## User-facing commands

Add a small project command group:

```bash
vharness project init [PATH]
vharness project status --project PATH
vharness project runs --project PATH
```

`project init` creates a manifest after showing the resolved project root and
planned local-state directory. It refuses to replace an existing manifest.

All existing workflows accept an optional `--project PATH`:

```bash
vharness run --project . --probes web src/
vharness scan --project . src/
vharness eval --project .
```

When `--project` is provided, Vharness validates the manifest, creates one
run directory, records lifecycle metadata, and places default logs/reports
there. Existing explicit output flags remain supported and are recorded as
external output locations. When `--project` is omitted, current standalone
behavior is unchanged.

Phase-1 dynamic assessment requires `--project`; it writes its authoritative
SQLite state, ordered event export, and evidence artifacts to that run's local
state directory. The dynamic command still requires its own literal-loopback
target and fixed safe-method policy; project membership does not authorize a
target.

Project discovery is explicit in v0: commands use `--project PATH`, and the
TUI asks an operator to select or initialize a project. Automatic upward
directory discovery is deferred until its symlink, nesting, and ambiguity
semantics are separately designed and tested.

## Run lifecycle

Every project-scoped launch gets a unique run ID and records:

- workflow (`scan`, `eval`, or later `assess`);
- project manifest schema/version and resolved project root;
- immutable normalized inputs and non-secret configuration provenance;
- created, started, completed, cancelled, or failed status;
- timestamps, exit status, stop reason when applicable, and report locations.

Create `run.json` before execution. Update lifecycle state atomically so an
interrupted run remains visible as interrupted/unknown rather than appearing
successfully complete. Never store API keys, raw authorization/cookie headers,
or unredacted dynamic evidence in it.

`project runs` lists records from run directories without mutating them and
reports corrupt or incomplete metadata clearly. It supports filtering by
workflow, status, and time once the basic list is stable.

## Compatibility and boundaries

- Existing `scan`, `run`, `eval`, `replay`, `list`, and `usage` semantics work
  without a project exactly as they do today.
- Existing JSONL and report paths remain readable; project mode does not move
  or rewrite historical output.
- A project is local organization, not a sandbox, authorization system,
  workspace scheduler, Git worktree manager, collaboration model, or cloud
  synchronization service.
- Source roots are descriptive defaults for launch forms and status output;
  they do not create filesystem permissions or restrict arbitrary standalone
  scan targets in v0.
- The project manifest must be treated as untrusted repository input. Validate
  schema and paths, show normalized values to the operator, and never execute
  commands or load code from it.

## Core interfaces

Create a narrow project/run service layer used by both CLI and later TUI:

```text
resolve_project(path) -> Project
initialize_project(path, metadata) -> Project
create_run(project, workflow, normalized_inputs) -> Run
start_run(run) / finish_run(run, outcome) / cancel_run(run, outcome)
list_runs(project, filters) -> list[Run]
```

The service owns manifest validation, state-layout creation, atomic lifecycle
updates, and safe path joining. Workflow implementations supply normalized
inputs and output records; they do not construct paths from user-provided run
IDs or artifact names.

## Test plan

- Initialize an empty project and reject an existing manifest without
  modification.
- Preserve an existing `.gitignore` while adding an idempotent `.vharness/`
  rule when requested.
- Reject malformed manifests, unsupported schema versions, traversal paths,
  and state directories escaping the resolved project root.
- Verify project-scoped scan/eval runs create isolated IDs, metadata, and
  default output locations.
- Verify a failed or interrupted run has accurate persisted lifecycle state.
- Verify standalone commands remain byte-for-byte compatible where practical
  and do not create project state.
- Verify explicit external output paths are recorded but never deleted or
  rewritten by project cleanup.
- Verify no secret values enter manifests, run metadata, ordinary logs, or the
  project-status display.

## Implementation order

1. ~~Manifest schema, project resolution, safe state-layout helpers, and unit
   tests.~~
2. ~~`project init`, `status`, and `runs` CLI commands.~~
3. ~~Run lifecycle metadata and `--project` support for `run`, `scan`, and
   `eval`.~~
4. ~~Project-aware report/log defaults with standalone compatibility tests.~~
5. Require project context for the dynamic safe-method assessment milestone.
6. Use the same project/run service from the TUI.

## Completion criteria

Workspace v0 is complete: an operator can initialize a project, run an
existing generic run, scan, or eval into a self-contained local run directory,
reopen its status and outputs later, and still run all existing workflows
without a project. Dynamic assessment and the TUI may now consume this
contract.
