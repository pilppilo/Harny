"""Pure session transition checks and resource accounting."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum

from .errors import TransitionError
from .models import (
    Attempt,
    AttemptDisposition,
    BudgetLimits,
    CommittedNode,
    EvaluationReceipt,
    EvaluationRequest,
    PromotionDisposition,
    ResourceReservation,
    SessionStatus,
    TaskSpec,
    UsageMeasurement,
)


@dataclass(frozen=True, slots=True)
class UsageLedger:
    """Known usage and unsettled reserved exposure for scheduling decisions."""

    actions: int = 0
    evaluations: int = 0
    cost: Decimal = Decimal("0")
    unsettled_cost: Decimal | None = Decimal("0")

    def reserve(
        self, reservation: ResourceReservation, limits: BudgetLimits
    ) -> "UsageLedger":
        """Refuse a reservation that exceeds a configured known resource limit."""
        if (
            limits.actions is not None
            and self.actions + reservation.actions > limits.actions
        ):
            raise TransitionError("action budget exhausted")
        if (
            limits.evaluations is not None
            and self.evaluations + reservation.evaluations > limits.evaluations
        ):
            raise TransitionError("evaluation budget exhausted")
        if limits.cost is not None:
            if reservation.cost is None or self.unsettled_cost is None:
                raise TransitionError("cost budget requires a known reservation bound")
            if self.cost + self.unsettled_cost + reservation.cost > limits.cost:
                raise TransitionError("cost budget exhausted")
        unsettled = (
            None
            if self.unsettled_cost is None or reservation.cost is None
            else self.unsettled_cost + reservation.cost
        )

        return replace(
            self,
            actions=self.actions + reservation.actions,
            evaluations=self.evaluations + reservation.evaluations,
            unsettled_cost=unsettled,
        )

    def settle(
        self, reservation: ResourceReservation, measurement: UsageMeasurement | None
    ) -> "UsageLedger":
        """Replace a reservation's cost exposure with measured cost when available."""
        if measurement is None or measurement.cost is None or reservation.cost is None:
            return replace(self, unsettled_cost=None)
        if self.unsettled_cost is None:
            return self
        return replace(
            self,
            cost=self.cost + measurement.cost,
            unsettled_cost=max(Decimal("0"), self.unsettled_cost - reservation.cost),
        )


class EvaluationOperationStatus(str, Enum):
    """Monotonic lifecycle of one externally requested evaluation."""

    INTENDED = "intended"
    INTAKE_RECORDED = "intake_recorded"
    VERIFICATION_FAILED = "verification_failed"
    RECEIPT_CONSUMED = "receipt_consumed"


@dataclass(frozen=True, slots=True)
class EvaluationOperation:
    """Replay-owned facts for one evaluation request and its terminal handling."""

    request: EvaluationRequest
    reservation: ResourceReservation
    status: EvaluationOperationStatus = EvaluationOperationStatus.INTENDED
    receipt_id: str | None = None
    raw_receipt: str | None = None


# The projection intentionally holds each scheduling fact needed by replay.
# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True, slots=True)
class SessionState:
    """Small rebuildable projection needed for phase-one scheduling."""

    task: TaskSpec
    status: SessionStatus
    lineage_head: CommittedNode
    active_attempt: Attempt | None = None
    pending_proposal_id: str | None = None
    wait_reason: str | None = None
    ledger: UsageLedger = UsageLedger()
    action_operations: tuple[tuple[str, str, int, ResourceReservation, bool], ...] = ()
    evaluation_operations: tuple[EvaluationOperation, ...] = ()
    latest_evaluation: (
        tuple[EvaluationRequest, EvaluationReceipt, PromotionDisposition] | None
    ) = None


def start_attempt(state: SessionState, attempt_id: str) -> SessionState:
    """Start a new trajectory from the current committed lineage node."""
    if state.active_attempt is not None:
        raise TransitionError("an attempt is already active")
    if state.status not in (SessionStatus.CREATED, SessionStatus.RUNNING):
        raise TransitionError(
            f"cannot start an attempt while session is {state.status.value}"
        )
    attempt = Attempt(
        attempt_id=attempt_id,
        objective_version=state.task.objective_version,
        base_node_id=state.lineage_head.node_id,
        starting_state=state.lineage_head.state,
    )
    return replace(state, status=SessionStatus.RUNNING, active_attempt=attempt)


