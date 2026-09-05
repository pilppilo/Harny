# Types and callable contracts

## Representation rules

Use `@dataclass(frozen=True, slots=True)` for domain records. Use tuples for
ordered collections and copied/read-only mappings where mappings are needed.
Freezing a dataclass is insufficient if its members remain externally mutable.
IDs are opaque nonempty strings; do not infer authority or ordering from them.
Sequences and objective versions are positive integers assigned by the coordinator.

Define a recursive JSON value alias for transport data rather than using `Any`.
Domain objects cross internal boundaries; JSON-compatible dictionaries exist at
codec and external boundaries. Encode with stable key ordering, UTF-8, fixed
separators, and rejection of NaN/infinity. Keep array order. Hash that documented
encoding, not Python `repr`, unordered sets, or incidental dataclass layout.

All work-affecting envelopes carry schema version, stable ID, session ID,
objective version, causal references, timestamp, and provenance. Transport
receipt identity is distinct from operation/proposal identity because an operation
can produce multiple status updates. Keep unknown same-version fields as opaque
extensions and preserve original input; never let extensions override typed
fields. Reject unsupported schema versions for interpretation without losing the
raw inbound record. Do not automatically migrate legacy databases.

External decoders check required fields, exact types (including bool versus int),
enum values, bounds, reference shape, timestamps, and supported schema versions.
Validate action arguments against the configured action schema before dispatch.
Do not silently ignore unsupported schema constructs or implement a pretend
general JSON Schema validator. Select a maintained validator if actual declared
schemas require it; use existing dependencies where adequate and justify any new
dependency in the implementation handoff. Domain constructors enforce intrinsic
invariants even for direct library callers.

## Foundational records

ARCH-0001 owns required meanings. The following is the code-level decomposition;
fields listed as references point to immutable records rather than copied state.

| Record | Essential fields / representation |
| --- | --- |
| `TaskSpec` | Task/session identity, objective version and text, constraints, finite/ongoing mode, success evidence, budgets, environment/knowledge/evaluation references |
| `EnvironmentContract` | Environment identity/version, initial observation and state, action space, configured runtime capabilities |
| `ActionDefinition` | Name, description, argument schema, configured effect/revision semantics |
| `RuntimeCapabilities` | Explicit supported/unsupported cancellation, idempotency, reconciliation, snapshot and revision semantics; no model-provided guarantees |
| `StateRef` | Owner/environment identity, opaque state ID or trajectory cursor, optional digest/revision, externally declared restorable flag |
| `ArtifactRef` | SHA-256 digest, byte size, media type, provenance; no arbitrary writable path supplied by model output |
| `Observation` | Envelope, source cursor/time, typed content or artifact references |
| `ActionProposal` | Envelope, attempt ID, action/arguments, expected revision/outcome, context cursor, deadline, reservation ID, supported idempotency key, concise rationale |
| `ExecutionReceipt` | Envelope, proposal/operation identity, external revision, status, output/error references, timing, usage, raw-input reference |
| `EvaluationRequest` | Envelope, attempt, evaluated state/digest, baseline, evaluator contract/version, expected lineage head |
| `EvaluationReceipt` | Request correlation and the same applicability identities, native constraints/objective vector/comparison/acceptance, evidence and raw-input reference |
| `PromotionRequest` | Envelope, attempt, state/digest, evaluation IDs, expected current head |
| `Attempt` | ID, objective version, base committed node, start/result state, starting/ending event cursors, evaluation references, disposition |
| `CommittedNode` | ID, objective version, single parent (root has none), state, accepted evaluation reference, native objective vector, change summary, commit time |
| `Checkpoint` | Objective version, represented journal cursor, projection version/hash, pending IDs, budgets/reservations and controls |

`EvaluationContract` and `KnowledgeSource` follow ARCH-0001 without copying their
contents into every request. Store explicit contract versions and provenance.
Objective vectors retain named dimensions, native direction, and external
comparison. Do not compute a synthetic scalar fitness or reinterpret acceptance.

Seeded root creation is a distinct event with external initial-state provenance;
it is not falsely represented as a newly evaluated improvement. Only successors
require promotion from applicable accepted evaluation. Steering changes objective
version without rewriting old nodes; requests bind both objective version and
the exact current baseline/head.

## Finite states and result types

`SessionStatus`: created, running, waiting, paused, stopping, completed, failed,
stopped. A waiting view includes a specific condition and correlation ID where
applicable. A paused view retains any outstanding wait/operation independently.

`ExecutionStatus`: accepted, rejected, running, succeeded, failed, indeterminate.
An indeterminate operation remains unresolved; a later authoritative receipt may
resolve it. Preserve history instead of overwriting its earlier status event.

`PromotionResult`: accepted, rejected, incomparable, stale, with reason and
supporting receipt references. This result expresses applicability and external
judgment, not a second evaluation.

