---
id: ARCH-0001
title: AVO-inspired long-horizon agent system
type: architecture
status: accepted
owners: []
created: 2026-09-04
updated: 2026-09-04
depends_on: [ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005]
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
- Climb the software, Gymnasium, ARC-AGI-3, and authorized-assessment
  capability ladder without changing the core by benchmark identity.
- Remain simple enough to test deterministically and inspect after failure.

## Non-goals

- Reproducing NVIDIA's private code or guessing unspecified AVO internals.
- Building a multi-agent swarm, distributed scheduler, or workflow language.
- Making Vharness an authorization, identity, credential, isolation, or policy
  enforcement boundary.
- Replacing environment lifecycle, audit, scoring, or validation systems.
- Creating benchmark-specific agent profiles or hidden benchmark strategies.
- Treating a benchmark name or aggregate score as the product's identity.
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
11. A variation attempt may contain many planning, inspection, implementation,
    debugging, and evaluation actions. Those are agent-chosen activities, not a
    coordinator-enforced pipeline.
12. Unsuccessful attempts remain in trajectory history but never enter the
    committed lineage. A commit requires an externally accepted evaluation.

## Components and responsibilities

### Session coordinator

Owns the session state machine, serializes state-changing events, applies
operator controls, invokes the kernel, dispatches proposals to the external
runtime connection, and schedules checkpoints. It is the only event writer in
the first implementation; UI and receipt readers submit messages to its queue.

### Agent kernel

Runs the domain-neutral decide/act/observe loop. Given a `TaskSpec`, selected
context, an environment contract, budgets, and current controls, it returns one
typed result: an action proposal, a lineage or knowledge query, a memory update,
an evaluation request, a question to the operator, a wait, or a completion
proposal. It autonomously chooses when to inspect prior committed states,
consult knowledge, modify work, debug, or evaluate. It never invokes a tool
directly.

### Context assembler

Builds a deterministic, token-bounded model input from mandatory state and
ranked memory items. It reports included and omitted item IDs so any decision
can be reconstructed and selection quality can be measured.

### Journal and memory projections

The journal stores immutable events. Projections expose working state,
episodes, knowledge, hypotheses, failures, operator direction, budgets, and
attempt/committed-lineage views. Projection code is versioned and replay-tested.

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

### Attempts and committed lineage

Tracks the AVO distinction between internal search and committed progress. An
attempt starts from a committed state and may span many actions and evaluations.
Its events always remain in the journal, but a successor joins the lineage only
after the external evaluator accepts it. The initial implementation maintains
one active lineage, matching the paper; population archives and branching wait
for evidence that they are needed.

Environments expose mechanical state semantics. Candidate-capable environments
may supply opaque restorable state references. Irreversible or externally owned
environments supply trajectory cursors instead; a committed milestone records
externally supported progress and never implies that Vharness can roll back,
reset, or control the environment.

## Public contracts

Contracts are versioned JSON-compatible records. Python uses frozen dataclasses,
enums, and `typing.Protocol` at process boundaries; canonical JSON is used for
persistence and external transport. Unknown fields are retained on ingest,
required fields are validated, and schema versions are explicit. Every envelope
that can affect work includes `session_id`, `objective_version`, stable identity,
causal parent IDs, timestamp, and provenance. Runtime identity and effect
guarantees come from trusted connector/runtime configuration, never model text.

| Contract | Required meaning |
| --- | --- |
| `TaskSpec` | `task_id`, `objective_version`, objective, constraints, success evidence requested, finite/ongoing completion mode, budgets, environment identity, initial observations, knowledge sources, and evaluation contract |
| `ActionSpace` | Named actions with argument schemas plus trusted cancellation, idempotency, reconciliation, snapshot, and revision semantics |
| `EvaluationContract` | External evaluator identity; hard-constraint and objective names; objective directions; native comparison/acceptance semantics; and version |
| `Observation` | Source, sequence/cursor, typed content or artifact references, and external timestamp/metadata |
| `ActionProposal` | Proposal ID, objective version, action name/arguments, expected state revision and observable outcome, deadline, resource reservation, idempotency key when supported, concise rationale, and context cursor |
| `ExecutionReceipt` | Proposal and objective IDs, external operation/revision, status, outputs/artifacts, measured usage, error, timing, and raw receipt reference |
| `KnowledgeSource` | Source ID, description, version/provenance, access reference, and content type for agent-directed consultation |
| `StateRef` | Opaque external or workspace state identity, content digest when available, and whether the external system declares it restorable |
| `Attempt` | Attempt ID, base committed-node ID, starting state reference, event range, status, and resulting state/evaluation references |
| `Investigation` | Optional grouping of a question, zero or more hypotheses, attempts/actions/evidence, remaining uncertainty, usage references, and active/paused/concluded/abandoned disposition |
| `ProgressClaim` | Outcome or knowledge progress with before/after condition, scope, evidence IDs, assessor provenance, and pending/supported/rejected/stale status |
| `RecoveryEvent` | Interrupted operation, reconciliation evidence, restored local state reference, duration, and outcome; operational health rather than productive progress |
| `EvaluationReceipt` | Evaluator and objective versions; evaluated state/hash and baseline IDs; hard constraints; objective vector; comparison; external acceptance; evidence; and raw receipt reference |
| `PromotionRequest` | Evaluated state/hash, evaluation IDs, objective version, and expected current lineage head; returns accepted/rejected/incomparable/stale without regrading |
| `OperatorCommand` | Command ID and one of message, steer, pause, resume, stop, checkpoint, or request-evaluation with optional reason |
| `Guidance` | Trigger evidence, supervisor diagnosis, constraints, suggested experiments, and expiry/cooldown |
| `Checkpoint` | Objective version, journal cursor, projection versions/hashes, pending proposal IDs, reserved/remaining budgets, and active controls |
| `CommittedNode` | Node ID, single parent ID, accepted state reference, change summary, evaluation receipt ID, objective vector, and commit time |
| `AlternativeRetention` | Optional artifact identity, retention reason, supporting evidence, availability, attributable bytes, and review/expiry condition |

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
Publish an artifact by writing a temporary file, verifying its hash, and
atomically renaming it before an event commits its reference. Missing or corrupt
required evidence blocks dependent promotion.

