---
id: PHASE-0003
title: Add progress supervision recovery and lineage
type: phase
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [PHASE-0002]
supersedes: []
related: [ARCH-0001, BENCH-0001, WORK-0001]
---

# Add progress supervision recovery and lineage

## Observable outcome

Vharness detects seeded non-progress from journal evidence, requests bounded
advisory supervision, performs a discriminating replan/variation, and records
whether the intervention improved the external result. Candidate and trajectory
history survive failure and remain attributable.

## Entrance criteria

PHASE-0002 is verified with deterministic context manifests and bounded
end-to-end evidence. Real failure traces are available to supplement seeded
fixtures; otherwise the phase limits itself to the ARCH-0001 defaults.

## In scope

- Rolling progress signals and normalized action/failure fingerprints.
- Stagnation thresholds, hysteresis, cooldown, and trigger evidence.
- Advisory supervisor requests and typed `Guidance` results without tools.
- Main-agent accept/reject/replan handling with recorded concise reasons.
- Escalation from guidance to checkpoint/replan to operator question.
- Optional candidate and trajectory lineage with parentage and external evidence.
- Recovery drills spanning model, supervisor, runtime, evaluator, and process
  failures.

## Out of scope

Supervisor tool use, recursive agent spawning, broad search-tree algorithms,
learned threshold models, silent autonomous rollback of external state, or
domain-specific recovery policies.

## Contracts added or changed

Implement `Guidance`, `ProgressSignal`, and `LineageNode` from ARCH-0001. Add
monitor and supervisor versions to run manifests. External receipts and scores
remain the evidence; lineage disposition is a Vharness planning decision, not a
replacement evaluation.

## Implementation sequence

1. Derive progress signals from existing event fixtures and expose diagnostics.
2. Implement default triggers, hysteresis, cooldown, and deterministic fakes.
3. Add bounded supervisor context and typed guidance with no execution access.
4. Connect main-agent response and operator-visible escalation.
5. Add minimal lineage projection and one-change-at-a-time variation records.
6. Run seeded loop, regression, crash, and recovery scenarios.
7. Create EXP documents only for threshold or algorithm changes justified by
   observed false positives, false negatives, or benchmark cost.

## Compatibility and migration

Sessions without supervision events replay normally. Supervision is enabled by
one kernel capability flag during this phase for paired measurement; the flag is
global to a run and never selected by benchmark identity.

## Test strategy

Label seeded productive, stalled, repetitive, and regressing traces. Assert
trigger timing, cooldown, escalation, and no trigger on clear progress. Compare
supervised and unsupervised paired runs by task/seed. Inject failure at every
guidance and lineage transition and assert replay equivalence and no duplicate
external effect.

## Exit criteria and required evidence

- All labeled stalls trigger within the expected window and productive fixtures
  do not thrash the supervisor.
- Guidance has no execution capability and all use is causally recorded.
- At least one paired trial demonstrates recovery with bounded extra cost; any
  regressions and rejected guidance remain visible.
- Candidate/trajectory parentage, changes, evaluations, and disposition replay.
- Repeated failed recovery escalates to the operator rather than looping forever.
- BENCH-0001 evidence is linked from WORK-0001.

## Risks and recovery

An overeager supervisor can become a second noisy planner. Keep deterministic
triggers and cooldown authoritative, supervisor output advisory, and disable the
capability globally if paired evidence shows net harm while retaining traces for
a focused experiment.

