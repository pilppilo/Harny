---
id: ARCH-0001
title: AVO-inspired long-horizon agent system
type: architecture
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ADR-0001, ADR-0002, ADR-0003, ADR-0004]
supersedes: []
related: [ROAD-0001, BENCH-0001, SCHEM-0001, PHASE-0001, PHASE-0002, PHASE-0003, PHASE-0004]
---

# AVO-inspired long-horizon agent system

## Problem and scope

The current probe/generator/detector/evaluator pipeline is useful for bounded
runs but is not a long-horizon agent architecture. Vharness Next must maintain
coherent state over long work, choose and use externally executed tools,
incorporate evaluation and operator feedback, detect non-progress, recover
after failures, and resume without losing causal history.

This architecture adapts the system lessons of NVIDIA AVO: a persistent main
agent, environment interaction, durable work state, external feedback, and a
supervisory path that helps the main agent escape stagnation. It intentionally
does not claim fidelity to unpublished implementation details.

## Goals

- Sustain useful autonomous work across minutes, hours, and process restarts.
- Keep one agent kernel across assessment, ARC, Gymnasium, and software tasks.
- Make evidence, hypotheses, failures, operator direction, and progress durable.
- Bound model context while preserving the information most likely to matter.
- Detect loops and regressions early enough to redirect rather than burn budget.
- Let a human monitor, converse, steer, pause, resume, and stop at any time.
- Measure capability and efficiency using externally authoritative results.
- Remain simple enough to test deterministically and inspect after failure.

## Non-goals

- Reproducing NVIDIA's private code or guessing unspecified AVO internals.
- Building a multi-agent swarm, distributed scheduler, or workflow language.
- Making Vharness an authorization, identity, credential, isolation, or policy
  enforcement boundary.
- Replacing environment lifecycle, audit, scoring, or validation systems.
- Creating benchmark-specific agent profiles or hidden benchmark strategies.
- Migrating historical runs or deleting the current implementation in the
  initial phases.

## Invariants

1. The append-only event journal is canonical. Every other state view is a
   deterministic, rebuildable projection.
2. Only the external runtime causes tool effects. Vharness emits proposals and
   consumes correlated receipts.
3. Only external evaluators make authoritative completion and scoring claims.
4. The agent kernel is environment-neutral. Adapters translate mechanics only.
5. Current operator direction is durable mandatory context, not an incidental
   chat message.
6. Every proposal, receipt, evaluation, checkpoint, and operator command has a
   stable ID and causal link.
7. Recovery never blindly replays an action whose completion is indeterminate.
8. Model-generated summaries are derived aids and never erase source evidence.
9. A session's memory is isolated by default; sharing requires an explicit,
   provenance-preserving import.
10. Hidden chain-of-thought is neither required nor persisted. Stored reasoning
    is limited to concise decisions, hypotheses, evidence, and action summaries.

## Components and responsibilities

### Session coordinator

Owns the session state machine, serializes state-changing events, applies
operator controls, invokes the kernel, dispatches proposals to the external
runtime connection, and schedules checkpoints. It is the only event writer in
the first implementation; UI and receipt readers submit messages to its queue.

### Agent kernel

Runs the domain-neutral decide/act/observe loop. Given a `TaskSpec`, selected
context, an environment contract, budgets, and current controls, it returns one
typed result: an action proposal, a memory update, an evaluation request, a
question to the operator, a wait, or a completion proposal. It never invokes a
tool directly.

### Context assembler

Builds a deterministic, token-bounded model input from mandatory state and
ranked memory items. It reports included and omitted item IDs so any decision
can be reconstructed and selection quality can be measured.

### Journal and memory projections

The journal stores immutable events. Projections expose working state,
episodes, knowledge, hypotheses, failures, operator direction, budgets, and
candidate/trajectory lineage. Projection code is versioned and replay-tested.

### Environment connection

Presents task observations and a machine-readable `ActionSpace`; carries action
proposals to the separately controlled runtime; returns execution and evaluation
receipts. An adapter may normalize external protocol data but contains no agent
prompt, planning policy, score imitation, or target lifecycle logic.

### Progress monitor and supervisor

The deterministic monitor calculates progress and stagnation signals from the
journal. When a threshold fires, the advisory supervisor receives a bounded
trajectory digest and returns a diagnosis, constraints, and suggested next
experiments. It has no tools and cannot mutate state except by a recorded
guidance event consumed by the main agent.

### Human interaction surface

Streams state, proposals, receipts, evidence, budgets, and supervisor notices.
It converts operator input into typed events and confirms their application.
The first surface may be the existing CLI/TUI; the durable contract, not the
presentation layer, is architectural.

### Candidate and trajectory lineage

Tracks parentage, changes, evidence, and disposition when work has alternatives.
Code and optimization tasks may have explicit artifact candidates; ARC, Gym,
and assessment sessions may instead track trajectory branches and checkpoints.
The agent decides whether branching is useful; it is not imposed on every task.

