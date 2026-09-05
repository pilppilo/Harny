"""Validated, pure reconstruction of durable session projections."""

# The event-kind reducer intentionally contains the complete phase-one state
# machine. Splitting branches would obscure the single authoritative reducer.
# pylint: disable=too-many-branches,too-many-locals,too-many-return-statements,too-many-statements

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Iterable, Mapping

from .codec import canonical_json, parse_json_object
from .errors import IntegrityError, TransitionError
from .models import (
    Event,
    ExecutionStatus,
    PromotionDisposition,
    ResourceReservation,
    SessionStatus,
)
from .session_state import (
    attempt_from_payload,
    evaluation_receipt_from_payload,
    evaluation_request_from_payload,
    node_from_payload,
    receipt_from_payload,
    reservation_from_payload,
    string_from_payload,
    task_from_payload,
    integer_from_payload,
)
from .transitions import (
    SessionState,
    apply_steer,
    consume_evaluation,
    evaluation_operation,
    fail_evaluation_verification,
    intend_action,
    intend_evaluation,
    promote,
    promotion_disposition,
    record_evaluation_intake,
    record_receipt_state,
    start_attempt,
)


def reduce_event(previous: SessionState | None, event: Event) -> SessionState:
    """Apply one typed durable fact without I/O or a stored projection snapshot."""
    if "snapshot" in event.payload:
        raise IntegrityError(
            "legacy snapshot journal is unsupported; create a new session journal"
        )
    if previous is None:
        return _create_session(event)
    if (
        event.objective_version < previous.task.objective_version
        and event.kind not in _HISTORICAL_EVIDENCE_KINDS
    ):
        raise IntegrityError("event objective version regresses the projection")
    if (
        event.objective_version > previous.task.objective_version
        and event.kind != "objective_steered"
    ):
        raise IntegrityError("only objective_steered may advance objective version")
    return _reduce_existing(previous, event)


def _create_session(event: Event) -> SessionState:
    if event.kind != "session_created":
        raise IntegrityError("the first event must create the session")
    task = task_from_payload(_mapping(event.payload, "task"))
    root = node_from_payload(_mapping(event.payload, "root_node"))
    if event.objective_version != task.objective_version:
        raise IntegrityError("session_created objective version disagrees with task")
    if root.objective_version != task.objective_version or root.parent_id is not None:
        raise IntegrityError("session_created root node is invalid")
    return SessionState(task=task, status=SessionStatus.CREATED, lineage_head=root)


