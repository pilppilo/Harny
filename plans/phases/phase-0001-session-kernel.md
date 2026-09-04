---
id: PHASE-0001
title: Establish the durable session kernel and external contracts
type: phase
status: ready
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ARCH-0001, ROAD-0001, BENCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004]
supersedes: []
related: [WORK-0001]
---

# Establish the durable session kernel and external contracts

## Observable outcome

A deterministic scripted agent can create a session, ingest an environment
contract and operator commands, emit one typed action proposal, receive an
external receipt, checkpoint, restart, reconcile pending work, and reproduce
the same projected state from its journal. Vharness itself executes no action.

## Entrance criteria

ARCH-0001, ROAD-0001, BENCH-0001, and ADR-0001 through ADR-0004 are accepted.
The current test suite passes before implementation begins. WORK-0001 records
the baseline revision and commands.

## In scope

- Versioned Python records for task, environment, events, proposals, execution
  receipts, evaluation receipts, operator commands, and checkpoints.
- SQLite journal with atomic sequence assignment, replay, integrity checks, and
  content-addressed artifact references.
- Session state machine and a single-writer coordinator.
- Durable message, steer, pause, resume, stop, checkpoint, and evaluation-request
  operator events, with a minimal programmatic/CLI observation surface.
- External runtime/evaluator protocols plus deterministic fakes for tests.
- Pending-proposal recovery with reconciliation and `indeterminate` handling.
- Counters and run manifest fields required by BENCH-0001.

## Out of scope

Model-driven planning, semantic retrieval, supervisor calls, candidate variation,
real benchmark adapters, distributed coordination, UI redesign, historical run
migration, and any Vharness-side authorization, credentials, execution policy,
target lifecycle, audit enforcement, or grading.

## Contracts added or changed

Implement the ARCH-0001 public contracts without adding speculative fields.
Provide one `Environment` protocol for task/observation/action-space exchange,
one `Runtime` protocol for submit/reconcile/receipt exchange, and one `Evaluator`
protocol for evaluation requests/receipts. The production implementation is
external; only fakes belong in this phase.

## Implementation sequence

1. Capture current tests and map existing reusable model/usage primitives.
2. Implement records and strict validation at external deserialization edges.
3. Implement journal append, artifact storage, replay, and projection versioning.
4. Implement the coordinator state machine and operator command application.
5. Add proposal dispatch and receipt correlation against deterministic fakes.
6. Add checkpoint/restart and pending-proposal reconciliation.
7. Expose a thin CLI command or internal demo that exercises the full slice.

## Compatibility and migration

Add the kernel beside existing runner behavior; do not change the default CLI
path. Reuse package logging/configuration only where it does not weaken the new
contracts. Use a new database namespace and fail clearly on unknown versions.

## Test strategy

Unit-test contract validation and state transitions. Use temporary SQLite files
for journal/replay checks. One table-driven end-to-end test covers create, run,
pause, steer, resume, proposal, receipt, checkpoint, restart, and completion.
Inject crashes before submit, after submit/before receipt, and after receipt/
before projection; assert no blind duplicate submission and identical replay.
Property-style loops may use seeded standard-library randomness; add no testing
dependency unless it finds failures the table tests cannot cover.

## Exit criteria and required evidence

- All current and new tests pass and `git diff --check` is clean.
- Journal replay is byte-stable for canonical event payloads and yields the same
  projection hashes across repeated runs.
- Duplicate event and receipt ingestion is idempotent by stable ID.
- Each crash point resumes correctly; indeterminate work is never resent.
- Operator commands survive restart and affect the next coordinator decision.
- No implementation path executes environment effects or evaluates success.
- WORK-0001 links commands, fixtures, and test output; then status becomes
  `implemented`. Independent verification is required for `verified`.

## Risks and recovery

The main risk is encoding too much future behavior in foundational records.
Prefer opaque extension metadata and add fields only when the vertical slice
needs them. If existing code forces incompatible assumptions, wrap the smallest
reusable boundary rather than refactoring the current product during this phase.

