"""Validated decoding of session projection payloads at the persistence boundary."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .errors import IntegrityError
from .models import (
    Attempt,
    AttemptDisposition,
    BudgetLimits,
    CommittedNode,
    CompletionMode,
    ExecutionReceipt,
    ExecutionStatus,
    ResourceReservation,
    SessionStatus,
    StateRef,
    TaskSpec,
    UsageMeasurement,
)
from .transitions import SessionState, UsageLedger


def state_from_snapshot(value: Mapping[str, object]) -> SessionState:
    """Decode a persisted projection using strict primitive checks."""
    task_data = _mapping(value, "task")
    budgets = _mapping(task_data, "budgets")
    task = TaskSpec(
        _string(task_data, "task_id"),
        _string(task_data, "objective"),
        CompletionMode(_string(task_data, "completion_mode")),
        _string(task_data, "success_evidence"),
        BudgetLimits(
            actions=_optional_int(budgets, "actions"),
            model_calls=_optional_int(budgets, "model_calls"),
            evaluations=_optional_int(budgets, "evaluations"),
            cost=_optional_decimal(budgets, "cost"),
        ),
        _string(task_data, "environment_id"),
        _string(task_data, "evaluation_contract_id"),
        _integer(task_data, "objective_version"),
        tuple(_strings(task_data.get("constraints", []), "constraints")),
    )
    node = _node_from(_mapping(value, "lineage_head"))
    active_value = value.get("active_attempt")
    active = (
        None
        if active_value is None
        else _attempt_from(_mapping_value(active_value, "active_attempt"))
    )
    ledger_data = _mapping(value, "ledger")
    return SessionState(
        task,
        SessionStatus(_string(value, "status")),
        node,
        active,
        _optional_string(value, "pending_proposal_id"),
        _optional_string(value, "wait_reason"),
        UsageLedger(
            _integer(ledger_data, "actions"),
            _integer(ledger_data, "evaluations"),
            _decimal(ledger_data, "cost"),
            _optional_decimal(ledger_data, "unsettled_cost"),
        ),
    )


def reservation_from_payload(value: Mapping[str, object]) -> ResourceReservation:
    """Decode a durable operation reservation."""
    return ResourceReservation(
        _string(value, "reservation_id"),
        _string(value, "operation_id"),
        _integer(value, "objective_version"),
        _integer(value, "actions"),
        _integer(value, "evaluations"),
        _optional_decimal(value, "cost"),
    )


def receipt_from_payload(value: Mapping[str, object]) -> ExecutionReceipt:
    """Decode one durable runtime receipt."""
    state = value.get("state")
    usage = value.get("usage")
    return ExecutionReceipt(
        _string(value, "receipt_id"),
        _string(value, "proposal_id"),
        _integer(value, "objective_version"),
        ExecutionStatus(_string(value, "status")),
        _optional_string(value, "operation_id"),
        None if state is None else state_ref_from(_mapping_value(state, "state")),
        _optional_string(value, "error"),
        None if usage is None else usage_from_payload(_mapping_value(usage, "usage")),
    )


def state_ref_from(value: Mapping[str, object]) -> StateRef:
    """Decode an opaque external state reference."""
    restorable = value.get("restorable", False)
    if not isinstance(restorable, bool):
        raise IntegrityError("snapshot restorable must be a boolean")
    return StateRef(
        _string(value, "owner"),
        _string(value, "value"),
        _optional_string(value, "digest"),
        _optional_string(value, "revision"),
        restorable,
    )


def usage_from_payload(value: Mapping[str, object]) -> UsageMeasurement:
    """Decode measured external resource consumption."""
    return UsageMeasurement(
        _string(value, "measurement_id"),
        _integer(value, "actions"),
        _integer(value, "model_calls"),
        _integer(value, "evaluations"),
        _optional_decimal(value, "cost"),
    )


def _node_from(value: Mapping[str, object]) -> CommittedNode:
    return CommittedNode(
        _string(value, "node_id"),
        _integer(value, "objective_version"),
        state_ref_from(_mapping(value, "state")),
        _optional_string(value, "parent_id"),
        _optional_string(value, "evaluation_receipt_id"),
        _mapping_or_empty(value, "objectives"),
    )


def _attempt_from(value: Mapping[str, object]) -> Attempt:
    result = value.get("result_state")
    return Attempt(
        _string(value, "attempt_id"),
        _integer(value, "objective_version"),
        _string(value, "base_node_id"),
        state_ref_from(_mapping(value, "starting_state")),
        AttemptDisposition(_string(value, "disposition")),
        (
            None
            if result is None
            else state_ref_from(_mapping_value(result, "result_state"))
        ),
    )


def _mapping(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    """Extract one required JSON object."""
    return _mapping_value(value.get(name), name)


def _mapping_value(value: object, name: str) -> Mapping[str, object]:
    """Validate a JSON object from an untyped persisted payload."""
    if not isinstance(value, Mapping):
        raise IntegrityError(f"snapshot {name} must be an object")
    return value


def _mapping_or_empty(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    """Extract an optional JSON object using an empty default."""
    return _mapping_value(value.get(name, {}), name)


def _string(value: Mapping[str, object], name: str) -> str:
    """Extract a required string without coercion."""
    candidate = value.get(name)
    if not isinstance(candidate, str):
        raise IntegrityError(f"snapshot {name} must be a string")
    return candidate


def _optional_string(value: Mapping[str, object], name: str) -> str | None:
    candidate = value.get(name)
    if candidate is not None and not isinstance(candidate, str):
        raise IntegrityError(f"snapshot {name} must be a string or null")
    return candidate


def _integer(value: Mapping[str, object], name: str) -> int:
    candidate = value.get(name)
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise IntegrityError(f"snapshot {name} must be an integer")
    return candidate


def _optional_int(value: Mapping[str, object], name: str) -> int | None:
    candidate = value.get(name)
    return None if candidate is None else _integer(value, name)


def _decimal(value: Mapping[str, object], name: str) -> Decimal:
    return _parse_decimal(_string(value, name), name)


def _optional_decimal(value: Mapping[str, object], name: str) -> Decimal | None:
    candidate = value.get(name)
    return None if candidate is None else _parse_decimal(_string(value, name), name)


def _parse_decimal(value: str, name: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise IntegrityError(f"snapshot {name} must be a decimal string") from exc


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise IntegrityError(f"snapshot {name} must be an array of strings")
    return tuple(value)