def _reduce_existing(previous: SessionState, event: Event) -> SessionState:
    payload = event.payload
    if event.kind in {"command_admitted", "operator_message"}:
        return previous
    if event.kind in {"command_applied", "command_rejected"}:
        if event.causation_id != string_from_payload(payload, "command_id"):
            raise IntegrityError("command disposition has invalid causation")
        return previous
    if event.kind == "attempt_started":
        attempt = attempt_from_payload(_mapping(payload, "attempt"))
        _same_objective(event, previous)
        try:
            state = start_attempt(previous, attempt.attempt_id)
        except TransitionError as exc:
            raise IntegrityError("attempt_started is not a legal transition") from exc
        if state.active_attempt != attempt:
            raise IntegrityError("attempt_started payload is not the derived attempt")
        return state
    if event.kind == "action_intended":
        _exact_keys(payload, {"proposal", "reservation"})
        proposal = _mapping(payload, "proposal")
        reservation = reservation_from_payload(_mapping(payload, "reservation"))
        _same_objective(event, previous)
        active = previous.active_attempt
        if (
            active is None
            or string_from_payload(proposal, "attempt_id") != active.attempt_id
        ):
            raise IntegrityError(
                "action_intended does not belong to the active attempt"
            )
        proposal_id = string_from_payload(proposal, "proposal_id")
        if (
            reservation.operation_id != proposal_id
            or reservation.objective_version != event.objective_version
        ):
            raise IntegrityError("action_intended operation identity is invalid")
        try:
            return intend_action(previous, proposal_id, active.attempt_id, reservation)
        except TransitionError as exc:
            raise IntegrityError("action_intended exceeds the durable budget") from exc
    if event.kind == "receipt_received":
        _exact_keys(payload, {"receipt"})
        receipt = receipt_from_payload(_mapping(payload, "receipt"))
        operation = _action_operation(previous, receipt.proposal_id)
        _proposal_id, attempt_id, objective_version, reservation, settled = operation
        if receipt.objective_version != objective_version:
            raise IntegrityError("receipt objective version disagrees with operation")
        state = record_receipt_state(
            previous, receipt.proposal_id, receipt.status.value
        )
        active = state.active_attempt
        if (
            receipt.state is not None
            and receipt.status not in _NONTERMINAL
            and active is not None
            and active.objective_version == receipt.objective_version
            and active.attempt_id == attempt_id
        ):
            state = replace(
                state, active_attempt=replace(active, result_state=receipt.state)
            )
        if receipt.status not in _NONTERMINAL and not settled:
            state = replace(
                state, ledger=state.ledger.settle(reservation, receipt.usage)
            )
            state = replace(
                state,
                action_operations=_mark_action_settled(
                    state.action_operations, receipt.proposal_id
                ),
            )
        return state
    if event.kind == "evaluation_intended":
        _exact_keys(payload, {"request", "reservation"})
        request = evaluation_request_from_payload(_mapping(payload, "request"))
        reservation = reservation_from_payload(_mapping(payload, "reservation"))
        _same_objective(event, previous)
        if (
            previous.active_attempt is None
            or request.attempt_id != previous.active_attempt.attempt_id
        ):
            raise IntegrityError(
                "evaluation_intended does not belong to the active attempt"
            )
        if reservation.operation_id != request.request_id:
            raise IntegrityError("evaluation_intended operation identity is invalid")
        try:
            return intend_evaluation(previous, request, reservation)
        except TransitionError as exc:
            raise IntegrityError(
                "evaluation_intended exceeds the durable budget"
            ) from exc
    if event.kind == "evaluation_intake":
        _exact_keys(payload, {"request_id", "receipt_id", "raw_receipt"})
        request_id = string_from_payload(payload, "request_id")
        try:
            operation = evaluation_operation(previous, request_id)
        except TransitionError as exc:
            raise IntegrityError(str(exc)) from exc
        raw_receipt = string_from_payload(payload, "raw_receipt")
        receipt = evaluation_receipt_from_payload(parse_json_object(raw_receipt))
        if raw_receipt != canonical_json(receipt):
            raise IntegrityError("evaluation intake raw receipt is not canonical")
        if (
            receipt.request_id != request_id
            or receipt.receipt_id != string_from_payload(payload, "receipt_id")
        ):
            raise IntegrityError("evaluation intake receipt identity is invalid")
        try:
            return record_evaluation_intake(
                previous, request_id, receipt.receipt_id, raw_receipt
            )
        except TransitionError as exc:
            raise IntegrityError(str(exc)) from exc
    if event.kind == "evaluation_verification_failed":
        _exact_keys(payload, {"request_id", "receipt_id", "reason"})
        try:
            return fail_evaluation_verification(
                previous,
                string_from_payload(payload, "request_id"),
                string_from_payload(payload, "receipt_id"),
            )
        except TransitionError as exc:
            raise IntegrityError(str(exc)) from exc
    if event.kind == "evaluation_received":
        _exact_keys(payload, {"receipt", "disposition"})
        receipt = evaluation_receipt_from_payload(_mapping(payload, "receipt"))
        try:
            operation = evaluation_operation(previous, receipt.request_id)
        except TransitionError as exc:
            raise IntegrityError(str(exc)) from exc
        request, reservation = operation.request, operation.reservation
        if receipt.request_id != reservation.operation_id:
            raise IntegrityError("evaluation receipt does not link to its operation")
        if receipt.objective_version != reservation.objective_version:
            raise IntegrityError(
                "evaluation receipt objective version disagrees with operation"
            )
        if (
            operation.receipt_id != receipt.receipt_id
            or operation.raw_receipt != canonical_json(receipt)
        ):
            raise IntegrityError(
                "evaluation receipt was not durably verified at intake"
            )
        disposition = promotion_disposition(previous, request, receipt)
        if _promotion_disposition(payload) is not disposition:
            raise IntegrityError("evaluation disposition is not derived from its facts")
        try:
            return consume_evaluation(previous, receipt, disposition)
        except TransitionError as exc:
            raise IntegrityError(str(exc)) from exc
    if event.kind == "lineage_promoted":
        _exact_keys(payload, {"node", "evaluation_receipt_id"})
        node = node_from_payload(_mapping(payload, "node"))
        _same_objective(event, previous)
        evaluation = previous.latest_evaluation
        if evaluation is None or evaluation[2] is not PromotionDisposition.ACCEPTED:
            raise IntegrityError(
                "lineage_promoted lacks a matching accepted evaluation"
            )
        request, receipt, _disposition = evaluation
        if string_from_payload(payload, "evaluation_receipt_id") != receipt.receipt_id:
            raise IntegrityError("lineage_promoted receipt identity is invalid")
        try:
            derived = promote(previous, request, receipt, node.node_id)
        except TransitionError as exc:
            raise IntegrityError("lineage_promoted is not applicable") from exc
        if derived.lineage_head != node:
            raise IntegrityError("lineage_promoted node is not derived from evaluation")
        return derived
    if event.kind == "objective_steered":
        command = _mapping(payload, "command")
        _command_causation(event, command)
        state = apply_steer(
            previous,
            string_from_payload(command, "objective"),
            string_from_payload(command, "success_evidence"),
        )
        if event.objective_version != state.task.objective_version:
            raise IntegrityError(
                "objective_steered must advance objective version once"
            )
        return state
    if event.kind == "session_paused":
        _command_causation(event, _mapping(payload, "command"))
        _same_objective(event, previous)
        if previous.status not in {
            SessionStatus.CREATED,
            SessionStatus.RUNNING,
            SessionStatus.WAITING,
        }:
            raise IntegrityError("session_paused is not a legal command transition")
        return replace(previous, status=SessionStatus.PAUSED)
    if event.kind == "session_resumed":
        _command_causation(event, _mapping(payload, "command"))
        _same_objective(event, previous)
        if previous.status is not SessionStatus.PAUSED:
            raise IntegrityError("session_resumed is not a legal command transition")
        return replace(
            previous,
            status=(
                SessionStatus.WAITING
                if previous.pending_proposal_id
                else SessionStatus.RUNNING
            ),
        )
    if event.kind == "session_stopped":
        _command_causation(event, _mapping(payload, "command"))
        _same_objective(event, previous)
        if previous.status in {
            SessionStatus.COMPLETED,
            SessionStatus.FAILED,
            SessionStatus.STOPPED,
        }:
            raise IntegrityError("session_stopped is not a legal command transition")
        return replace(previous, status=SessionStatus.STOPPED)
    if event.kind == "proposal_reconciled":
        _same_objective(event, previous)
        reconciliation = string_from_payload(payload, "result")
        return replace(
            previous,
            status=SessionStatus.WAITING,
            wait_reason=f"runtime reconciliation: {reconciliation}",
        )
    if event.kind == "checkpoint":
        checkpoint = _mapping(payload, "checkpoint")
        string_from_payload(checkpoint, "checkpoint_id")
        if string_from_payload(checkpoint, "session_id") != event.session_id:
            raise IntegrityError("checkpoint session identity is invalid")
        if (
            integer_from_payload(checkpoint, "objective_version")
            != previous.task.objective_version
        ):
            raise IntegrityError("checkpoint objective version is invalid")
        if integer_from_payload(checkpoint, "cursor") != event.sequence - 1:
            raise IntegrityError(
                "checkpoint cursor does not represent its event prefix"
            )
        pending_operation_ids = _string_sequence_from_payload(
            checkpoint, "pending_operation_ids"
        )
        expected_pending = (
            ()
            if previous.pending_proposal_id is None
            else (previous.pending_proposal_id,)
        )
        if pending_operation_ids != expected_pending:
            raise IntegrityError("checkpoint pending operation IDs are invalid")
        expected = hashlib.sha256(
            canonical_json(projection_payload(previous)).encode()
        ).hexdigest()
        if string_from_payload(checkpoint, "projection_digest") != expected:
            raise IntegrityError(
                "checkpoint projection digest does not match its prefix"
            )
        return previous
    raise IntegrityError(f"unknown event kind {event.kind!r}")


