---
id: PHASE-0002
title: Add the general agent loop memory and operator interaction
type: phase
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [PHASE-0001]
supersedes: []
related: [ARCH-0001, BENCH-0001, WORK-0001]
---

# Add the general agent loop memory and operator interaction

## Observable outcome

A model-driven Vharness session completes bounded tasks through a fake or simple
external environment. Within each attempt, the agent autonomously chooses when
to inspect committed lineage, consult supplied knowledge, act, debug, and request
external evaluation. It maintains evidence-backed memory, constructs reproducible
bounded context, and accepts live operator steering without losing causal state.
The same kernel runs a software fixture and representative Gymnasium fixtures.

## Entrance criteria

PHASE-0001 is verified. Its replay, crash, and external-boundary evidence is
linked from WORK-0001. BENCH-0001 run-manifest fields are available.

## In scope

- Typed model result handling for action, lineage/knowledge query, memory,
  evaluation, question, wait, and completion proposals through the existing
  model provider boundary.
- Working, episodic, and knowledge projections with evidence/provenance links.
- Durable visible model inputs/outputs, context manifests, usage, and latency;
  provider-hidden reasoning is neither requested nor required.
- Agent-directed access to committed states, their objective vectors, supplied
  knowledge sources, and prior attempt evidence in addition to automatic context.
- A single-lineage autonomous variation loop supporting multiple actions and
  evaluations before externally accepted commit or unsuccessful closure.
- Lightweight, overlapping `Investigation` groups that may begin without a
  hypothesis or candidate and may pause, conclude, abandon, or reopen by event.
- Evidence-backed `ProgressClaim` records separating outcome progress from
  knowledge progress, with recovery retained as operational health only.
- Selective failed-artifact retention under a byte budget while protecting
  accepted states, pending effects, and evidence required by active claims.
- Deterministic context bands, ranking, de-duplication, and context manifests.
- Token/action/time budgets enforced as coordinator scheduling limits.
- A live operator surface showing objective, plan, action/receipt stream, current
  evidence, budgets, questions, and acknowledged steering.
- Mechanical adapters for deterministic software and Gymnasium fixtures.
- Context/retrieval and end-to-end metrics from BENCH-0001.

## Out of scope

Supervisor model calls, automated stagnation response, population/archive
branching, full benchmark campaigns, benchmark-specific prompts, multi-session
shared memory, and replacing the current default CLI.

## Contracts added or changed

Add the typed `AgentResult` union, including explicit lineage and knowledge
queries, plus projection/context manifest versions. Do not change external action,
state-reference, evaluation, or receipt semantics from PHASE-0001. Gymnasium is
an environment adapter around official reset/step values, not an agent profile.
Add `Investigation`, `ProgressClaim`, `RecoveryEvent`, and `AlternativeRetention`
as projections over the journal rather than independent workflow engines.

## Implementation sequence

1. Connect typed model results to the coordinator using a scripted model first.
2. Implement working/knowledge projections and explicit hypothesis transitions.
3. Add agent-directed lineage/knowledge lookup with provenance-preserving results.
4. Add investigation grouping and distinct outcome/knowledge/recovery projections.
5. Implement FTS5 ranking, deterministic selection, and context manifests.
6. Add episodic compaction and selective retention with protected evidence roots.
7. Connect a real model adapter and repair malformed outputs within a budget.
8. Exercise free ordering of inspect, act, debug, and evaluate within attempts.
9. Expose the live operator view and durable conversation/control path.
10. Run the same kernel against software and Gymnasium fixtures.

## Compatibility and migration

Keep existing generator providers usable by adapting their request/usage path,
not their old pipeline semantics. New CLI entry points remain opt-in. Sessions
created under PHASE-0001 replay without reinterpretation; new projection versions
rebuild from their events.

## Test strategy

Golden journal fixtures assert identical context manifests for fixed budgets.
Tests cover mandatory-item overflow, contradictory evidence, summary provenance,
stale model cursors, malformed results, budget exhaustion, and steering while an
action is pending. They also prove that the coordinator does not impose a fixed
plan/implement/evaluate/debug sequence and that explicit lineage/knowledge
queries return source-linked results. End-to-end seeded runs compare fresh
process and resumed outcomes. Benchmark evidence follows BENCH-0001 without a
local duplicate grader.
Additional cases cover investigation overlap without double-counting shared
usage, abandonment/reopening, unsupported or duplicate progress claims, recovery
that cannot reset stagnation, and optional artifact eviction without deleting
protected/shared evidence or its retained lesson.

## Exit criteria and required evidence

- The software and Gymnasium fixtures complete with one unchanged kernel policy.
- The model, not a fixed workflow, chooses when and how often to inspect, act,
  debug, and request evaluation within an attempt.
- External acceptance alone advances the committed lineage; rejected attempts
  remain available for later agent-directed inspection.
- Fixed journals produce deterministic contexts within budget.
- Every stored fact/hypothesis and summary resolves to source events.
- Every model decision resolves to its visible input, output, context manifest,
  usage, and causally preceding event cursor.
- Outcome and knowledge progress identify before/after conditions and evidence;
  pending claims, raw activity, and recovery never count as supported progress.
- Failed-work lessons survive replay even when an optional large artifact expires;
  accepted and required-evidence artifacts remain protected.
- Operator messages are visible, durable, acknowledged, and affect later context.
- Paused sessions make no new model calls or proposal submissions.
- Resume tests show no lost direction, duplicated effect, or projection drift.
- BENCH-0001 metrics and run artifacts are linked from WORK-0001.

## Risks and recovery

Retrieval can look plausible while omitting decisive evidence. Inspect context
manifests and add a focused EXP document before adding embeddings or learned
ranking. If model schemas are unreliable, improve one repair boundary rather
than adding provider-specific reasoning paths.
