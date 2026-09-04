---
id: BENCH-0001
title: Cross-domain general agent capability and efficiency
type: benchmark
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ARCH-0001, ADR-0001, ADR-0002, ADR-0003, ADR-0004]
supersedes: []
related: [ROAD-0001, PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# Cross-domain general agent capability and efficiency

## Product behavior under evaluation

This contract measures whether one Vharness agent kernel can sustain progress,
recover, use feedback, and collaborate with an operator across distinct external
environments. It evaluates product capability, efficiency, quality, and
reliability; it does not define authorization or recreate external scoring.

The generality claim requires the same built artifact, agent prompt policy,
memory/context algorithms, supervisor logic, and default thresholds. Only the
environment contract, task input, action schema, model endpoint credentials,
and run budgets may vary. Any other variance is reported and invalidates a
strict cross-domain comparison.

## External environment and scoring authority

| Family | External authority | Vharness boundary |
| --- | --- | --- |
| Gymnasium | Pinned Gymnasium environment implementation and its returned reward/termination signals | Consume reset/step observations and expose action schema; do not rescore |
| ARC-AGI-3 | Official ARC interface, toolkit, and scorecard | Submit allowed actions and retain official results; do not imitate the grader |
| Hack The Box | Operator-selected authorized lab and HTB validation | Interact through the external runtime; do not spawn/reset targets or validate flags |
| Software tasks | Pinned task repository and its external test/evaluation command | Propose changes and consume test/evaluator receipts; do not invent a second pass criterion |

HTB authorization, VPN/session access, machine lifecycle, reset, and flag
submission remain external. Rotated flags and reset state are observations tied
to the external instance identity, never durable cross-instance knowledge.

## Inputs and visible observations

Every run records the exact `TaskSpec`, environment/version identity, initial
observation, action-space schema, model identity, Vharness revision, configuration
digest, budgets, and operator interventions. The agent receives only observations
available through the environment contract and explicit operator messages.

Gymnasium uses the official `reset` and `step` outputs, including reward,
`terminated`, `truncated`, and `info`. ARC uses the exact grid/state and legal
actions surfaced by the official interface. HTB and software tasks use external
tool outputs and receipts without hidden access to validators or solutions.

## Available and counted actions

An environment publishes its `ActionSpace`; the kernel is unchanged. Count at
minimum:

- external effectful actions and read-only observations separately;
- environment-native actions for Gymnasium and ARC;
- model and supervisor calls, input/output tokens, retries, and invalid outputs;
- operator messages and controls, classified as requested, corrective, or abort;
- evaluations, checkpoints, resumes, recovery reconciliations, and unresolved
  indeterminate proposals;
- variation directions, attempts, externally accepted commits, and unsuccessful
  closures, with each evaluation correlated to its attempt and baseline.

Environment-native efficiency measures remain authoritative. Vharness counters
are diagnostic and must reconcile to retained external receipts.

## Versions, seeds, and datasets

Each benchmark run manifest pins package/toolkit version, environment/task ID,
dataset split or machine identity, seed when supported, model identifier, agent
configuration digest, and external evaluator version. Secrets and credentials
are referenced, never copied into the manifest.

PHASE-0002 starts with small deterministic fixtures and at least one discrete
and one continuous/control Gymnasium environment. PHASE-0004 selects the full
publicly available ARC-AGI-3 set/toolkit, a representative Gymnasium suite,
operator-selected HTB labs, and a pinned software-task suite. The exact set is
frozen in the run manifest rather than prematurely fixed in this architecture.

## Contamination and memory boundaries

Use a fresh session and empty private memory for each scored task unless the
external benchmark explicitly evaluates adaptation across episodes. Development
and scored splits use separate workspaces. Do not import solution traces, flags,
grader internals, or prior task-specific memories into scored sessions.

When a benchmark intentionally permits accumulated memory, report the imported
item IDs and provenance and compare against a fresh-memory condition. Operator
interventions are always retained and reported, never hidden as autonomous work.

## Completion and quality measurements

Report external completion and native metrics without reinterpretation, plus:

- completed tasks/runs and completion rate;
- best and final external score where the authority supplies both;
- externally supplied hard-constraint results and objective vectors for every
  evaluated attempt, preserving incomparable results rather than scalarizing them;
- evidence or artifact references for terminal results;
- regression from a previously best externally evaluated state or trajectory;
- attempted versus committed versions and the committed single-lineage sequence;
- autonomous, human-assisted, and operator-aborted outcomes separately;
- recovery correctness after injected process interruption.

ARC reporting includes official completion and action-efficiency/RHAE outputs
when supplied. Gymnasium reports native return and episode length. HTB reports
only platform-validated outcomes returned by the external workflow. Software
tasks report their external test/evaluator result.

## Efficiency, cost, and reliability measurements

For every run record wall time; model latency and tokens; external actions;
supervisor calls; context selection time and utilization; bytes/artifacts read;
journal size; retry counts; repeated-action/failure signals; attempted directions;
attempts; evaluations; accepted commits; time, actions, evaluations, and tokens
between commits; correctness rejection rate; and human interventions. Report
progress per external action, per model call, per million tokens, and per
wall-clock hour where meaningful.

Report the attempt-to-commit ratio and distribution rather than treating every
failed attempt as wasted work. AVO's published trajectory retained 40 committed
versions from more than 500 explored directions; unsuccessful work is necessary
search evidence even though it is excluded from committed lineage.

Reliability includes malformed model result rate, uncorrelated receipt count,
resume success, duplicate-effect count, projection replay agreement, supervisor
trigger precision on labeled injected stalls, and time/actions lost to recovery.
A duplicate external effect after recovery is a release-blocking defect.

## Repetition and statistical reporting

Use at least five seeds or repetitions for stochastic short tasks and report
median, interquartile range, range, and completion count. Expensive long tasks
may use fewer repetitions only when cost and confidence limits are disclosed.
Pair baseline and candidate runs by task and seed. Do not average unlike native
scores into a single synthetic capability number.

The cross-domain generality gate is satisfied only when the candidate improves
a named architectural metric or domain result without a material regression in
completion, cost, or reliability on the other available families. Release
judgment uses the external results and raw evidence; Vharness does not implement
an internal meta-grader.

## Required evidence

Retain run manifests, canonical Vharness event journals, context manifests,
external execution/evaluation receipts, stdout/stderr or artifact references,
aggregate calculation scripts, and the exact Git revision/configuration digest.
Secrets and provider-hidden reasoning are excluded. Evidence must be sufficient
to replay projections and independently reproduce aggregate tables.

Phase verification uses this progression:

- PHASE-0001: contract, journal, crash, replay, and indeterminate-action tests.
- PHASE-0002: bounded end-to-end tasks and operator steering/resume evidence.
- PHASE-0003: seeded stagnation, supervision, recovery, and lineage comparisons.
- PHASE-0004: pinned external cross-domain runs and paired baseline comparison.

## Invalid comparisons

A comparison is invalid when it changes the agent core or hidden prompt by
environment, uses different model capability without reporting it, leaks prior
task solutions, replaces external scores with local approximations, omits human
help, cannot correlate actions/evaluations/commits to attempts and baselines,
counts a rejected attempt as committed progress, cherry-picks seeds, or silently
changes versions/budgets. Invalid runs remain useful diagnostics but cannot
support a product capability claim.
