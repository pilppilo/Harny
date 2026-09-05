---
id: PHASE-0003
title: Add progress supervision and recovery
type: phase
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [PHASE-0002]
supersedes: []
related: [ARCH-0001, BENCH-0001, WORK-0001]
---

# Add progress supervision and recovery

## Observable outcome

Vharness detects seeded non-progress from journal and committed-lineage evidence,
requests bounded advisory supervision, performs a discriminating replan or new
variation attempt, and records whether the intervention improved the external
result. Attempt history and committed lineage survive failure and remain
attributable.

## Entrance criteria

PHASE-0002 is verified with deterministic context manifests and bounded
end-to-end evidence. Real failure traces supplement seeded fixtures. Before this
phase becomes `ready`, its linked EXP must select an initial supervisor policy;
ARCH-0001 intentionally supplies no numerical trigger defaults.

## In scope

- Rolling progress signals and normalized action/failure fingerprints.
- Stagnation thresholds, hysteresis, cooldown, and trigger evidence.
- Advisory supervisor requests and typed `Guidance` results without tools.
- Main-agent accept/reject/replan handling with recorded concise reasons.
- Escalation from guidance to checkpoint/replan to operator question.
- Supervisor access to a bounded digest of attempts, committed objective vectors,
  failures, and still-unexplored directions.
- Lineage-informed variation direction and external comparison using the
  PHASE-0001 single-lineage contracts.
- Recovery drills spanning model, supervisor, runtime, evaluator, and process
  failures.

## Out of scope

Supervisor tool use, recursive agent spawning, population/archive management,
branching or broad search-tree algorithms, learned threshold models, silent
autonomous rollback of external state, or domain-specific recovery policies.

## Contracts added or changed

Implement `Guidance` and the monitor projection over `ProgressClaim` and
`RecoveryEvent` from ARCH-0001. Reuse `Attempt` and `CommittedNode` without
changing their external acceptance semantics. Add monitor and supervisor policy
versions to run manifests. External receipts and scores remain the evidence;
Vharness does not replace evaluation. Derive monitor inputs from supported
outcome/knowledge claims while keeping recovery, pending claims, and raw activity
separate.

## Implementation sequence

1. Derive progress signals from existing event/lineage fixtures and expose
   diagnostics, distinguishing repeated cycles from productive plateaus.
2. Create an EXP document to select initial trigger windows, thresholds,
   normalization, hysteresis, and cooldown from labeled traces.
3. Implement the selected policy and deterministic fakes.
4. Add bounded supervisor context and typed guidance with no execution access.
5. Connect main-agent response, new-attempt creation, and operator escalation.
6. Run seeded loop, plateau, regression, crash, and recovery scenarios.
7. Use later EXP documents for material algorithm changes justified by observed
   false positives, false negatives, or benchmark cost.

## Compatibility and migration

Sessions without supervision events replay normally. Supervision is enabled by
one kernel capability flag during this phase for paired measurement; the flag is
global to a run and never selected by benchmark identity.

## Test strategy

Label seeded productive, plateaued-but-exploring, stalled, repetitive, and
regressing traces. Assert trigger timing, cooldown, escalation, no trigger on
clear progress, and bounded intervention on productive plateaus. Compare
supervised and unsupervised paired runs by task/seed. Inject failure at every
guidance, attempt, and commit transition and assert replay equivalence and no
duplicate external effect.

## Exit criteria and required evidence

- All labeled stalls trigger within the expected window and productive fixtures
  do not thrash the supervisor.
- Guidance has no execution capability and all use is causally recorded.
- At least one paired trial demonstrates recovery with bounded extra cost; any
  regressions and rejected guidance remain visible.
- Across the predeclared paired sample, report supervisor benefit, harm, and
  uncertainty against fixed tolerances; one recovery remains functional evidence,
  not a general benefit claim.
- Attempt history, committed parentage, changes, evaluations, and dispositions
  replay without failed attempts entering committed lineage.
- Repeated failed recovery escalates to the operator rather than looping forever.
- BENCH-0001 evidence is linked from WORK-0001.

## Risks and recovery

An overeager supervisor can become a second noisy planner. Keep deterministic
triggers and cooldown authoritative, supervisor output advisory, and disable the
capability globally if paired evidence shows net harm while retaining traces for
a focused experiment.
