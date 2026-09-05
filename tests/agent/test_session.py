"""End-to-end checks for the phase-one session library."""

from __future__ import annotations

from dataclasses import dataclass

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
from vharness.agent.codec import canonical_json
from vharness.agent.errors import ContractError, IntegrityError, TransitionError
from vharness.agent.journal import SqliteJournal
from vharness.agent.models import ArtifactRef, ExecutionStatus, Pause
from vharness.agent.ports import ReconciliationKind, ReconciliationResult


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
