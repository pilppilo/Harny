# Implementation sequence and verification handoff

## Before implementation

Read the entry documents in this directory and the current governed route. Inspect
the relevant source, tests, working-tree changes, and tool configuration again.
The baseline for this specification has Python >=3.10, pytest, and an existing
OpenAI dependency. Black 26.5.1 and Pylint 4.0.7 were available at `/usr/bin` when
this handoff was prepared. `pyproject.toml` did not yet configure either tool or a
type checker. Availability on the developer machine is not reproducible project
configuration.

Capture the implementation baseline revision and test output. Do not mix user
changes into a cleanup. Keep plans unchanged under the user's current instruction;
report any unmet formal phase prerequisite instead of editing its status.

## First-phase implementation order

1. Add the minimal domain records, explicit codecs, caller-relevant errors, and
   pure transition rules. Test invalid construction and boundary input.
2. Add the concrete SQLite journal and atomic artifact store. Prove replay,
   duplicate handling, publication integrity, and expected-cursor transactions.
3. Add objective-version, attempt, lineage, and resource projections. Prove stale
   applicability and idempotent settlement before external dispatch is connected.
4. Add the session API with a serialized inbox, controls, bounded advancement,
   immutable views, and dependency ownership. Drive it with scripted choices.
5. Add test-only runtime/evaluator implementations and connect durable intent,
   dispatch, receipt, evaluation and promotion handling. No real environment
   integration is needed to prove these contracts.
6. Exercise restart and every crash window. Fix the shared transition/persistence
   boundary rather than adding special cases in the CLI or tests.
7. Add a thin opt-in demonstration/CLI entry point calling the tested library.
   Keep the existing default path. It must demonstrate behavior, not implement it.
8. Run the checks below and hand off evidence plus any remaining limitations.

The implementing model should not generate all records/modules for later phases
at step 1. Implement the first-phase contract in full, including recent objective,
reservation, artifact, and stale-result requirements; small does not mean partial.

## Test organization

Use existing pytest and temporary-directory fixtures. Suggested responsibility
groups under `tests/agent/` are contracts, transitions/resources, journal/artifacts,
session, and recovery. Split where setup and responsibility differ. Use small
deterministic fakes at ports and real temporary SQLite for persistence; do not
mock the reducer or SQL methods to make an integration test pass.

| Required scenario | Observable assertion |
| --- | --- |
| Typed boundaries | Wrong/missing types, negative bounds, invalid enum/schema, mutable aliasing and non-finite JSON values cannot enter domain state |
| Codec round trip | Typed fields and unknown same-version extensions survive; canonical bytes are stable |
| Ordinary multi-action attempt | Several scripted actions/evaluations can occur before one accepted successor |
| Failed/regressed/incomparable evaluation | Evidence remains queryable without a locally invented acceptance or lineage advance |
| Equivalent external result | Follow external acceptance semantics; do not infer acceptance from equality alone |
| Duplicate input | Same command/receipt/promotion applied once; conflicting reuse of an ID is visible |
| Out-of-order status | Old running receipts cannot downgrade terminal status; contradictory terminal evidence is surfaced |
| Objective A changed to B during I/O | A's late output/usage is retained but cannot promote or complete B |
| Stale applicability | Changed head, baseline, evaluator version, state/hash or objective prevents promotion |
| Budget lifecycle | Reserve before dispatch; settle once on known usage; retain unknown exposure on timeout or missing cost |
| Actual usage exceeds reservation | Full measured value retained and future scheduling reflects it |
| Pause/stop during slow I/O | Durable control is applied without waiting for the slow call; no subsequent work dispatched |
| Waiting and ongoing task | Waiting is observable, does not burn model calls, and does not imply completion |
| Unsupported guarantees | No inferred idempotency/cancellation/reconciliation or automatic resend |
| Artifact publication failure | No committed reference precedes verified publication; hash/path failures are visible |
| Repeated replay | Same journal yields same state and canonical projection hash |
| Checkpoint plus suffix | Resume includes events after the checkpoint and rebuilds only derived mismatches |
| API embedding | Create, drive, inspect, checkpoint and reopen without CLI imports or terminal output |

Crash injection must cover at least: before intent commit; after intent before
submit; after submit before receipt persistence; after receipt before subsequent
interpretation; during promotion transaction; after promotion before caller
acknowledgement; during artifact publication; and after a checkpoint with a
nonempty event suffix. Reopen from disk using a new connection/session instance.
Assert no duplicate external submission when completion is uncertain, no duplicate
commit or usage charge, and complete replay. At least one subprocess termination
test should supplement exception injection to exercise actual process loss.

Use fake external state that survives replacement of the local session in these
tests. Resetting the fake along with the session would conceal duplicate effects.
Do not require a live model, network connection, or secret for the first-phase
suite. Existing tests remain regression coverage.

## Formatting, linting, and typing

At implementation time, configure Black for line length 88 and Python 3.10 in
`pyproject.toml`. Configure Pylint consistently, including Python target and source
import resolution. Use the installed tools; record their versions. If dev-tool
dependencies are declared for reproducible setup, keep them out of runtime
dependencies and update the lock through the normal project workflow.

Check only the new package and actually changed legacy/test files with Black and
Pylint. Do not introduce unrelated repository-wide formatting churn. New code must
have no unexplained lint failures. Do not use a score threshold to hide errors,
globally disable whole categories, or contort domain types to satisfy a cosmetic
warning. A narrow suppression needs a local reason; for example a validated
protocol record may legitimately have many fields. Fix responsibility problems
instead of suppressing complexity warnings reflexively.

Representative commands from the repository root, once paths exist:

```sh
black --check src/vharness/agent tests/agent
PYTHONPATH=src pylint src/vharness/agent tests/agent
uv run pytest tests/agent
uv run pytest
git diff --check
```

Include changed integration files explicitly in the formatting/lint command.
Run tools in an environment where project dependencies resolve; system Pylint
and the project interpreter may differ. An import error due to tool setup must
be fixed or reported, not globally disabled. Do not use Python 3.14-only syntax
because the locally installed formatter/linter runs on that interpreter.

Pylint is not a full static type checker. If the repository has acquired a type
checker by implementation time, run its narrow relevant target. Otherwise report
that no type checker is configured; do not claim type-check verification from
Pylint or annotations alone. Exercise the supported Python minimum when that
interpreter is available, and disclose when it was not tested.

## Design review checklist

- Public library calls are usable without CLI, global registration or hidden I/O.
- Every module has a cohesive owner responsibility and an acyclic import direction.
- Domain transitions and resource arithmetic are independent of persistence and
  external clients; infrastructure cannot decide success or agent strategy.
- Session orchestration delegates parsing, SQL, artifact handling and calculation
  instead of absorbing them into one large class.
- Inputs have types and boundary validation; immutable views do not leak mutable
  state. No unexplained `Any` or unstructured internal payload dictionaries.
- Errors preserve causes; expected external outcomes remain typed evidence.
- IDs, sequence, objective version, state revision and lineage checks remain
  explicit throughout dispatch, receipt handling and restart.
- Dependencies and close/transaction ownership are explicit and documented.
- No no-op placeholder packages, custom framework, or unsupported external
  responsibility has been added.

## Final implementation handoff

Report files/API added, the behavior demonstrated, exact commands and outcomes,
unrun checks with reasons, tool/Python versions, and remaining risks. Link the
durable test evidence. A successful scripted first-phase slice establishes local
contract/recovery behavior, not broad autonomous capability or completion of later
phases. Plans and phase statuses remain untouched under this task's instruction.
