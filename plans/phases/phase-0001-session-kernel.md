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

A deterministic scripted agent can create a session, ingest environment,
knowledge, and evaluation contracts, start an attempt from a seeded committed
state, perform multiple proposed actions, receive external receipts, and commit
a successor only after external acceptance. Failed attempts remain replayable
without entering the committed lineage. The session can checkpoint, restart,
reconcile pending work, and reproduce the same state. Vharness executes no action.

## Entrance criteria

ARCH-0001, ROAD-0001, BENCH-0001, and ADR-0001 through ADR-0004 are accepted.
The current test suite passes before implementation begins. WORK-0001 records
the baseline revision and commands.

## In scope

- Versioned Python records for task, environment, knowledge sources, state
  references, attempts, committed nodes, events, proposals, execution receipts,
  evaluation receipts, operator commands, and checkpoints.
- SQLite journal with atomic sequence assignment, replay, integrity checks, and
  content-addressed artifact references.
- Session state machine and a single-writer coordinator.
- Durable message, steer, pause, resume, stop, checkpoint, and evaluation-request
  operator events, with a minimal programmatic/CLI observation surface.
- External runtime/evaluator protocols plus deterministic fakes for tests.
- A minimal single-active-lineage projection separating all attempts from only
  externally accepted committed states.
- Pending-proposal recovery with reconciliation and `indeterminate` handling.
- Counters and run manifest fields required by BENCH-0001.

## Out of scope

Model-driven planning, semantic retrieval, supervisor calls, population/archive
branching, real benchmark adapters, distributed coordination, UI redesign,
historical run migration, and any Vharness-side authorization, credentials,
execution policy, target lifecycle, audit enforcement, or grading.

## Contracts added or changed

Implement the ARCH-0001 public contracts without adding speculative fields.
Provide one `Environment` protocol for task/observation/action-space and opaque
state-reference exchange, one `Runtime` protocol for submit/reconcile/receipt
exchange, and one `Evaluator` protocol for evaluation requests/receipts. The
environment declares whether state references are restorable or trajectory-only.
The evaluator supplies validity, objective vector, baseline comparison, and
acceptance; Vharness records rather than recomputes that judgment. Production
execution and evaluation remain external; only deterministic fakes belong here.

## Implementation sequence

1. Capture current tests and map existing reusable model/usage primitives.
2. Implement records and strict validation at external deserialization edges.
3. Implement journal append, artifact storage, replay, and projection versioning.
4. Implement attempt and single-lineage projections with a seeded root state.
5. Implement the coordinator state machine and operator command application.
6. Add proposal dispatch and receipt correlation against deterministic fakes.
7. Add external evaluation handling and accepted-successor commits.
8. Add checkpoint/restart and pending-proposal reconciliation.
9. Expose a thin CLI command or internal demo that exercises the full slice.

## Compatibility and migration

Add the kernel beside existing runner behavior; do not change the default CLI
path. Reuse package logging/configuration only where it does not weaken the new
contracts. Use a new database namespace and fail clearly on unknown versions.

## Test strategy

Unit-test contract validation and state transitions. Use temporary SQLite files
for journal/replay checks. One table-driven end-to-end test covers create, run,
pause, steer, resume, a multi-action attempt, evaluation, accepted commit,
checkpoint, restart, and completion. Separate cases prove invalid, regressed, and
incomparable evaluations remain in attempt history without advancing lineage.
Inject crashes before submit, after submit/before receipt, after evaluation, and
before commit projection; assert no blind duplicate submission or commit and
identical replay.
Property-style loops may use seeded standard-library randomness; add no testing
dependency unless it finds failures the table tests cannot cover.

## Exit criteria and required evidence

- All current and new tests pass and `git diff --check` is clean.
- Journal replay is byte-stable for canonical event payloads and yields the same
  projection hashes across repeated runs.
- Duplicate event and receipt ingestion is idempotent by stable ID.
- Each crash point resumes correctly; indeterminate work is never resent.
- Operator commands survive restart and affect the next coordinator decision.
- A variation attempt may contain multiple actions and evaluations in any order.
- Only an externally accepted evaluation creates one single-parent committed node;
  failed and non-improving attempts remain queryable outside that lineage.
- Candidate-capable and trajectory-only fake environments both preserve correct
  state semantics without Vharness rollback or lifecycle control.
- No implementation path executes environment effects or evaluates success.
- WORK-0001 links commands, fixtures, and test output; then status becomes
  `implemented`. Independent verification is required for `verified`.

## Risks and recovery

The main risk is encoding too much future behavior in foundational records.
Prefer opaque extension metadata and add fields only when the vertical slice
needs them. If existing code forces incompatible assumptions, wrap the smallest
reusable boundary rather than refactoring the current product during this phase.
