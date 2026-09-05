# Later capability modules and extension seams

This document describes code placement for PHASE-0002 through PHASE-0004. It does
not change their order, prerequisites, algorithms, or evidence requirements.
Implement modules when their phase begins; no empty classes or speculative APIs.

## Kernel and model boundary — PHASE-0002

`kernel.py` owns constructing a decision request from typed context and interpreting
a typed `AgentResult`. It has no SQL, terminal presentation, or runtime execution
access. The session applies results through its existing intent/reservation/event
path; the kernel cannot mutate committed state directly.

A model connection accepts a versioned `DecisionInput` and returns a
`ModelResponse` containing visible output, model identity, finish condition,
measured/unknown usage, and transport outcome. Separate response decoding from
provider transport. Persist the visible input and output, request identity,
objective version, context cursor/manifest, and usage. Hidden reasoning is neither
requested nor required.

Malformed model output becomes a bounded repair observation using the same path
for every provider. Retry ownership is explicit: the coordinator schedules and
accounts for retries, while any unavoidable transport-level attempts are exposed
and included in the reservation bound. A provider adapter must not silently double
the maximum output or hide additional paid calls.

The agent may query history, inspect knowledge, act, debug, and evaluate in any
order. Do not implement a mandatory plan/execute/evaluate workflow. A model swap
changes the connection, not the domain reducer or agent result semantics.

## Memory projections — PHASE-0002

`memory.py` owns typed working, episodic, knowledge, investigation, and progress
views over events. SQL indexing belongs in journal/query infrastructure, not in
model prompts or the reducer. Use FTS5 and structured filters as specified by
ARCH-0001. Queries return source references plus excerpts, not detached claims.

| Type | Fields beyond the common envelope |
| --- | --- |
| `KnowledgeItem` | Statement, scope, hypothesis/supported/contradicted/retired status, evidence IDs, confidence/provenance, superseding or conflicting item references |
| `Episode` | Source event range, concise summary, artifact/evidence references, summary model/version |
| `Investigation` | Question, optional hypotheses, referenced attempts/actions/evidence, uncertainty, disposition and usage IDs |
| `ProgressClaim` | Outcome/knowledge category, before/after condition, scope, evidence, assessor provenance, pending/supported/rejected/stale status |
| `RecoveryEvent` view | Interrupted operation, reconciliation evidence, local resumed-state reference, duration, outcome |
| `AlternativeRetention` | Artifact identity, reason, evidence, availability, attributable bytes, review/expiry condition |

Investigations may overlap, begin without hypotheses, and be abandoned or reopened
by events. They are organizational projections, not another task scheduler.
Deduplicate shared usage by operation/measurement ID when aggregating across
investigations. Confidence alone cannot promote a hypothesis into a supported fact.

Evidence must support a specific change in knowledge or outcome. Repeated claims,
raw tool counts, new summaries, and successful process restart do not create
productive progress. Keep contradictory evidence visible and version-scoped.

## Context selection — PHASE-0002

`context.py` exposes a deterministic assembly operation taking the current state,
retrieved candidates, policy/version, and token counter, returning `ContextBundle`
and `ContextManifest`. It does not call the model or mutate memory.

Implement the mandatory/retrieved/recent bands and ranking terms in ARCH-0001:
FTS/BM25 relevance, salience, unresolved status, causal proximity, bounded recency,
and greedy maximal-marginal-relevance duplicate penalties. Keep ranking and
selection as inspectable functions. Stable ties use event sequence and ID.
Record the initial coefficients and token-counter identity/version explicitly in
run configuration; do not claim the paper supplies them. Algorithm changes based
on untested hypotheses follow the required EXP process rather than quietly
replacing this accepted ranking design.

The manifest records included and omitted item IDs/reasons, source cursors,
objective version, policy version, and token allocation. Account for serialization
and request overhead plus reserved output when checking the model window. If
mandatory context does not fit, return a typed overflow outcome; never silently
drop operator direction, governing contracts, or pending-action identity.

Large history remains queryable even if omitted from current context. Summaries
link to source ranges and never overwrite originals. The same input/policy/token
counter produces the same selection manifest. This is reproducible context
construction, not a guarantee of deterministic provider output.

## Artifact retention — PHASE-0002

Select retention candidates using recorded reasons and byte budgets. Before
deleting local optional bytes, compute protected roots from accepted states,
pending operations, and evidence needed by unresolved or accepted claims across
the entire workspace. Shared bytes are charged once and remain protected if any
session needs them.

Journal eviction intent and availability outcome so interrupted deletion can be
reconciled. Preserve identity, source, failure lesson, and the fact that bytes are
unavailable. Do not erase journal events or claim external artifacts have been
deleted. Byte storage mechanics remain in `artifacts.py`; protection/retention
decisions belong to the memory/application layer.

## Supervision — PHASE-0003

`supervision.py` separates a deterministic progress monitor from a model-backed
advisory call. Monitor inputs are supported outcome/knowledge claims, native
evaluation results, repetition/failure fingerprints, and resource consumption.
Recovery and activity stay separate operational signals.

The monitor returns either no trigger or `SupervisionTrigger` with policy version,
input event IDs, signal values and cause. The EXP-selected policy supplies windows,
normalization, thresholds, hysteresis and cooldown. Do not invent defaults in the
implementation or select them by benchmark identity.

The supervisor receives only a bounded trajectory digest and returns typed
`Guidance`. It has no runtime port, journal writer, or direct state mutation.
The main agent's acceptance/rejection and rationale are durable events. Guidance
expiry, repeated-trigger escalation and failed-supervisor handling are explicit.
Reuse the session's reservation and usage path for supervisor calls.

## External integrations — PHASE-0004

Connections translate external observations, action schemas and receipts into the
existing records. Domain knowledge enters as observations or referenced sources.
Do not add benchmark names to kernel branches, hidden prompt selection, memory
policy, or supervisor thresholds.

Contract tests use recorded external fixtures and the same core configuration.
Native score reporting stays external; diagnostic counters are library views,
not another grader. Campaign tools consume exported manifests/receipts and remain
separate from session decision logic. A real protocol mismatch is reported for a
governing design decision rather than buried in an adapter.