def intend_action(
    state: SessionState,
    proposal_id: str,
    attempt_id: str,
    reservation: ResourceReservation,
) -> SessionState:
    """Reserve and record an action owned by the current active attempt."""
    if state.active_attempt is None or state.active_attempt.attempt_id != attempt_id:
        raise TransitionError("action does not belong to the active attempt")
    if reservation.operation_id != proposal_id:
        raise TransitionError("action reservation does not match proposal")
    ledger = state.ledger.reserve(reservation, state.task.budgets)
    return replace(
        state,
        status=SessionStatus.WAITING,
        pending_proposal_id=proposal_id,
        wait_reason="runtime receipt pending",
        ledger=ledger,
        action_operations=(
            *state.action_operations,
            (proposal_id, attempt_id, state.task.objective_version, reservation, False),
        ),
    )


def intend_evaluation(
    state: SessionState, request: EvaluationRequest, reservation: ResourceReservation
) -> SessionState:
    """Reserve and register one evaluation before external dispatch."""
    if (
        state.active_attempt is None
        or state.active_attempt.attempt_id != request.attempt_id
    ):
        raise TransitionError("evaluation does not belong to the active attempt")
    if reservation.operation_id != request.request_id:
        raise TransitionError("evaluation reservation does not match request")
    if any(
        operation.request.request_id == request.request_id
        for operation in state.evaluation_operations
    ):
        raise TransitionError("evaluation request ID is already recorded")
    ledger = state.ledger.reserve(reservation, state.task.budgets)
    return replace(
        state,
        status=SessionStatus.WAITING,
        pending_proposal_id=request.request_id,
        wait_reason="evaluation pending",
        ledger=ledger,
        evaluation_operations=(
            *state.evaluation_operations,
            EvaluationOperation(request, reservation),
        ),
    )


def record_evaluation_intake(
    state: SessionState, request_id: str, receipt_id: str, raw_receipt: str
) -> SessionState:
    """Record verified raw intake exactly once for its intended evaluation."""
    operation = _evaluation_operation(state, request_id)
    _require_new_intake(operation)
    updated = replace(
        operation,
        status=EvaluationOperationStatus.INTAKE_RECORDED,
        receipt_id=receipt_id,
        raw_receipt=raw_receipt,
    )
    return replace(state, evaluation_operations=_replace_evaluation(state, updated))


def fail_evaluation_verification(
    state: SessionState, request_id: str, receipt_id: str
) -> SessionState:
    """Make an evidence-verification failure terminal for that evaluation."""
    operation = _evaluation_operation(state, request_id)
    if operation.receipt_id != receipt_id:
        raise TransitionError("evaluation verification failure has no active intake")
    _require_consumable(operation)
    return _terminalize_evaluation(
        state, operation, EvaluationOperationStatus.VERIFICATION_FAILED
    )


def consume_evaluation(
    state: SessionState,
    receipt: EvaluationReceipt,
    disposition: PromotionDisposition,
) -> SessionState:
    """Consume an intake once, preserving late evidence without clearing other work."""
    operation = _evaluation_operation(state, receipt.request_id)
    if operation.receipt_id != receipt.receipt_id:
        raise TransitionError("evaluation receipt does not match its verified intake")
    _require_consumable(operation)
    result = _terminalize_evaluation(
        state, operation, EvaluationOperationStatus.RECEIPT_CONSUMED
    )
    return replace(
        result,
        latest_evaluation=(operation.request, receipt, disposition),
    )


def evaluation_operation(state: SessionState, request_id: str) -> EvaluationOperation:
    """Return one intended evaluation or reject an unknown request ID."""
    return _evaluation_operation(state, request_id)


def _evaluation_operation(state: SessionState, request_id: str) -> EvaluationOperation:
    for operation in state.evaluation_operations:
        if operation.request.request_id == request_id:
            return operation
    raise TransitionError("evaluation does not link to an intended operation")


def _terminalize_evaluation(
    state: SessionState,
    operation: EvaluationOperation,
    terminal_status: EvaluationOperationStatus,
) -> SessionState:
    updated = replace(operation, status=terminal_status)
    result = replace(
        state,
        evaluation_operations=_replace_evaluation(state, updated),
        ledger=state.ledger.settle(operation.reservation, None),
    )
    if state.pending_proposal_id != operation.request.request_id:
        return result
    status = (
        SessionStatus.RUNNING if state.status is SessionStatus.WAITING else state.status
    )
    return replace(result, status=status, pending_proposal_id=None, wait_reason=None)