Operator commands are a union of separate `Message`, `Steer`, `Pause`, `Resume`,
`Stop`, `CheckpointRequest`, and `EvaluationCommand` dataclasses. Each carries
command identity and causal context. `Steer` carries a typed objective update;
changes to intent or acceptance create a new version. An ordinary message does
not silently edit objective acceptance. Avoid one record with unrelated optional
fields for all commands.

PHASE-0002 adds an `AgentResult` union: action, lineage query, knowledge query,
memory update, evaluation request, operator question, wait, completion proposal.
Each variant has the fields that apply to that variant. Lifecycle metadata such
as authoritative session identity, reservation, and IDs is bound by the
coordinator; model text cannot manufacture trusted runtime semantics.

## Resource types

Represent `BudgetLimits`, `ResourceReservation`, and `UsageMeasurement` separately.
Track integer fresh/cached/output token counts, action/evaluation/model call
counts, elapsed duration, and optional monetary cost with currency. Use exact
decimal strings on the wire and `Decimal` for monetary arithmetic when supplied;
never invent prices. Missing measurement is `None`, not zero. Distinguish
cumulative amounts from peak values and estimated reservations from actual use.

A reservation binds operation ID, objective version, declared resource bounds,
and disposition. Settlement is idempotent by operation and measurement identity;
repeated receipts cannot double-charge. Preserve outstanding uncertainty when a
timeout or unknown measurement prevents settlement. Expose known usage and
unsettled exposure separately; never release uncertain cost as though it were free.

## Application API

These signatures describe intended calls; they are specification notation, not
stub files to generate. All methods document exceptions and blocking behavior.

| Callable | Contract |
| --- | --- |
| `Session.create(task, *, journal, artifacts, environment, runtime, evaluator) -> Session` | Validate initial contracts, persist seed and initial objective atomically, return without launching autonomous work |
| `Session.open(session_id, *, journal, artifacts, environment, runtime, evaluator) -> Session` | Rebuild durable state, verify compatibility, expose pending reconciliation; never blindly resubmit |
| `Session.enqueue(command) -> CommandToken` | Admit a typed operator command with stable identity; not yet an applied acknowledgement |
| `Session.receive(receipt) -> ReceiptToken` | Admit an external typed receipt; transport decoding belongs to the connection boundary |
| `Session.advance() -> StepOutcome` | Drain a bounded batch of inputs, apply controls, and perform at most one new dispatch/decision; do not sleep waiting for external completion |
| `Session.view() -> SessionView` | Return an immutable view at a named durable cursor |
| `Session.checkpoint() -> Checkpoint` | Through the coordinator only, persist a consistent projection reference |
| `Session.events(after_sequence, limit) -> tuple[Event, ...]` | Bounded durable observation for embedding applications and UI |

First-phase scripted choices enter a narrow typed coordinator input, not a model
prompt or new public workflow language. The implementation may expose a named
internal `apply_choice` method for this test seam. PHASE-0002 connects the kernel
to that same application path.

`StepOutcome` includes durable cursor, session status, applied command IDs,
dispatched operation ID if any, wait reason, and whether another immediate step
can make progress. It must let a caller avoid busy polling. Snapshot query methods
must not dispatch operations as an undocumented side effect.

## External ports

Use structural `typing.Protocol` contracts with fully annotated methods:

- `Environment.describe() -> EnvironmentContract`: obtain mechanical task and
  action metadata from the configured external connection.
- `Runtime.submit(proposal) -> ExecutionReceipt`: exchange a proposal with the
  existing external runtime; receipt may say accepted/running, not just terminal.
- `Runtime.reconcile(operation_ref) -> ReconciliationResult`: report known
  receipt, explicitly not submitted, unknown, or unsupported.
- `Runtime.cancel(operation_ref) -> CancellationResult`: only invoked when the
  configured runtime supports it; reports external acknowledgement, not undo.
- `Evaluator.evaluate(request) -> EvaluationReceipt`: request the configured
  external evaluation and preserve native judgment.
- `Evaluator.reconcile(request_ref) -> EvaluationReconciliationResult`: resolve
  interrupted evaluation where the external contract supports it.

Unsupported features are explicit typed outcomes. Do not assume every port has
an implementation for every capability. Timeouts and transport failures retain
operation identity and uncertainty. Ports may block for their configured timeout;
the session writer must remain available while their I/O worker runs.

## Errors

Use a small vocabulary: `ContractError` for invalid caller/boundary input,
`TransitionError` for invalid local operations, `PersistenceError` for storage
failure, and `IntegrityError` for corrupt or incompatible required state. Define
inheritance only where callers benefit; integrity may subclass persistence.
Translate underlying errors with `raise ... from exc`.

Normal runtime rejection, unknown completion, stale evaluation, unsupported
capabilities, and budget refusal are typed outcomes/events. Do not hide them in
generic exceptions or broad catches. Unexpected programming errors must fail
visibly. There is no broad "catch everything and continue" in the session loop.