_NONTERMINAL = frozenset({ExecutionStatus.ACCEPTED, ExecutionStatus.RUNNING})
_HISTORICAL_EVIDENCE_KINDS = frozenset(
    {
        "receipt_received",
        "evaluation_intake",
        "evaluation_verification_failed",
        "evaluation_received",
    }
)


def projection_payload(state: SessionState) -> Mapping[str, object]:
    """Return the derived projection used only for checkpoint integrity."""
    return {
        "task": state.task,
        "status": state.status,
        "lineage_head": state.lineage_head,
        "active_attempt": state.active_attempt,
        "pending_proposal_id": state.pending_proposal_id,
        "wait_reason": state.wait_reason,
        "ledger": state.ledger,
        "action_operations": state.action_operations,
        "evaluation_operations": state.evaluation_operations,
        "latest_evaluation": state.latest_evaluation,
    }


def replay(events: Iterable[Event]) -> SessionState:
    """Validate sequence and session identity before reducing all event facts."""
    state: SessionState | None = None
    session_id: str | None = None
    sequence = 0
    for event in events:
        if session_id is None:
            session_id = event.session_id
        elif event.session_id != session_id:
            raise IntegrityError("journal stream mixes session identities")
        sequence += 1
        if event.sequence != sequence:
            raise IntegrityError("journal event sequence is not contiguous")
        state = reduce_event(state, event)
    if state is None:
        raise IntegrityError("journal has no events")
    return state


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    candidate = value.get(name)
    if not isinstance(candidate, Mapping):
        raise IntegrityError(f"event payload {name} must be an object")
    return candidate


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> None:
    if set(value) != expected:
        raise IntegrityError("event payload has unexpected or missing fields")