An event contains `event_id`, `session_id`, monotonic sequence, kind, schema
version, recorded time, optional causation/correlation IDs, and canonical JSON
payload. Wall-clock time is descriptive; ordering comes from sequence. An event
and its session cursor update commit in one transaction.

Memory projections are deliberately distinct:

- **Working:** objective, current plan, controls, budgets, pending actions, and
  unresolved questions needed on the next step.
- **Investigations:** lightweight, overlapping work groups for questions and
  evidence. They do not require a hypothesis, candidate, fixed sequence, or
  successful conclusion.
- **Episodic:** compact spans of actions, observations, outcomes, and turning
  points with links to their source event ranges.
- **Knowledge:** evidence-backed facts, hypotheses, contradictions, confidence,
  scope, and provenance. Hypotheses never silently become facts.
- **Attempts:** complete internal search trajectories anchored to a committed
  state, including failed and non-improving work.
- **Lineage:** the ordered single-parent sequence of externally accepted states
  and their evaluation vectors. It excludes unsuccessful attempts.
- **Progress:** evidence-backed outcome and knowledge claims. Recovery and raw
  activity remain separate operational signals.

Failed-attempt metadata and lessons remain searchable, but retaining every large
failed artifact is unnecessary. Accepted states, pending effects, and evidence
required by unresolved or accepted claims are protected roots. Other artifacts
are retained only for a recorded tradeoff, unresolved hypothesis, or high
reproduction cost and may expire under a byte budget while their identity,
lesson, and availability status remain durable.

No vector database is required initially. SQLite FTS5, structured filters, and
deterministic scoring are sufficient until BENCH-0001 shows a retrieval ceiling.

## Control flow

A session moves through `created`, `running`, `waiting`, `paused`, `stopping`,
then one of `completed`, `failed`, or `stopped`. Waiting names a specific external
condition and does not imply completion or new authority. External evaluation can
support completion; only the coordinator commits the local state transition.

For each step, the coordinator:

1. Persists queued receipts and operator commands, then refreshes projections.
   A steering command that changes intent or acceptance creates a new objective
   version rather than rewriting prior work.
2. Applies pause/stop controls before any model call or proposal dispatch.
3. Ensures an active attempt is anchored to the latest committed node under the
   current objective version, then
   builds context and journals its manifest of selected event/item IDs.
4. Invokes the model through the existing model boundary for one typed result.
5. Validates shape, action name, arguments, trusted connector semantics, budgets,
   expected revision, objective version, and stale context cursor.
6. Reserves the declared resource bound and journals intent transactionally;
   invalid or unaffordable results become observations for repair.
7. Sends an action proposal outside the database transaction to the external
   runtime or applies a cognitive
   update/query locally as a new event. Lineage and knowledge queries return
   referenced records through the next context without external effects.
8. Persists returned receipts and measured usage, reconciling reservations even
   on error, before interpreting them.
9. On evaluation, verifies objective version, evaluated state/hash, evaluator
   version, baseline, and expected lineage head. It commits a successor only when
   the externally accepted receipt is applicable and current; otherwise the
   attempt continues, closes unsuccessfully, or records a stale/incomparable result.
10. Updates progress signals, requests supervision if triggered, and checkpoints
    at an external terminal receipt, operator control, committed successor, or
    configured event span.

