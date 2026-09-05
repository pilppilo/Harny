# Persistence, transitions, and execution boundaries

## Canonical state and database

Use a new SQLite database namespace per workspace. Enable WAL and foreign keys
on connection setup. Use explicit transactions and parameterized SQL. The owning
coordinator serializes writes; do not share its connection across I/O workers.

Minimum tables:

| Table | Required columns and constraints |
| --- | --- |
| `sessions` | Session ID primary key, latest sequence, schema version, cached status/objective version; mutable values rebuildable from events |
| `events` | Event ID primary key, session FK, sequence, kind, schema version, objective version, causal/correlation IDs, recorded time, provenance, canonical payload; unique `(session_id, sequence)` |
| `artifacts` | Digest primary key, size, media type and publication metadata; evidence provenance remains in referring records |

Add indexes on `(session_id, correlation_id, sequence)` for operation history and
on `(session_id, kind, sequence)` for typed event queries. Additional projection
tables are justified by actual queries, not created for every dataclass.
Keep source identity/provenance per reference because identical bytes may come
from different sources. A content digest is not an authority identity.

`SqliteJournal` exposes bounded ordered reads and atomic batch append with an
`expected_sequence`. Validate/reduce the entire proposed batch before committing.
Append events, update the session cursor, and update any materialized projections
in one transaction. A cursor mismatch produces a visible conflict, not a retry
that silently applies the batch to a different state.

The journal owns BEGIN/COMMIT/ROLLBACK. Domain helpers never commit. The session
chooses the logical event batch. External I/O never occurs inside its transaction.
Do not expose SQL connections through the public session API.

## Event reduction

Implement a pure `reduce_event(state, event) -> state` operation and an ordered
replay function using the same reduction rules as live execution. Supply IDs,
timestamps, and decisions in events; replay never invokes clocks, UUID factories,
models, runtime calls, or evaluators.

Do not copy the entire historical journal into every state snapshot. State views
hold current working values and references; historical attempts and receipts are
queried by cursor/identity. Update projections incrementally during live work.

Persist both operation intent and external receipts. Relevant event families are:

- Session creation, objective change, operator command and application result.
- Attempt start/closure and seeded/accepted lineage nodes.
- Proposal intent, dispatch observation, receipt received, reconciliation.
- Reservation creation, measured usage and settlement/uncertainty.
- Evaluation request/receipt and promotion disposition.
- Waiting/control transitions and checkpoints.

Use explicit typed payloads for families in the current phase. Do not add event
types for hypothetical integrations. An event's causal links must resolve to the
same session unless an explicit imported-evidence contract permits otherwise.

## Receipt identity and ordering

Preserve inbound raw bytes or their atomically published artifact reference before
interpretation affects work. Transport parsing failures become recorded boundary
failures and cannot disappear behind a log line. A malformed record whose claimed
session cannot be validated belongs to the connection's configured intake context,
not the untrusted session ID in its body.

An exact duplicate receipt ID/content is idempotent. The same receipt ID with
different content is a contract/integrity conflict. Separate status updates for
one operation use separate receipt identities. If the external interface lacks a
native receipt ID, the mechanical connection must document a stable derivation
from operation identity, external sequence/version, and canonical content.

Out-of-order and late receipts remain evidence. Use the configured external
revision/ordering semantics to select effective status; an older running receipt
cannot replace a terminal result. Contradictory terminal results without a
declared supersession rule remain visible and cannot silently enable promotion.
Late usage may settle an earlier uncertain charge without duplicating it.

## Dispatch sequence

For an action or evaluation:

1. Apply pending durable controls. Check current objective version, expected state
   revision, context applicability, operation shape and configured capabilities.
2. Calculate the reservation against known usage plus outstanding exposure.
3. In one transaction, record reservation and operation intent with stable IDs.
4. Dispatch to the existing external connection outside the transaction.
5. Enqueue its response, then atomically persist receipt and usage reconciliation
   before any later decision uses them.

Do not claim exactly-once delivery across SQLite and an external service. The
durable intent can survive a crash even when local code cannot tell whether the
external service received it. Stable identity and external reconciliation are
what make recovery possible.

If an upper resource bound is required for a configured budget but unavailable,
return an explicit insufficient-bound scheduling outcome. Do not claim a hard
budget guarantee using an estimate. Known measurement beyond a reservation is
recorded in full and affects future scheduling; never clamp it to the reservation.
Runtime cancellation and application time limits cannot guarantee refunded cost.