def _require_new_intake(operation: EvaluationOperation) -> None:
    if operation.status is EvaluationOperationStatus.VERIFICATION_FAILED:
        raise TransitionError("evaluation intake follows verification failure")
    if operation.status is EvaluationOperationStatus.RECEIPT_CONSUMED:
        raise TransitionError("evaluation intake follows consumed receipt")
    if operation.status is EvaluationOperationStatus.INTAKE_RECORDED:
        raise TransitionError("evaluation intake is already recorded")


def _require_consumable(operation: EvaluationOperation) -> None:
    if operation.status in {
        EvaluationOperationStatus.VERIFICATION_FAILED,
        EvaluationOperationStatus.RECEIPT_CONSUMED,
    }:
        raise TransitionError("evaluation receipt is already terminal")
    if operation.status is not EvaluationOperationStatus.INTAKE_RECORDED:
        raise TransitionError("evaluation receipt has no verified intake")


def _replace_evaluation(
    state: SessionState, updated: EvaluationOperation
) -> tuple[EvaluationOperation, ...]:
    return tuple(
        (
            updated
            if operation.request.request_id == updated.request.request_id
            else operation
        )
        for operation in state.evaluation_operations
    )


def apply_steer(
    state: SessionState, objective: str, success_evidence: str
) -> SessionState:
    """Version task intent and close old active work without rewriting its history."""
    old_attempt = state.active_attempt
    if old_attempt is not None:
        old_attempt = replace(old_attempt, disposition=AttemptDisposition.ABANDONED)
    return replace(
        state,
        task=state.task.steered(objective, success_evidence),
        status=SessionStatus.RUNNING,
        active_attempt=None,
        pending_proposal_id=None,
        wait_reason=None,
    )


def promotion_disposition(
    state: SessionState, request: EvaluationRequest, receipt: EvaluationReceipt
) -> PromotionDisposition:
    """Check applicability; external evaluator remains sole score authority."""
    if not receipt.accepted:
        return PromotionDisposition.REJECTED
    if receipt.comparison == "incomparable":
        return PromotionDisposition.INCOMPARABLE
    current = state.task.objective_version
    current_head = state.lineage_head.node_id
    matching = (
        receipt.request_id == request.request_id,
        request.objective_version == current,
        receipt.objective_version == current,
        request.baseline_node_id == current_head,
        receipt.baseline_node_id == current_head,
        request.evaluator_version == receipt.evaluator_version,
        request.evaluated_state == receipt.evaluated_state,
    )
    if not all(matching):
        return PromotionDisposition.STALE
    return PromotionDisposition.ACCEPTED


def promote(
    state: SessionState,
    request: EvaluationRequest,
    receipt: EvaluationReceipt,
    node_id: str,
) -> SessionState:
    """Advance the committed lineage only from an applicable accepted evaluation."""
    if (
        promotion_disposition(state, request, receipt)
        is not PromotionDisposition.ACCEPTED
    ):
        raise TransitionError("evaluation is not applicable for promotion")
    if (
        state.active_attempt is None
        or state.active_attempt.attempt_id != request.attempt_id
    ):
        raise TransitionError(
            "evaluation request does not belong to the active attempt"
        )
    node = CommittedNode(
        node_id=node_id,
        objective_version=state.task.objective_version,
        state=receipt.evaluated_state,
        parent_id=state.lineage_head.node_id,
        evaluation_receipt_id=receipt.receipt_id,
        objectives=receipt.objectives,
    )
    status = (
        SessionStatus.COMPLETED
        if state.task.completion_mode.value == "finite"
        and receipt.comparison == "completed"
        else SessionStatus.RUNNING
    )
    return replace(
        state,
        lineage_head=node,
        active_attempt=None,
        pending_proposal_id=None,
        wait_reason=None,
        status=status,
        latest_evaluation=None,
    )


def record_receipt_state(
    state: SessionState, proposal_id: str, status: str
) -> SessionState:
    """Update only the pending wait projection for a matching receipt."""
    if state.pending_proposal_id != proposal_id:
        return state
    if state.status in (SessionStatus.PAUSED, SessionStatus.STOPPED):
        if status in ("accepted", "running"):
            return state
        return replace(state, pending_proposal_id=None, wait_reason=None)
    if status in ("accepted", "running"):
        return replace(
            state, status=SessionStatus.WAITING, wait_reason="runtime receipt pending"
        )
    return replace(
        state, status=SessionStatus.RUNNING, pending_proposal_id=None, wait_reason=None
    )