One attempt may traverse the loop many times. The coordinator does not require
planning, implementation, evaluation, and bug-fixing to occur once or in a
fixed order. The agent controls their order and decides when to call the
external evaluation function, which is central to the AVO operator.

Late receipts retain their original proposal, objective, state, and causal
identity. They remain evidence but cannot advance a newer objective or lineage
head. Finite objectives complete only from current external evidence. Ongoing
objectives checkpoint between waits and require an explicit current end condition;
a scheduler wakeup alone is not progress, permission, or completion.

The coordinator permits at most one unresolved state-changing proposal per
session in the initial implementation. This makes crash recovery and causal
ordering obvious; parallel proposals require later benchmark evidence and a
new decision.

## Context and memory algorithms

Context has a hard token budget and three bands:

1. **Mandatory:** current objective version, environment/action contract, latest operator direction,
   knowledge/evaluation contracts, committed-lineage head, active attempt,
   active budgets, pending action, current plan, and latest receipt.
2. **Retrieved:** unresolved hypotheses, relevant evidence, prior failures, and
   episodes or committed nodes ranked against the objective, plan step, and
   latest observation.
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
stuck. Outcome progress is externally supported improvement or a newly satisfied
acceptance clause under the current objective. Knowledge progress is evidence
that resolves a named uncertainty, refutes an explanation, or changes a scoped
hypothesis. Recovery records continuity and reliability separately. Pending or
self-reported claims, new logs, tool-call counts, and repeated recovery do not
reset stagnation. Negative signals include repeated normalized actions or
evidence, recurring failure fingerprints, evaluation regression, and budget burn
without supported outcome or knowledge progress.

A plateau alone is not failure: the paper's trajectory shows discrete jumps,
long searches between commits, and diminishing returns. Repetition and absence
of new information are stronger signals than elapsed steps alone. The monitor's
window, thresholds, normalization, and cooldown are versioned run policy chosen
from a PHASE-0003 experiment, not fixed by this architecture. Every trigger
records its inputs so BENCH-0001 can measure false intervention and cost.

Supervisor guidance must name the observed pattern, identify assumptions to
challenge, and suggest a small discriminating experiment or replan. The main
agent may accept or reject it with a concise recorded reason. Repeated triggers
escalate from guidance to checkpoint/replan, then to an operator question; they
do not silently terminate externally controlled work.

A variation attempt starts from the current lineage head, states its intended
direction, performs as many ordinary external actions as needed, and invokes the
external evaluator when the agent judges the state ready. External acceptance
commits a successor; rejection retains the full attempt only in trajectory
history. One active lineage and one attributable direction per attempt are the
defaults. Population sampling, multiple parents, and archive management are
deferred, as they were outside the paper's evaluated single-lineage setting.

## Failure and recovery behavior

On startup, replay events through the checkpoint cursor, verify projection
hashes, rebuild mismatches, and enumerate pending proposals. Query the external
runtime for each pending proposal ID when reconciliation is available. Persist
the returned receipt and reconcile its resource reservation before continuing.
If completion cannot be determined,
mark the proposal `indeterminate`, expose it to the operator and agent, and do
not resend it automatically.

Model timeout, malformed output, runtime rejection, execution failure, evaluator
unavailability, and supervisor failure are typed events with bounded retry
budgets. Retries must either be safe reads or use the same externally supported
idempotency key. SQLite corruption or artifact hash mismatch stops the session
with diagnostic evidence rather than continuing from uncertain state.
Cancellation may stop waiting but cannot be assumed to undo an external effect.
A late result cannot complete or promote work under a different objective version
or lineage head.

## Performance and scaling assumptions

The first system is one Python process, one coordinator loop per active session,
and one SQLite writer. Model and external execution latency dominate local work.
Projection updates should be incremental, context queries indexed, and artifact
content loaded only when selected. Record model calls, tokens, local selection
time, external action count, wall time, supervisor calls, attempts, evaluations,
commits, and time/actions between commits from day one.
Resource records distinguish reserved from measured usage, cumulative quantities
from peaks, and fresh/cached/output tokens. Unknown provider cost is reported as
unknown rather than zero.

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
claims. Sections 3.1-3.3 establish the scored lineage, knowledge base, evaluation
function, autonomous multi-action variation step, single-lineage run, and
conditional supervision. They do not publish the internal agent, prompt, memory
algorithm, context algorithm, or supervisor thresholds; those remain Vharness
designs requiring local evidence. Exact external protocol versions and benchmark
datasets are pinned when PHASE-0004 begins and recorded in BENCH-0001 evidence.

## Open questions

No question blocks PHASE-0001. Supervisor threshold selection, shared-memory
import policy, and whether learned retrieval outperforms deterministic retrieval
require experiments after an end-to-end baseline exists.

## Implementing phases

PHASE-0001 through PHASE-0004 implement this architecture in dependency order.