## Public contracts

Contracts are versioned JSON-compatible records. Python uses frozen dataclasses,
enums, and `typing.Protocol` at process boundaries; canonical JSON is used for
persistence and external transport. Unknown fields are retained on ingest,
required fields are validated, and schema versions are explicit.

| Contract | Required meaning |
| --- | --- |
| `TaskSpec` | `task_id`, objective, success evidence requested, budgets, environment identity, initial observation references |
| `ActionSpace` | Named actions with argument schemas and environment-provided descriptions |
| `Observation` | Source, sequence/cursor, typed content or artifact references, and external timestamp/metadata |
| `ActionProposal` | Proposal ID, session ID, action name, validated arguments, expected observable outcome, concise rationale, and context event cursor |
| `ExecutionReceipt` | Proposal ID, external operation ID if any, status, outputs/artifact references, error, timing, and raw receipt reference |
| `EvaluationReceipt` | External evaluator identity, task/run identity, completion state, metrics, evidence references, and raw receipt reference |
| `OperatorCommand` | Command ID and one of message, steer, pause, resume, stop, checkpoint, or request-evaluation with optional reason |
| `Guidance` | Trigger evidence, supervisor diagnosis, constraints, suggested experiments, and expiry/cooldown |
| `Checkpoint` | Journal cursor, projection versions/hashes, pending proposal IDs, budgets, and active controls |
| `LineageNode` | Node ID, parent IDs, artifact or trajectory reference, change summary, evidence, and active/retained/rejected state |

Execution receipt status is one of `accepted`, `rejected`, `running`,
`succeeded`, `failed`, or `indeterminate`. Acceptance means only that the
external runtime took responsibility; it is not task success. Every inbound
receipt is preserved before any projection or model call uses it.

## State ownership and persistence

Use one SQLite database per workspace with WAL mode, foreign keys, and a unique
`(session_id, sequence)` constraint. The minimum durable tables are `sessions`,
`events`, and `artifacts`; typed projections may be tables or views once their
queries require it. Large/binary payloads live in a content-addressed artifact
directory and are referenced by SHA-256, size, media type, and provenance.

An event contains `event_id`, `session_id`, monotonic sequence, kind, schema
version, recorded time, optional causation/correlation IDs, and canonical JSON
payload. Wall-clock time is descriptive; ordering comes from sequence. An event
and its session cursor update commit in one transaction.

Memory projections are deliberately distinct:

- **Working:** objective, current plan, controls, budgets, pending actions, and
  unresolved questions needed on the next step.
- **Episodic:** compact spans of actions, observations, outcomes, and turning
  points with links to their source event ranges.
- **Knowledge:** evidence-backed facts, hypotheses, contradictions, confidence,
  scope, and provenance. Hypotheses never silently become facts.
- **Lineage:** candidates or trajectory branches, parentage, evaluations, and
  retained/rejected decisions.

No vector database is required initially. SQLite FTS5, structured filters, and
deterministic scoring are sufficient until BENCH-0001 shows a retrieval ceiling.

## Control flow

A session moves through `created`, `running`, `paused`, `stopping`, then one of
`completed`, `failed`, or `stopped`. External evaluation can support completion;
only the coordinator commits the state transition.

For each step, the coordinator:

1. Persists queued receipts and operator commands, then refreshes projections.
2. Applies pause/stop controls before any model call or proposal dispatch.
3. Builds context and journals its manifest of selected event/item IDs.
4. Invokes the model through the existing model boundary for one typed result.
5. Validates shape, action name, arguments, budgets, and stale context cursor.
6. Journals an accepted result; invalid results become observations for repair.
7. Sends an action proposal to the external runtime or applies a cognitive
   update locally as a new event.
8. Persists returned receipts before interpreting them.
9. Updates progress signals, requests supervision if triggered, and checkpoints
   at an external terminal receipt, operator control, or configured event span.

The coordinator permits at most one unresolved state-changing proposal per
session in the initial implementation. This makes crash recovery and causal
ordering obvious; parallel proposals require later benchmark evidence and a
new decision.

## Context and memory algorithms

Context has a hard token budget and three bands:

1. **Mandatory:** task, environment/action contract, latest operator direction,
   active budgets, pending action, current plan, and latest receipt.
2. **Retrieved:** unresolved hypotheses, relevant evidence, prior failures, and
   episodes ranked against the objective, plan step, and latest observation.
3. **Recent:** newest events that fit after mandatory and retrieved content.

Candidate ranking combines FTS/BM25 relevance, explicit salience, unresolved
status, causal proximity, and bounded recency. Greedy maximal-marginal-relevance
selection penalizes near-duplicates. Stable tie-breaking uses event sequence and
ID, so the same journal and budget produce the same manifest. Source excerpts
are preferred to summaries when both fit; every summary links its source span.

