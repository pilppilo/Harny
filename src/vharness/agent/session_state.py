"""Validated decoding of session projection payloads at the persistence boundary."""

# One branch per immutable command variant keeps durable command decoding explicit.
# pylint: disable=too-many-return-statements

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Mapping

from .errors import IntegrityError
from .models import (
    ArtifactRef,
    Attempt,
    AttemptDisposition,
    BudgetLimits,
    CommittedNode,
    CompletionMode,
    ExecutionReceipt,
    ExecutionStatus,
    EvaluationCommand,
    EvaluationReceipt,
    EvaluationRequest,
    CheckpointRequest,
    Message,
    OperatorCommand,
    Pause,
    ResourceReservation,
    Resume,
    StateRef,
    Steer,
    Stop,
    TaskSpec,
    UsageMeasurement,
)


def task_from_payload(value: Mapping[str, object]) -> TaskSpec:
    """Decode the task fact carried by session creation."""
    budgets = _mapping(value, "budgets")
    return TaskSpec(
        _string(value, "task_id"),
        _string(value, "objective"),
        CompletionMode(_string(value, "completion_mode")),
        _string(value, "success_evidence"),
        BudgetLimits(
            actions=_optional_int(budgets, "actions"),
            model_calls=_optional_int(budgets, "model_calls"),
            evaluations=_optional_int(budgets, "evaluations"),
            cost=_optional_decimal(budgets, "cost"),
        ),
        _string(value, "environment_id"),
        _string(value, "evaluation_contract_id"),
        _integer(value, "objective_version"),
        tuple(_strings(value.get("constraints", []), "constraints")),
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


def evaluation_request_from_payload(value: Mapping[str, object]) -> EvaluationRequest:
    """Decode one durable evaluation request."""
    return EvaluationRequest(
        _string(value, "request_id"),
        _string(value, "session_id"),
        _integer(value, "objective_version"),
        _string(value, "attempt_id"),
        state_ref_from(_mapping(value, "evaluated_state")),
        _string(value, "baseline_node_id"),
        _string(value, "evaluator_version"),
    )


def evaluation_receipt_from_payload(value: Mapping[str, object]) -> EvaluationReceipt:
    """Decode one verified durable evaluation receipt."""
    evidence = value.get("evidence", ())
    if not isinstance(evidence, (list, tuple)):
        raise IntegrityError("event payload evidence must be an array")
    accepted = value.get("accepted")
    if not isinstance(accepted, bool):
        raise IntegrityError("event payload accepted must be a boolean")
    return EvaluationReceipt(
        _string(value, "receipt_id"),
        _string(value, "request_id"),
        _integer(value, "objective_version"),
        state_ref_from(_mapping(value, "evaluated_state")),
        _string(value, "baseline_node_id"),
        _string(value, "evaluator_version"),
        accepted,
        _string(value, "comparison"),
        _mapping_or_empty(value, "objectives"),
        tuple(artifact_ref_from(_mapping_value(item, "evidence")) for item in evidence),
    )


def artifact_ref_from(value: Mapping[str, object]) -> ArtifactRef:
    """Decode a verified artifact reference carried by an evaluation receipt."""
    return ArtifactRef(
        _string(value, "digest"),
        _integer(value, "size"),
        _string(value, "media_type"),
        _string(value, "provenance"),
    )


def state_ref_from(value: Mapping[str, object]) -> StateRef:
    """Decode an opaque external state reference."""
    restorable = value.get("restorable", False)
    if not isinstance(restorable, bool):
        raise IntegrityError("event payload restorable must be a boolean")
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


def command_from_payload(value: Mapping[str, object]) -> OperatorCommand:
    """Decode an admitted command while rebuilding the durable inbox."""
    command_id = _string(value, "command_id")
    session_id = _string(value, "session_id")
    command_type = _string(value, "__type__") if "__type__" in value else None
    if command_type == "Message":
        return Message(command_id, session_id, _string(value, "text"))
    if command_type == "Steer":
        return Steer(
            command_id,
            session_id,
            _string(value, "objective"),
            _string(value, "success_evidence"),
        )
    if command_type == "Pause":
        return Pause(command_id, session_id)
    if command_type == "Resume":
        return Resume(command_id, session_id)
    if command_type == "Stop":
        return Stop(command_id, session_id)
    if command_type == "CheckpointRequest":
        return CheckpointRequest(command_id, session_id)
    if command_type == "EvaluationCommand":
        return EvaluationCommand(
            command_id, session_id, state_ref_from(_mapping(value, "state"))
        )
    raise IntegrityError("admitted command has an unsupported type")


def string_from_payload(value: Mapping[str, object], name: str) -> str:
    """Decode a required string from a durable event payload."""
    return _string(value, name)


def integer_from_payload(value: Mapping[str, object], name: str) -> int:
    """Decode a required integer from a durable event payload."""
    return _integer(value, name)


def node_from_payload(value: Mapping[str, object]) -> CommittedNode:
    """Decode a committed lineage node from its durable event payload."""
    return CommittedNode(
        _string(value, "node_id"),
        _integer(value, "objective_version"),
        state_ref_from(_mapping(value, "state")),
        _optional_string(value, "parent_id"),
        _optional_string(value, "evaluation_receipt_id"),
        _mapping_or_empty(value, "objectives"),
    )


def attempt_from_payload(value: Mapping[str, object]) -> Attempt:
    """Decode an attempt fact from its durable event payload."""
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
        raise IntegrityError(f"event payload {name} must be an object")
    return value


def _mapping_or_empty(value: Mapping[str, object], name: str) -> Mapping[str, object]:
    """Extract an optional JSON object using an empty default."""
    return _mapping_value(value.get(name, {}), name)


def _string(value: Mapping[str, object], name: str) -> str:
    """Extract a required string without coercion."""
    candidate = value.get(name)
    if not isinstance(candidate, str):
        raise IntegrityError(f"event payload {name} must be a string")
    return candidate


def _optional_string(value: Mapping[str, object], name: str) -> str | None:
    candidate = value.get(name)
    if candidate is not None and not isinstance(candidate, str):
        raise IntegrityError(f"event payload {name} must be a string or null")
    return candidate


def _integer(value: Mapping[str, object], name: str) -> int:
    candidate = value.get(name)
    if isinstance(candidate, bool) or not isinstance(candidate, int):
        raise IntegrityError(f"event payload {name} must be an integer")
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
        raise IntegrityError(f"event payload {name} must be a decimal string") from exc


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(item, str) for item in value
    ):
        raise IntegrityError(f"event payload {name} must be an array of strings")
    return tuple(value)
