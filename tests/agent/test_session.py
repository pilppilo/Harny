"""End-to-end checks for the phase-one session library."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib

import pytest

from vharness.agent import (
    ActionDefinition,
    BudgetLimits,
    CompletionMode,
    EnvironmentContract,
    EvaluationReceipt,
    ExecutionReceipt,
    RuntimeCapabilities,
    Session,
    SessionStatus,
    StateRef,
    TaskSpec,
)
from vharness.agent.artifacts import ArtifactStore
from vharness.agent.codec import canonical_json, parse_json_object
from vharness.agent.errors import ContractError, IntegrityError, TransitionError
from vharness.agent.journal import SqliteJournal
from vharness.agent.models import ArtifactRef, Event, ExecutionStatus, Pause
from vharness.agent.ports import ReconciliationKind, ReconciliationResult
from vharness.agent.replay import projection_payload, reduce_event, replay


@dataclass
class FakeEnvironment:
    """A deterministic contract source used without external effects."""

    state: StateRef = StateRef("fake", "initial", digest="0" * 64)

    def describe(self) -> EnvironmentContract:
        return EnvironmentContract(
            environment_id="fake",
            version="1",
            initial_state=self.state,
            actions=(ActionDefinition("inspect", "Inspect current state"),),
            capabilities=RuntimeCapabilities(idempotency=True, reconciliation=True),
        )


class FakeRuntime:
    """Records submitted proposals and returns a configured receipt status."""

    def __init__(self, status: ExecutionStatus = ExecutionStatus.SUCCEEDED) -> None:
        self.status = status
        self.proposals = []
        self.receipts = {}
        self.raise_after_submit = False

    def submit(self, proposal):
        self.proposals.append(proposal)
        receipt = ExecutionReceipt(
            receipt_id=f"receipt-{proposal.proposal_id}",
            proposal_id=proposal.proposal_id,
            objective_version=proposal.objective_version,
            status=self.status,
            state=StateRef("fake", f"after-{proposal.proposal_id}", digest="1" * 64),
        )
        self.receipts[proposal.proposal_id] = receipt
        if self.raise_after_submit:
            raise RuntimeError("transport interrupted after external submit")
        return receipt

    def reconcile(self, operation_id):
        receipt = self.receipts.get(operation_id)
        if receipt is None:
            return ReconciliationResult(ReconciliationKind.UNKNOWN)
        return ReconciliationResult(ReconciliationKind.RECEIPT, receipt)


class FakeEvaluator:
    """Returns external acceptance for the exact request it receives."""

    def __init__(self, accepted: bool = True) -> None:
        self.accepted = accepted
        self.requests = []
        self.evidence = ()
        self.last_receipt = None

    def evaluate(self, request):
        self.requests.append(request)
        receipt = EvaluationReceipt(
            receipt_id=f"evaluation-{request.request_id}",
            request_id=request.request_id,
            objective_version=request.objective_version,
            evaluated_state=request.evaluated_state,
            baseline_node_id=request.baseline_node_id,
            evaluator_version=request.evaluator_version,
            accepted=self.accepted,
            comparison="improved" if self.accepted else "regressed",
            objectives={"score": 1},
            evidence=self.evidence,
        )
        self.last_receipt = receipt
        return receipt


@pytest.fixture
def dependencies(tmp_path):
    journal = SqliteJournal(tmp_path / "session.sqlite3")
    yield journal, ArtifactStore(
        tmp_path / "artifacts"
    ), FakeEnvironment(), FakeRuntime(), FakeEvaluator()
    journal.close()


def _task() -> TaskSpec:
    return TaskSpec(
        task_id="task-1",
        objective="inspect the fixture",
        completion_mode=CompletionMode.FINITE,
        success_evidence="external evaluator acceptance",
        budgets=BudgetLimits(actions=2, evaluations=1),
        environment_id="fake",
        evaluation_contract_id="fake-evaluator-v1",
    )


def test_session_commits_only_externally_accepted_successor_and_replays(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-1",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )

    session.begin_attempt("attempt-1")
    receipt = session.submit_action("inspect", {}, rationale="need an observation")
    session.request_evaluation(receipt.state)

    view = session.view()
    assert view.lineage_head.parent_id == "root-session-1"
    assert view.lineage_head.evaluation_receipt_id is not None
    assert view.active_attempt is None
    assert [event.kind for event in session.events()] == [
        "session_created",
        "attempt_started",
        "action_intended",
        "receipt_received",
        "evaluation_intended",
        "evaluation_intake",
        "evaluation_received",
        "lineage_promoted",
    ]

    reopened = Session.open(
        "session-1",
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    assert reopened.view() == view
    assert runtime.proposals and len(runtime.proposals) == 1


def test_admitted_command_reopens_and_applies_once(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-command",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    command = Pause("pause-1", "session-command")
    assert session.enqueue(command) == "pause-1"
    reopened = Session.open(
        "session-command",
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    assert reopened.advance().status is SessionStatus.PAUSED
    assert reopened.enqueue(command) == "pause-1"
    assert [event.kind for event in reopened.events()].count("session_paused") == 1


def test_second_action_uses_attempt_result_state(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-sequential",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    session.submit_action("inspect", {}, rationale="first")
    session.submit_action("inspect", {}, rationale="second")
    assert (
        runtime.proposals[1].expected_state
        == runtime.receipts[runtime.proposals[0].proposal_id].state
    )


def test_evaluation_intake_is_durable_when_evidence_verification_fails(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    evaluator.evidence = (ArtifactRef("f" * 64, 1, "text/plain", "fixture"),)
    session = Session.create(
        "session-evidence",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    with pytest.raises(IntegrityError, match="missing"):
        session.request_evaluation(receipt.state)
    kinds = [event.kind for event in session.events()]
    assert "evaluation_intake" in kinds
    assert "evaluation_verification_failed" in kinds
    assert "evaluation_received" not in kinds
    intake = next(
        event for event in session.events() if event.kind == "evaluation_intake"
    )
    assert intake.payload["raw_receipt"] == canonical_json(evaluator.last_receipt)
    from vharness.agent.transitions import EvaluationOperationStatus

    assert (
        replay(session.events()).evaluation_operations[0].status
        is EvaluationOperationStatus.VERIFICATION_FAILED
    )
    events = list(session.events())
    repeated_intake = replace(
        intake,
        event_id="event-repeated-failed-intake",
        sequence=len(events) + 1,
    )
    with pytest.raises(IntegrityError, match="follows verification failure"):
        replay([*events, repeated_intake])


def test_action_schema_enforces_declared_properties(dependencies):
    journal, artifacts, _environment, runtime, evaluator = dependencies

    @dataclass
    class StrictEnvironment:
        def describe(self) -> EnvironmentContract:
            return EnvironmentContract(
                environment_id="fake",
                version="1",
                initial_state=StateRef("fake", "initial", digest="0" * 64),
                actions=(
                    ActionDefinition(
                        "inspect",
                        "Inspect current state",
                        {"type": "object", "additionalProperties": False},
                    ),
                ),
                capabilities=RuntimeCapabilities(),
            )

    session = Session.create(
        "session-schema",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=StrictEnvironment(),
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    with pytest.raises(ContractError, match="undeclared"):
        session.submit_action("inspect", {"unexpected": 1}, rationale="invalid")
    assert runtime.proposals == []


def test_action_schema_rejects_unsupported_nested_constructs(dependencies):
    journal, artifacts, _environment, runtime, evaluator = dependencies

    @dataclass
    class UnsupportedSchemaEnvironment:
        def describe(self) -> EnvironmentContract:
            return EnvironmentContract(
                environment_id="fake",
                version="1",
                initial_state=StateRef("fake", "initial", digest="0" * 64),
                actions=(
                    ActionDefinition(
                        "inspect",
                        "Inspect current state",
                        {"properties": {"mode": {"type": "string", "enum": ["x"]}}},
                    ),
                ),
                capabilities=RuntimeCapabilities(),
            )

    session = Session.create(
        "session-nested-schema",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=UnsupportedSchemaEnvironment(),
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    with pytest.raises(ContractError, match="unsupported constructs"):
        session.submit_action("inspect", {}, rationale="invalid schema")
    assert runtime.proposals == []


def test_steering_makes_late_receipts_evidence_without_advancing_new_objective(
    dependencies,
):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.status = ExecutionStatus.ACCEPTED
    session = Session.create(
        "session-2",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    pending = session.submit_action("inspect", {}, rationale="inspect before steering")
    assert session.view().status is SessionStatus.WAITING

    from vharness.agent.models import Steer

    session.enqueue(Steer("steer-1", "session-2", "new objective", "new evidence"))
    session.advance()
    late = ExecutionReceipt(
        receipt_id="late-receipt",
        proposal_id=pending.proposal_id,
        objective_version=1,
        status=ExecutionStatus.SUCCEEDED,
        state=StateRef("fake", "late", digest="2" * 64),
    )
    session.receive_receipt(late)

    view = session.view()
    assert view.task.objective_version == 2
    assert view.lineage_head.node_id == "root-session-2"
    assert view.pending_proposal_id is None
    assert any(event.kind == "receipt_received" for event in session.events())


def test_unknown_reconciliation_never_resubmits_pending_action(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.status = ExecutionStatus.ACCEPTED
    session = Session.create(
        "session-3",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    session.submit_action("inspect", {}, rationale="may be interrupted")
    runtime.receipts.clear()

    reopened = Session.open(
        "session-3",
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    reopened.reconcile_pending()
    assert len(runtime.proposals) == 1
    assert reopened.view().status is SessionStatus.WAITING
    assert "unknown" in (reopened.view().wait_reason or "")


def test_budget_is_reserved_before_runtime_submission(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-4",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    session.submit_action("inspect", {}, rationale="first")
    session.submit_action("inspect", {}, rationale="second")
    with pytest.raises(TransitionError, match="action budget exhausted"):
        session.submit_action("inspect", {}, rationale="third")


def test_rejected_evaluation_remains_attempt_history_without_lineage_promotion(
    dependencies,
):
    journal, artifacts, environment, runtime, evaluator = dependencies
    evaluator.accepted = False
    session = Session.create(
        "session-5",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)

    assert session.view().lineage_head.node_id == "root-session-5"
    assert session.view().active_attempt is not None
    assert session.events()[-1].kind == "evaluation_received"


def test_checkpoint_hashes_the_projection_before_writing_its_marker(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-6",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )

    checkpoint = session.checkpoint()

    assert checkpoint.cursor == 1
    assert len(checkpoint.projection_digest) == 64
    assert session.view().cursor == 2
    assert session.events()[-1].kind == "checkpoint"


def test_replay_rejects_a_checkpoint_with_a_wrong_prefix_digest(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-checkpoint-corrupt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.checkpoint()
    events = list(session.events())
    checkpoint = events[-1]
    corrupted_payload = dict(checkpoint.payload)
    corrupted_checkpoint = dict(corrupted_payload["checkpoint"])
    corrupted_checkpoint["projection_digest"] = "0" * 64
    corrupted_payload["checkpoint"] = corrupted_checkpoint
    events[-1] = replace(checkpoint, payload=corrupted_payload)
    with pytest.raises(IntegrityError, match="digest"):
        replay(events)


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("wrong_session", "session identity"),
        ("wrong_objective", "objective version"),
        ("missing_pending", "pending operation IDs"),
        ("extra_pending", "pending operation IDs"),
    ],
)
def test_replay_rejects_invalid_checkpoint_envelope(
    dependencies, corruption, message
):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.status = ExecutionStatus.ACCEPTED
    session = Session.create(
        "session-checkpoint-envelope",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    session.submit_action("inspect", {}, rationale="pending operation")
    session.checkpoint()
    events = list(session.events())
    checkpoint = events[-1]
    payload = dict(checkpoint.payload)
    envelope = dict(payload["checkpoint"])
    if corruption == "wrong_session":
        envelope["session_id"] = "forged-session"
    elif corruption == "wrong_objective":
        envelope["objective_version"] = 2
    elif corruption == "missing_pending":
        envelope["pending_operation_ids"] = []
    else:
        envelope["pending_operation_ids"] = [
            *envelope["pending_operation_ids"],
            "forged-operation",
        ]
    payload["checkpoint"] = envelope
    events[-1] = replace(checkpoint, payload=payload)

    with pytest.raises(IntegrityError, match=message):
        replay(events)


def test_checkpoint_digest_covers_operation_and_evaluation_replay_state(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.status = ExecutionStatus.ACCEPTED
    session = Session.create(
        "session-checkpoint-operation-state",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    session.submit_action("inspect", {}, rationale="pending operation")
    session.checkpoint()
    events = list(session.events())
    checkpoint = events[-1]
    from vharness.agent.replay import projection_payload

    projection = dict(projection_payload(session._state))
    projection.pop("action_operations")
    projection.pop("evaluation_operations")
    legacy_digest = hashlib.sha256(canonical_json(projection).encode()).hexdigest()
    payload = dict(checkpoint.payload)
    checkpoint_data = dict(payload["checkpoint"])
    checkpoint_data["projection_digest"] = legacy_digest
    payload["checkpoint"] = checkpoint_data
    events[-1] = replace(checkpoint, payload=payload)
    with pytest.raises(IntegrityError, match="digest"):
        replay(events)


def test_replay_rejects_an_intake_with_mismatched_receipt_identity(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-intake-identity",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())
    intake_index = next(
        index for index, event in enumerate(events) if event.kind == "evaluation_intake"
    )
    payload = dict(events[intake_index].payload)
    payload["receipt_id"] = "forged-receipt"
    events[intake_index] = replace(events[intake_index], payload=payload)
    with pytest.raises(IntegrityError, match="receipt identity"):
        replay(events)


def test_duplicate_receipts_are_idempotent_but_conflicting_reuse_is_rejected(
    dependencies,
):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-7",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="deduplicate receipt")
    cursor = session.view().cursor

    assert session.receive_receipt(receipt).cursor == cursor
    conflicting = ExecutionReceipt(
        receipt_id=receipt.receipt_id,
        proposal_id=receipt.proposal_id,
        objective_version=receipt.objective_version,
        status=ExecutionStatus.FAILED,
    )
    with pytest.raises(ContractError, match="different content"):
        session.receive_receipt(conflicting)


def test_reopen_reconciles_submit_interruption_without_duplicate_effect(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.raise_after_submit = True
    session = Session.create(
        "session-8",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    with pytest.raises(RuntimeError, match="transport interrupted"):
        session.submit_action("inspect", {}, rationale="recover interrupted submit")

    runtime.raise_after_submit = False
    reopened = Session.open(
        "session-8",
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    reopened.reconcile_pending()

    assert len(runtime.proposals) == 1
    assert reopened.view().pending_proposal_id is None
    assert reopened.events()[-1].kind == "receipt_received"


def test_event_contract_has_no_authoritative_projection_snapshot(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-event-contract",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt("attempt-contract")
    assert all("snapshot" not in event.payload for event in session.events())


def test_replay_rejects_invalid_command_causation(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-causation-corrupt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.enqueue(Pause("pause-causation", "session-causation-corrupt"))
    session.advance()
    events = list(session.events())
    paused = next(event for event in events if event.kind == "session_paused")
    events[events.index(paused)] = replace(paused, causation_id="wrong-command")
    with pytest.raises(IntegrityError, match="causation"):
        replay(events)


def test_replay_rejects_illegal_command_transition(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-command-transition-corrupt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    pause = Pause("pause-transition", "session-command-transition-corrupt")
    session.enqueue(pause)
    session.advance()
    events = list(session.events())
    paused = next(event for event in events if event.kind == "session_paused")
    repeated = replace(paused, event_id="event-second-pause", sequence=len(events) + 1)
    with pytest.raises(IntegrityError, match="legal command transition"):
        replay([*events, repeated])


def test_replay_rejects_illegal_attempt_and_objective_transitions(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-transition-corrupt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt("attempt-transition")
    events = list(session.events())
    repeated = replace(events[-1], event_id="event-repeated", sequence=3)
    with pytest.raises(IntegrityError, match="attempt_started"):
        replay([*events, repeated])
    from vharness.agent.models import Steer

    session.enqueue(
        Steer(
            "steer-transition",
            "session-transition-corrupt",
            "new objective",
            "new evidence",
        )
    )
    session.advance()
    steered_events = list(session.events())
    regressed = replace(steered_events[-1], objective_version=1)
    with pytest.raises(IntegrityError, match="regresses"):
        replay([*steered_events[:-1], regressed])


def test_replay_rejects_invalid_lineage_parent(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-lineage-corrupt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())
    promoted = events[-1]
    payload = dict(promoted.payload)
    node = dict(payload["node"])
    node["parent_id"] = "wrong-parent"
    payload["node"] = node
    events[-1] = replace(promoted, payload=payload)
    with pytest.raises(IntegrityError, match="not derived"):
        replay(events)


def test_late_receipt_for_promoted_attempt_does_not_change_new_attempt(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    runtime.status = ExecutionStatus.ACCEPTED
    session = Session.create(
        "session-late-attempt",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt("attempt-a")
    pending = session.submit_action("inspect", {}, rationale="candidate")
    terminal = ExecutionReceipt(
        "receipt-a-terminal",
        pending.proposal_id,
        1,
        ExecutionStatus.SUCCEEDED,
        state=StateRef("fake", "a-result", digest="2" * 64),
    )
    session.receive_receipt(terminal)
    session.request_evaluation(terminal.state)
    session.begin_attempt("attempt-b")
    session.receive_receipt(
        ExecutionReceipt(
            "receipt-a-late",
            pending.proposal_id,
            1,
            ExecutionStatus.SUCCEEDED,
            state=StateRef("fake", "a-late-result", digest="3" * 64),
        )
    )

    assert session.view().active_attempt is not None
    assert session.view().active_attempt.attempt_id == "attempt-b"
    assert session.view().active_attempt.result_state is None
    reopened = Session.open(
        "session-late-attempt",
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    assert reopened.view() == session.view()


def test_replay_rejects_promotion_without_matching_evaluation(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-promotion-missing-evaluation",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())
    promoted = events[-1]
    receipt_event_index = next(
        index for index, event in enumerate(events) if event.kind == "receipt_received"
    )
    forged = replace(promoted, sequence=receipt_event_index + 2)
    with pytest.raises(IntegrityError, match="durably verified|matching accepted"):
        replay([*events[: receipt_event_index + 1], forged])


@pytest.mark.parametrize(
    ("field", "value", "disposition"),
    [
        ("accepted", False, "rejected"),
        ("comparison", "incomparable", "incomparable"),
        ("evaluator_version", "other-evaluator", "stale"),
    ],
)
def test_replay_rejects_nonpromotable_evaluation(
    dependencies, field, value, disposition
):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        f"session-promotion-{disposition}",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())
    evaluation_index = next(
        index for index, event in enumerate(events) if event.kind == "evaluation_received"
    )
    payload = dict(events[evaluation_index].payload)
    evaluation_receipt = dict(payload["receipt"])
    evaluation_receipt[field] = value
    payload["receipt"] = evaluation_receipt
    payload["disposition"] = disposition
    events[evaluation_index] = replace(events[evaluation_index], payload=payload)
    with pytest.raises(IntegrityError, match="durably verified|matching accepted"):
        replay(events)


def test_replay_rejects_forged_promotion_receipt_state_and_status(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-promotion-forged-fields",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt()
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())
    promoted = events[-1]
    payload = dict(promoted.payload)
    payload["evaluation_receipt_id"] = "missing-receipt"
    events[-1] = replace(promoted, payload=payload)
    with pytest.raises(IntegrityError, match="receipt identity"):
        replay(events)

    payload = dict(promoted.payload)
    node = dict(payload["node"])
    node["state"] = {"owner": "fake", "value": "forged"}
    payload["node"] = node
    events[-1] = replace(promoted, payload=payload)
    with pytest.raises(IntegrityError, match="not derived"):
        replay(events)

    payload = dict(promoted.payload)
    payload["status"] = "completed"
    events[-1] = replace(promoted, payload=payload)
    with pytest.raises(IntegrityError, match="unexpected or missing"):
        replay(events)


def test_replay_rejects_self_asserted_correlation_fields(dependencies):
    journal, artifacts, environment, runtime, evaluator = dependencies
    session = Session.create(
        "session-forged-correlation",
        _task(),
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt("attempt-a")
    receipt = session.submit_action("inspect", {}, rationale="candidate")
    session.request_evaluation(receipt.state)
    events = list(session.events())

    receipt_index = next(
        index for index, event in enumerate(events) if event.kind == "receipt_received"
    )
    payload = dict(events[receipt_index].payload)
    payload["operation"] = {"attempt_id": "forged"}
    events[receipt_index] = replace(events[receipt_index], payload=payload)
    with pytest.raises(IntegrityError, match="unexpected or missing"):
        replay(events)

    events = list(session.events())
    evaluation_index = next(
        index for index, event in enumerate(events) if event.kind == "evaluation_received"
    )
    payload = dict(events[evaluation_index].payload)
    payload["request"] = {"request_id": "forged"}
    events[evaluation_index] = replace(events[evaluation_index], payload=payload)
    with pytest.raises(IntegrityError, match="unexpected or missing"):
        replay(events)


def _append_event(
    events, kind, payload, *, objective_version=None, causation_id=None
):
    return [
        *events,
        replace(
            events[-1],
            event_id=f"event-{kind}-{len(events) + 1}",
            sequence=len(events) + 1,
            kind=kind,
            objective_version=(
                events[-1].objective_version
                if objective_version is None
                else objective_version
            ),
            payload=payload,
            causation_id=causation_id,
        ),
    ]


def _evaluation_a_intake_prefix(dependencies, *, evaluations=1):
    journal, artifacts, environment, runtime, evaluator = dependencies
    task = replace(_task(), budgets=BudgetLimits(actions=2, evaluations=evaluations))
    session = Session.create(
        f"session-evaluation-lifecycle-{evaluations}",
        task,
        journal=journal,
        artifacts=artifacts,
        environment=environment,
        runtime=runtime,
        evaluator=evaluator,
    )
    session.begin_attempt("attempt-a")
    action = session.submit_action("inspect", {}, rationale="candidate a")
    session.request_evaluation(action.state)
    events = list(session.events())
    intake_index = next(
        index for index, event in enumerate(events) if event.kind == "evaluation_intake"
    )
    received = next(event for event in events if event.kind == "evaluation_received")
    stale_receipt = dict(received.payload["receipt"])
    stale_receipt["evaluator_version"] = "stale-evaluator"
    intake = events[intake_index]
    intake_payload = dict(intake.payload)
    intake_payload["raw_receipt"] = canonical_json(stale_receipt)
    events[intake_index] = replace(intake, payload=intake_payload)
    return events[: intake_index + 1], stale_receipt


def _newer_pending_event(events, kind):
    from vharness.agent.models import Steer
    from vharness.agent.transitions import start_attempt

    steer = Steer(
        "steer-a-to-b",
        events[0].session_id,
        "objective b",
        "evidence b",
    )
    events = _append_event(
        events,
        "objective_steered",
        {"command": parse_json_object(canonical_json(steer))},
        objective_version=2,
        causation_id=steer.command_id,
    )
    attempt = start_attempt(replay(events), "attempt-b")
    events = _append_event(
        events,
        "attempt_started",
        {"attempt": parse_json_object(canonical_json(attempt.active_attempt))},
        objective_version=2,
    )
    if kind == "action":
        template = next(event for event in events if event.kind == "action_intended")
        proposal = dict(template.payload["proposal"])
        reservation = dict(template.payload["reservation"])
        proposal["proposal_id"] = "proposal-b"
        proposal["attempt_id"] = "attempt-b"
        proposal["objective_version"] = 2
        reservation["reservation_id"] = "reservation-b"
        reservation["operation_id"] = "proposal-b"
        reservation["objective_version"] = 2
        return _append_event(
            events,
            "action_intended",
            {"proposal": proposal, "reservation": reservation},
            objective_version=2,
        )
    template = next(event for event in events if event.kind == "evaluation_intended")
    request = dict(template.payload["request"])
    reservation = dict(template.payload["reservation"])
    request["request_id"] = "evaluation-b"
    request["attempt_id"] = "attempt-b"
    request["objective_version"] = 2
    reservation["reservation_id"] = "reservation-b"
    reservation["operation_id"] = "evaluation-b"
    reservation["objective_version"] = 2
    return _append_event(
        events,
        "evaluation_intended",
        {"request": request, "reservation": reservation},
        objective_version=2,
    )


def _late_a_receipt(events, receipt):
    return _append_event(
        events,
        "evaluation_received",
        {"receipt": receipt, "disposition": "stale"},
        objective_version=1,
    )


@pytest.mark.parametrize("pending_kind", ["action", "evaluation"])
def test_late_stale_evaluation_preserves_newer_pending_work(dependencies, pending_kind):
    prefix, stale_receipt = _evaluation_a_intake_prefix(
        dependencies, evaluations=2 if pending_kind == "evaluation" else 1
    )
    with_pending = _newer_pending_event(prefix, pending_kind)
    before = replay(with_pending)
    result = replay(_late_a_receipt(with_pending, stale_receipt))

    assert result.pending_proposal_id == before.pending_proposal_id
    assert result.wait_reason == before.wait_reason
    assert result.status is before.status
    assert result.evaluation_operations[0].status.value == "receipt_consumed"


@pytest.mark.parametrize("duplicate_kind", ["intake", "receipt"])
def test_duplicate_terminal_evaluation_evidence_is_rejected_without_side_effects(
    dependencies, duplicate_kind
):
    prefix, stale_receipt = _evaluation_a_intake_prefix(dependencies)
    with_pending = _newer_pending_event(prefix, "action")
    consumed = _late_a_receipt(with_pending, stale_receipt)
    state = replay(consumed)
    duplicate = (
        prefix[-1]
        if duplicate_kind == "intake"
        else consumed[-1]
    )
    duplicate = replace(
        duplicate,
        event_id=f"event-duplicate-{duplicate_kind}",
        sequence=len(consumed) + 1,
    )

    with pytest.raises(IntegrityError, match="consumed receipt|already terminal"):
        reduce_event(state, duplicate)
    with pytest.raises(IntegrityError, match="consumed receipt|already terminal"):
        replay([*consumed, duplicate])
    assert replay(consumed).pending_proposal_id == state.pending_proposal_id
    assert replay(consumed).wait_reason == state.wait_reason
    assert replay(consumed).status is state.status
    assert replay(consumed).ledger == state.ledger


def _lifecycle_events(dependencies, lifecycle):
    prefix, receipt = _evaluation_a_intake_prefix(dependencies)
    if lifecycle == "intended":
        return prefix[:-1]
    if lifecycle == "intake_recorded":
        return prefix
    if lifecycle == "verification_failed":
        return _append_event(
            prefix,
            "evaluation_verification_failed",
            {
                "request_id": prefix[-1].payload["request_id"],
                "receipt_id": prefix[-1].payload["receipt_id"],
                "reason": "artifact missing",
            },
        )
    return _late_a_receipt(prefix, receipt)


@pytest.mark.parametrize(
    "lifecycle",
    ["intended", "intake_recorded", "verification_failed", "receipt_consumed"],
)
def test_open_reconstructs_each_evaluation_lifecycle(dependencies, tmp_path, lifecycle):
    journal, artifacts, environment, runtime, evaluator = dependencies
    events = _lifecycle_events(dependencies, lifecycle)
    reopened_journal = SqliteJournal(tmp_path / f"{lifecycle}.sqlite3")
    try:
        reopened_journal.append(events, expected_cursor=0)
        opened = Session.open(
            events[0].session_id,
            journal=reopened_journal,
            artifacts=artifacts,
            environment=environment,
            runtime=runtime,
            evaluator=evaluator,
        )
        assert opened._state == replay(events)
    finally:
        reopened_journal.close()
        journal.close()


def test_verification_failure_clears_its_own_wait_and_preserves_terminal_statuses(
    dependencies,
):
    from vharness.agent.transitions import fail_evaluation_verification

    prefix, _receipt = _evaluation_a_intake_prefix(dependencies)
    intake = replay(prefix)
    request_id = prefix[-1].payload["request_id"]
    receipt_id = prefix[-1].payload["receipt_id"]
    cleared = fail_evaluation_verification(intake, request_id, receipt_id)
    assert cleared.pending_proposal_id is None
    assert cleared.wait_reason is None
    assert cleared.status is SessionStatus.RUNNING
    for status in (SessionStatus.PAUSED, SessionStatus.STOPPED):
        terminal = fail_evaluation_verification(
            replace(intake, status=status), request_id, receipt_id
        )
        assert terminal.status is status
        assert terminal.pending_proposal_id is None


@pytest.mark.parametrize("lifecycle", ["verification_failed", "receipt_consumed"])
def test_checkpoint_digest_covers_each_terminal_evaluation_branch(
    dependencies, lifecycle
):
    events = _lifecycle_events(dependencies, lifecycle)
    terminal_state = replay(events)
    before_terminal = replay(events[:-1])
    digest = hashlib.sha256(canonical_json(projection_payload(terminal_state)).encode()).hexdigest()
    checkpoint = _append_event(
        events,
        "checkpoint",
        {
            "checkpoint": {
                "checkpoint_id": f"checkpoint-{lifecycle}",
                "session_id": events[0].session_id,
                "objective_version": 1,
                "cursor": len(events),
                "projection_digest": digest,
                "pending_operation_ids": [],
            }
        },
    )

    assert digest != hashlib.sha256(
        canonical_json(projection_payload(before_terminal)).encode()
    ).hexdigest()
    assert replay(checkpoint) == terminal_state
    corrupted = list(checkpoint)
    if lifecycle == "verification_failed":
        corrupted[-2] = replace(
            corrupted[-2],
            kind="evaluation_received",
            payload={
                "receipt": parse_json_object(events[-2].payload["raw_receipt"]),
                "disposition": "stale",
            },
        )
    else:
        intake = events[-2]
        corrupted[-2] = replace(
            corrupted[-2],
            kind="evaluation_verification_failed",
            payload={
                "request_id": intake.payload["request_id"],
                "receipt_id": intake.payload["receipt_id"],
                "reason": "corrupted",
            },
        )
    with pytest.raises(IntegrityError, match="digest"):
        replay(corrupted)