A knowledge item changes state only through explicit evidence: `hypothesis` to
`supported`, `contradicted`, or `retired`. Conflicts remain visible together.
A compactor may create new episodic summaries after a checkpoint but cannot
rewrite or delete source events.

## Progress, supervision, and variation

The monitor maintains rolling signals rather than asking a model whether it is
stuck. Positive signals include new external score, newly satisfied evidence,
resolved hypotheses, newly reachable state, and retained candidate improvement.
Negative signals include repeated normalized actions, repeated failure
fingerprints, no positive signal over a step window, evaluation regression, and
budget burn without new observations.

Initial thresholds are intentionally visible defaults: supervision after six
effectful receipts with no positive signal, or three repetitions of an action
or failure fingerprint. A four-step cooldown prevents supervisor loops. Every
trigger records its inputs, so BENCH-0001 can tune thresholds from evidence.

Supervisor guidance must name the observed pattern, identify assumptions to
challenge, and suggest a small discriminating experiment or replan. The main
agent may accept or reject it with a concise recorded reason. Repeated triggers
escalate from guidance to checkpoint/replan, then to an operator question; they
do not silently terminate externally controlled work.

Where candidates apply, a variation step selects one parent, states one intended
change, obtains the change through ordinary external actions, evaluates through
the external evaluator, and retains or rejects from recorded evidence. Keeping
one change attributable at a time is the default; combining parents or changes
requires an explicit reason in the lineage event.

## Failure and recovery behavior

On startup, replay events through the checkpoint cursor, verify projection
hashes, rebuild mismatches, and enumerate pending proposals. Query the external
runtime for each pending proposal ID when reconciliation is available. Persist
the returned receipt before continuing. If completion cannot be determined,
mark the proposal `indeterminate`, expose it to the operator and agent, and do
not resend it automatically.

Model timeout, malformed output, runtime rejection, execution failure, evaluator
unavailability, and supervisor failure are typed events with bounded retry
budgets. Retries must either be safe reads or use the same externally supported
idempotency key. SQLite corruption or artifact hash mismatch stops the session
with diagnostic evidence rather than continuing from uncertain state.

## Performance and scaling assumptions

The first system is one Python process, one coordinator loop per active session,
and one SQLite writer. Model and external execution latency dominate local work.
Projection updates should be incremental, context queries indexed, and artifact
content loaded only when selected. Record model calls, tokens, local selection
time, external action count, wall time, and supervisor calls from day one.

Add concurrency, embeddings, remote state, or a workflow engine only when a
repeatable benchmark demonstrates that the simple design is the limiting factor.

## External boundaries

Above the authoritative boundary, Vharness, models, supervisors, and environment
descriptions reason and propose. Below it, the operator-selected runtime binds
identity and credentials, enforces policy and isolation, executes actions, and
produces receipts. Benchmark/lab systems own targets, lifecycle, and validation.
Vharness neither asserts authorization nor interprets possession of a tool as
permission; authorization is established by the operator before use.

## Compatibility and migration

Retain the existing package and CLI while implementing the new kernel under a
separate internal namespace. Existing model adapters may be reused after they
can return typed results and usage. Existing assessment code may become an
environment integration, but its probe/detector abstractions do not define the
new kernel. No old database format is silently upgraded.

## Alternatives considered

- **AgentStorm-first redesign:** rejected by operator direction and unnecessary
  to validate the new core.
- **Benchmark-specific profiles:** rejected by ADR-0003.
- **Harness-enforced security and grading:** rejected by ADR-0002.
- **Event sourcing plus vector database plus distributed actors initially:**
  rejected as unmeasured complexity; SQLite and a single writer satisfy the
  first durability and retrieval requirements.
- **Supervisor with direct tools:** rejected initially because advisory guidance
  is easier to attribute, test, and constrain.

## Sources, assumptions, and freshness

- NVIDIA AVO paper, version 1: <https://arxiv.org/html/2603.24517v1>
- NVIDIA AVO ARC-AGI-3 article: <https://developer.nvidia.com/blog/nvidia-avo-reaches-100-on-arc-agi-3-demonstrating-a-frontier-level-general-purpose-architecture-for-long-horizon-autonomous-agents/>
- Gymnasium environment API: <https://gymnasium.farama.org/api/env/>
- ARC-AGI-3 documentation: <https://docs.arcprize.org/>

The paper and article inform decomposition and hypotheses, not compatibility
claims. Exact external protocol versions and benchmark datasets are pinned when
PHASE-0004 begins and recorded in BENCH-0001 evidence.

## Open questions

No question blocks PHASE-0001. Threshold tuning, shared-memory import policy,
and whether learned retrieval outperforms deterministic retrieval require
experiments after an end-to-end baseline exists.

## Implementing phases

PHASE-0001 through PHASE-0004 implement this architecture in dependency order.