## Local lifecycle and steering

| Input/condition | Required local behavior |
| --- | --- |
| Start created session | Enter running through a durable transition |
| Await external result or operator answer | Enter waiting with a named condition; no busy model calls |
| Pause | Record paused before new decisions or dispatch; retain pending operation state |
| Resume | Return to running or the unresolved wait, based on current state |
| Stop | Enter stopping, prevent new work, record any supported cancellation request; retain unresolved operation identity |
| Late receipt while paused/stopped | Preserve and reconcile it; do not restart autonomous work |
| Finite completion proposal | Require applicable current external completion evidence |
| Ongoing objective | Checkpoint/wait; only an explicit current end condition supports completion |
| Objective-changing steer | Create the next objective version; old work remains attributed to its original version |

A stopped session means local scheduling stopped, not that the external world
was rolled back or every pending effect vanished. Admission acknowledgement and
durable command application must be observable separately. Duplicate commands
with identical identity/content do not repeat their effect.

A steering event invalidates old decision applicability immediately. Do not
discard late results: their usage still counts and their evidence remains
available, but they cannot promote or complete the new objective. Resume and
checkpoint must retain this distinction.

## Promotion transaction

`check_promotion(state, request, receipts)` performs reference/applicability checks
and returns a typed disposition. It does not compare scores itself. Require:

- Current objective version and expected lineage head.
- Correlated evaluation request, attempt, baseline, evaluator identity/version.
- Matching evaluated state identity and digest/revision where declared.
- Required evidence is present and intact.
- External acceptance and applicable native comparison semantics.

An externally rejected or incomparable result cannot promote. A mismatch in
current applicability is stale even if the evaluator originally accepted it.
An equivalent score is not automatically accepted or rejected by local code;
preserve the evaluator contract's explicit decision.

Commit the promotion event, new single-parent node, attempt disposition, and
projection/cursor updates together under the expected head/cursor. Repeated
promotion of the same accepted result returns the existing disposition/node.
No failed attempt enters lineage. A changed head forces a fresh applicability
decision; it must not silently attach the result to another parent.

## Artifacts

Publish through `ArtifactStore.put(...) -> ArtifactRef`: write a temporary file in
the destination filesystem, stream/hash its bytes, verify expected hash/size when
provided, flush/fsync, and atomically rename into the digest-derived location.
Synchronize the parent directory where required for durable publication. An event
may reference the artifact only after publication succeeds. Existing matching
bytes may be reused after integrity checks; never overwrite conflicting content.

Separate trusted local paths from opaque external artifact references. Resolve
local paths from validated digests inside the store root; reject traversal or
model-supplied arbitrary paths. Reads verify required evidence before promotion.
Interrupted publication may leave an unreferenced file, which is preferable to a
committed dangling reference. Cleanup must not remove referenced evidence.

PHASE-0001 needs correct publication/read semantics, not a garbage collector.
PHASE-0002 adds selective retention as described in the capability specification.

## Checkpoints and restart

A checkpoint hashes a versioned canonical projection at a specific journal
cursor. Define that cursor as the last event represented, before the checkpoint
record itself, to avoid a self-referential hash. Derived checkpoints can accelerate
loading; the journal remains authoritative.

On reopen, verify the checkpoint against its represented prefix, then replay the
suffix through the latest committed journal cursor. Rebuild incompatible or
mismatching derived projections from valid source events. Corrupt source events
or required evidence fail visibly; a projection mismatch is not permission to
discard authoritative history.

Recover pending intents through external reconciliation where supported:

| External outcome | Resume behavior |
| --- | --- |
| Known terminal result | Persist and settle, then apply current-version checks |
| Known running/accepted | Continue waiting with the same operation identity |
| Authoritatively not submitted | Redispatch only if still current, budgeted and permitted by documented external guarantees |
| Unknown/unsupported | Mark indeterminate; retain uncertainty and do not blindly resend |

Cancellation acknowledgement alone does not prove absence of an effect. Reopening
must not generate a new idempotency key for the same pending operation. Evaluation
requests need the same recovery discipline because evaluations may consume time,
budget, or external effects. Tests must exercise the crash windows below.
