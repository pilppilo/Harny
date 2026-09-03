# TUI operator console: initial plan

> Status: planned. Its Workspace v0 prerequisite was completed in commit
> `2b7e6e4`; the TUI itself has not been started.

## Objective

Add an optional terminal user interface that makes Vharness easier to operate
locally before a browser dashboard exists. The TUI is an operator console: it
launches and observes the same core workflows as the CLI, reads the same
authoritative state, and never becomes a second assessment engine.

It follows the Workspace v0 prerequisite defined in
`workspace-project-foundation.md`, is useful with the existing `scan` and
`eval` workflows, then extends to the dynamic safe-method assessment milestone
defined in `dynamic-safe-method-assessment.md`.

## Product boundary

```text
CLI and TUI
    -> shared project/run service and Vharness runner API
    -> assessment policy and executor (when available)
    -> JSONL runs / SQLite session events / evidence artifacts
```

The TUI does not implement its own planner loop, HTTP client, scope validation,
policy decisions, persistence format, or target interaction. A TUI operation
must map to an equivalent documented CLI/core operation.

## Packaging

- Ship the TUI as an optional dependency, for example `vharness[tui]`, so the
  default CLI installation remains lightweight.
- Use Textual unless a short technical spike shows it cannot meet the test or
  accessibility requirements.
- Expose an explicit entry point such as `vharness tui`; importing Vharness or
  running a normal CLI command never starts an interactive UI.
- Keep UI presentation, state adaptation, and core operations in separate
  modules so noninteractive tests do not require a terminal.

## Initial screens

### 1. Runs

List recent local scan, eval, and assessment sessions. Each row shows:

- workflow and status;
- target or source path;
- model/profile when available;
- start time and duration;
- finding/result count;
- JSONL, SQLite, and report locations.

An operator can reopen a completed run using its existing JSONL or SQLite
state. The TUI must tolerate missing, moved, malformed, or older log files and
show a clear error without altering them.

Runs are scoped to an explicitly selected Workspace v0 project. The TUI can
initialize a project through the same core service or ask the operator to
select one; it does not auto-discover project roots in the initial release.

### 2. Launch

Provide structured forms for existing operations:

- `scan`: source targets, analyzers/probes, formats, output location;
- `eval`: corpus/dataset, model/profile, output location;
- `assess` when Phase 1 is available: target, safe-method mode, decision/
  request/redirect/duration budgets, state path, and export path.

The screen validates basic input before launch and displays the equivalent CLI
command for review. It must not expose a free-form shell command field or use
an operator-entered command string for execution.

### 3. Live run

Show event or CLI progress for one active run:

- current phase, elapsed time, and terminal status;
- model queries, token/latency data, cache status, and errors when available;
- incremental logs with filtering/search;
- a clean cancel control;
- the final stop reason and report locations.

Cancellation invokes the same core cancellation mechanism as the CLI. Until a
shared cancellation API exists, it may manage only the subprocess it launched,
send an interrupt, wait for completion, and report the outcome; it must not
kill unrelated processes.

### 4. Details

For static runs, show filterable findings by severity, CWE, source path,
status, and evaluator. A finding view includes source location, model
explanation, suggested patch, detector notes, and report references.

For dynamic sessions, enabled only once Phase 1 exists, show:

- a persistent scope, safe-method, and budget warning banner;
- ordered planner-action, policy-decision, HTTP-result, observation, and error
  events;
- separately derived counts for decisions, requests, rejections, observations,
  and runtime errors;
- bounded evidence previews plus metadata such as requested/effective URL,
  content type, byte count, truncation, hash, and capture time;
- stop and export controls.

The dynamic view reads committed SQLite events and core-produced exports. It
does not infer or invent findings from observations.

## Configuration and status

Provide a non-secret status view that shows:

- resolved endpoint, model, and profile source;
- cache path and local usage summary;
- selected local skills and their provenance;
- installed/available Vharness plugins;
- warnings relevant to the active workflow.

Never display API keys, authorization headers, cookies, tokens, or unredacted
evidence fields.

## Safety boundaries

The first TUI release excludes:

- arbitrary shell execution or terminal emulation;
- raw HTTP request composition, target proxying, browser automation, or file
  upload;
- a chat box that can propose or issue assessment actions;
- target-specific BlackVault behavior;
- approval of state-changing actions;
- changing session state other than launching a supported workflow, cleanly
  cancelling a TUI-owned active run, and exporting existing records.

Safe-method assessment views must repeat the core warning that GET/HEAD
restrictions do not guarantee a target handler is read-only.

## Data and compatibility contract

- Existing CLI JSONL logs remain readable and are never rewritten by the TUI.
- Dynamic session display consumes versioned core events in sequence order; it
  does not reconstruct session state from timestamps or presentation logs.
- The TUI uses a narrow adapter around public core APIs and documented event
  schemas. It does not bind directly to unstable internal database tables.
- Summaries and counters are derived from the same source of truth as the CLI;
  discrepancies are presented as a diagnostic error, not silently reconciled.

## Test plan

- Unit-test view models and state adapters without a live terminal.
- Test form validation, CLI-equivalent operation construction, and refusal of
  arbitrary command strings.
- Test run reopening, missing/malformed logs, schema-version incompatibility,
  and report-path errors.
- Test live progress, cancellation of a TUI-owned subprocess, and preservation
  of unrelated processes.
- Test filtering, bounded evidence rendering, redaction, and safe display of
  target/model text as untrusted text.
- For dynamic sessions, assert event ordering and counters match committed core
  SQLite/JSONL state exactly.
- Run a small Textual integration/snapshot suite for keyboard navigation,
  focus, screen-reader labels, narrow terminals, and resize behavior.

## Implementation order

1. Complete the Workspace v0 prerequisite and use its project/run service.
2. Establish the shared operation/service boundary needed by both CLI and TUI.
3. Add optional dependency, explicit `vharness tui` entry point, and a minimal
   Runs screen that opens existing static run logs.
4. Add static finding Details and Configuration/status views.
5. Add structured scan/eval Launch and live-run/cancel handling.
6. After the dynamic safe-method milestone is complete, add assessment Launch
   and dynamic event/evidence Details.
7. Validate the TUI against the external BlackVault safe-method acceptance
   session without adding BlackVault logic to the product.

## Completion criteria

The initial TUI is complete when an operator can launch or reopen supported
local workflows, understand progress and results, safely inspect bounded data,
cancel only a run it owns, and see the same state and counters as the CLI and
authoritative run/session records.