def _string_sequence_from_payload(
    value: Mapping[str, object], name: str
) -> tuple[str, ...]:
    candidate = value.get(name)
    if not isinstance(candidate, (list, tuple)) or not all(
        isinstance(item, str) for item in candidate
    ):
        raise IntegrityError(f"event payload {name} must be an array of strings")
    return tuple(candidate)


def _promotion_disposition(payload: Mapping[str, object]) -> PromotionDisposition:
    try:
        return PromotionDisposition(string_from_payload(payload, "disposition"))
    except ValueError as exc:
        raise IntegrityError("event payload disposition is invalid") from exc


def _action_operation(
    state: SessionState, proposal_id: str
) -> tuple[str, str, int, ResourceReservation, bool]:
    for operation in state.action_operations:
        if operation[0] == proposal_id:
            return operation
    raise IntegrityError("receipt does not link to an intended action")


def _mark_action_settled(
    operations: tuple[tuple[str, str, int, ResourceReservation, bool], ...],
    proposal_id: str,
) -> tuple[tuple[str, str, int, ResourceReservation, bool], ...]:
    return tuple(
        (*operation[:4], True) if operation[0] == proposal_id else operation
        for operation in operations
    )


def _same_objective(event: Event, state: SessionState) -> None:
    if event.objective_version != state.task.objective_version:
        raise IntegrityError("event objective version disagrees with projection")


def _command_causation(event: Event, command: Mapping[str, object]) -> None:
    if event.causation_id != string_from_payload(command, "command_id"):
        raise IntegrityError("control event has invalid command causation")
