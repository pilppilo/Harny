# Bugfix Specification: Complete Phase 1 Session Kernel

**Date:** 2026-09-05
**Slug:** `phase-1-completion`
**Status:** Follow-up required
**Governing scope:** PHASE-0001, ARCH-0001, ROAD-0001, and BENCH-0001

## Objective

Finish the remaining PHASE-0001 durability, recovery, accounting, history, and
evidence work before beginning PHASE-0002. This file is an implementation
handoff, not a change to plan status or architecture.

Vharness continues to propose actions while external runtimes execute them and
external evaluators judge results. Do not add Vharness-side authorization,
target lifecycle, execution-policy, audit-enforcement, or duplicate grading
systems.

## Reviewed implementation baseline

The Phase 1 library already provides:

- frozen domain records, canonical JSON encoding, strict primitive decoding,
  and immutable nested JSON values;
- a SQLite event journal and content-addressed artifact store;
- durable session creation, attempts, action intent, runtime receipts,
  evaluation, lineage promotion, checkpoints, controls, and restart;
- event-derived projection replay without authoritative embedded snapshots;
- replay validation for event ordering, objective changes, legal transitions,
  action ownership, evaluation correlation, promotion, and checkpoint prefix
  integrity;
- a typed, irreversible evaluation-operation lifecycle covering intent, raw
  intake, verification failure, and receipt consumption;
- late/stale evaluation isolation, terminal settlement deduplication, reopen
  equivalence, and checkpoint coverage for evaluation lifecycle state; and
- focused regression coverage for the implemented session behavior.

At the final read-only review of this baseline, 179 repository tests and 49
agent tests passed. Black and Pylint passed on the changed production modules,
Pylint reported 10.00/10, and `git diff --check` passed. Tests were neither
formatted nor linted.

This evidence covers the implemented fragment only. It does not satisfy all
PHASE-0001 exit criteria.

## Remaining work

Complete one numbered fragment at a time. Keep each fragment bounded, add its
failure and recovery tests, and review it before proceeding.

### 1. Make command application atomic

- Add a journal batch append that assigns contiguous sequences and updates the
  session cursor in one SQLite transaction.
- Refactor command transitions so a state-changing command event and its
  applied or rejected disposition are committed atomically.
- Rebuild command completion from disposition events only; remove inference
  that any command-related state event is an acknowledgement.
- Preserve control priority for pause, steer, and stop.
- Inject crashes after admission, during transition preparation, and before
  acknowledgement. Reopen must apply each admitted command at most once.

### 2. Unify durable external operations and recovery

- Replace the action-operation tuple and evaluation-specific coordinator
  indexes with one typed durable operation record where their mechanics are
  genuinely shared.
- Retain operation kind, identity, attempt and objective ownership, reservation,
  dispatch observation, receipt lifecycle, terminal state, and reconciliation
  capability.
- Rebuild every pending operation on reopen.
- Add an evaluator-specific reconciliation boundary. Never pass evaluation
  request IDs to `Runtime.reconcile()`.
- Preserve unsupported or unknown completion as explicit indeterminate state;
  never blindly resubmit an operation.

### 3. Enforce operation identity and monotonic receipt progression

- Reject reused attempt, proposal, operation, request, receipt, reservation,
  and measurement IDs when their required uniqueness scope is violated.
- Bind each receipt to the immutable operation and originating attempt facts.
- Define legal monotonic receipt transitions so late `accepted` or `running`
  observations cannot downgrade terminal state.
- Retain contradictory terminal evidence explicitly instead of silently
  replacing or discarding it.
- Enforce expected state revision semantics when the environment declares
  revision support.

### 4. Replace the resource ledger

- Separate reserved exposure from measured consumption.
- Key settlement by operation ID and measurement ID rather than a proposal-level
  boolean.
- Track action, evaluation, model-call, token, duration, and monetary measures
  required by PHASE-0001 and BENCH-0001.
- Apply measured usage in full even when it exceeds the reservation.
- Accept late measurements, deduplicate exact measurements, and define how
  corrected or additional measurements are represented.
- Preserve unknown exposure as unknown and reconcile every terminal path.

### 5. Complete evaluation, evidence, and promotion semantics

- Add the remaining evaluation-contract and receipt facts: validity, hard
  constraints, completion evidence, required evidence rules, usage, and raw
  receipt reference.
- Verify required artifacts before any dependent promotion event.
- Persist evaluation receipt, disposition, usage settlement, and accepted
  promotion with crash-safe boundaries.
- Keep rejected, stale, and incomparable results queryable without advancing
  lineage.
- Derive finite completion only from applicable external completion evidence;
  promotion by itself is not completion.

### 6. Persist attempts and lineage as queryable history

- Store every attempt with its event range, objective version, base lineage
  node, result state, evaluation references, and final disposition.
- Durably record abandonment on steering and closure after rejection,
  incomparability, or acceptance.
- Preserve unsuccessful attempts outside the accepted single-parent lineage.
- Expose query APIs for all attempts and for accepted lineage independently.

### 7. Finish Phase 1 public contracts and strict envelopes

- Add the remaining in-scope versioned records, including observations,
  knowledge sources, evaluation contracts/results, operation records, run
  manifests, and counters.
- Complete required envelope identity, objective, causation, correlation,
  timestamp, provenance, and schema-version fields.
- Validate unknown versions clearly and deliberately retain compatible unknown
  fields and raw inbound records.
- Keep deserialization and compatibility logic outside `session.py`.

### 8. Complete the Phase 1 evidence surface

- Add the BENCH-0001 run manifest and required counters.
- Add deterministic candidate-restorable and trajectory-only fake
  environments and prove their distinct state semantics.
- Add the thin opt-in demo or CLI only after the library path is covered. Keep
  the existing default CLI behavior unchanged.

### 9. Close the recovery and integration matrix

- Cover every required crash/reopen point for commands, actions, evaluations,
  promotion, settlement, artifacts, and checkpoints.
- Cover stale applicability, out-of-order and contradictory receipts, budget
  exhaustion, unknown cost, unsupported connector guarantees, interrupted
  evaluation, checkpoint-plus-suffix replay, and artifact publication failure.
- Add one table-driven end-to-end scripted session covering controls,
  multi-action attempts, evaluation, accepted commit, checkpoint, restart, and
  finite completion.
- Verify Python 3.10 when available and record any unavailable validation.
- Record final commands, fixtures, revision, and evidence in WORK-0001 before
  requesting PHASE-0001 status changes.

## Completion gate

PHASE-0001 is ready for independent verification only when:

- all nine remaining fragments above are complete;
- all PHASE-0001 exit criteria have linked evidence;
- focused and full pytest suites pass;
- Black and Pylint pass on production code only;
- tests are not sent through formatters or linters;
- `git diff --check` passes;
- crash recovery never creates a duplicate external effect;
- replay and reopen yield the same complete projection; and
- no default CLI path or external-authority boundary has changed.

Do not edit plan status from this bug-fix handoff. Plan and workstream updates
require an explicit, separately reviewed completion change.
