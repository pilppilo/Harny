---
id: PHASE-0004
title: Advance the unchanged core through the capability ladder
type: phase
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [PHASE-0003]
supersedes: []
related: [ARCH-0001, BENCH-0001, WORK-0001]
---

# Advance the unchanged core through the capability ladder

## Observable outcome

Pinned external campaigns advance the same Vharness kernel, memory/context
algorithms, supervision, and operator model through the software, Gymnasium,
ARC-AGI-3, and operator-authorized Hack The Box capability rungs. Each achieved
rung meets its predeclared target and retains regression evidence for earlier
rungs. Raw external receipts support every reported result.

## Entrance criteria

PHASE-0003 is verified. BENCH-0001 metrics are emitted automatically. The
operator has selected and independently authorized any HTB labs and configured
the external runtime. Versions, tasks, model/settings, budgets, seeds,
repetitions, targets, comparison tolerances, and assistance labels are frozen in
campaign manifests before scored runs.

## In scope

- Thin mechanical environment integrations needed for the selected suites.
- Contract conformance tests proving adapters do not change kernel policy.
- Paired baseline/current runs, repetitions, failure injection, and cost reports.
- Operator-assisted versus autonomous outcome labeling.
- Per-rung capability conclusions, cross-domain regression analysis, and honest
  milestone recommendations based on external evidence.
- A reversible switch making the new kernel the default only after verification.

## Out of scope

Target provisioning/reset, authorization checks, credential management, VPN
management, flag validation/submission, cloned benchmark graders, benchmark-
specific prompts, model fine-tuning, and deletion of the previous execution path.

## Contracts added or changed

No kernel contract should change. If an external environment cannot be expressed
through ARCH-0001, stop and propose an architecture/decision amendment rather
than smuggling behavior through an adapter. Pin each external protocol/version
in its run manifest.

## Implementation sequence

1. Freeze each rung's suite, versions, settings, budgets, seeds, repetitions,
   baseline, targets, tolerances, assistance labels, and evidence locations.
2. Connect software-task evaluation through its existing external command path.
3. Implement the smallest conforming Gymnasium and ARC integrations.
4. Connect operator-provided HTB observations/actions to the external runtime;
   leave lifecycle and validation with HTB/operator systems.
5. Run smoke tests, then the paired/repeated BENCH-0001 matrix.
6. Analyze completion, efficiency, reliability, recovery, and human intervention.
7. Fix general defects or create explicit experiments; do not tune hidden per-
   environment policy.
8. Verify evidence, publish achieved/remaining rungs, and switch the default entry
   point reversibly after the full phase exit and operator decision.

## Compatibility and migration

The old entry point remains selectable for comparison and rollback. The new
kernel writes only its versioned journal format. Removing old internals or
migrating old state requires a later operator-approved phase after field use.

## Test strategy

Run adapter conformance tests with recorded external fixtures before live use.
Execute the repetition and reporting rules in BENCH-0001. Independently verify
aggregate calculations from raw manifests and receipts. Inject process loss in
at least one task per family and verify recovery behavior without duplicate
effects.

## Exit criteria and required evidence

- All four target environment families meet their predeclared capability targets;
  otherwise the unmet rung and evidence remain explicit and the phase is not
  represented as fully verified.
- Run manifests prove unchanged core/prompt/algorithms across families.
- Efficiency, reliability, recovery, and human-intervention results satisfy
  BENCH-0001 reporting, predeclared tolerances, and regression coverage.
- No adapter contains agent planning, scoring imitation, authorization, target
  lifecycle, or benchmark-specific behavioral prompts.
- Raw evidence and reproducible aggregate calculations receive independent
  review; PHASE-0004 then becomes `verified`.
- The new default is reversible and existing supported behavior still tests.

## Risks and recovery

External services, costs, and environment changes can make runs incomparable.
Invalidate and rerun only affected cells with a new manifest; never merge them
silently. A weak domain result is evidence for a general algorithm experiment,
not permission to add a hidden benchmark profile.
