"""Immutable domain records for durable agent sessions."""

# pylint: disable=too-many-instance-attributes
# Immutable boundary records intentionally name every persisted contract field.

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, TypeAlias

from .errors import ContractError

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = (
    JsonPrimitive | tuple["JsonValue", ...] | Mapping[str, "JsonValue"]
)

SCHEMA_VERSION = 1


def frozen_mapping(
    values: Mapping[str, JsonValue] | None = None,
) -> Mapping[str, JsonValue]:
    """Copy a JSON-shaped mapping so domain records never share caller mutation."""
    return MappingProxyType(dict(values or {}))


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")


class CompletionMode(str, Enum):
    """Whether external evidence may complete the current objective."""

    FINITE = "finite"
    ONGOING = "ongoing"


class SessionStatus(str, Enum):
    """The local scheduler lifecycle of one durable session."""

    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ExecutionStatus(str, Enum):
    """The latest externally observed operation status."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INDETERMINATE = "indeterminate"


class AttemptDisposition(str, Enum):
    """The durable outcome of one internal search trajectory."""

    ACTIVE = "active"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABANDONED = "abandoned"


class PromotionDisposition(str, Enum):
    """Whether an evaluation applies to the current committed lineage."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INCOMPARABLE = "incomparable"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    """A verified immutable object held by the local artifact store."""

    digest: str
    size: int
    media_type: str
    provenance: str

    def __post_init__(self) -> None:
        if len(self.digest) != 64 or any(
            char not in "0123456789abcdef" for char in self.digest
        ):
            raise ContractError(
                "artifact digest must be a lowercase SHA-256 hex digest"
            )
        if self.size < 0:
            raise ContractError("artifact size must not be negative")
        _nonempty(self.media_type, "artifact media_type")
        _nonempty(self.provenance, "artifact provenance")


@dataclass(frozen=True, slots=True)
class StateRef:
    """An opaque externally owned state or trajectory cursor."""

    owner: str
    value: str
    digest: str | None = None
    revision: str | None = None
    restorable: bool = False

    def __post_init__(self) -> None:
        _nonempty(self.owner, "state owner")
        _nonempty(self.value, "state value")
        if self.digest is not None and len(self.digest) != 64:
            raise ContractError("state digest must be a SHA-256 digest when supplied")


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Scheduling limits. None means the configured limit is not bounded."""

    actions: int | None = None
    model_calls: int | None = None
    evaluations: int | None = None
    cost: Decimal | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("actions", self.actions),
            ("model_calls", self.model_calls),
            ("evaluations", self.evaluations),
        ):
            if value is not None and value < 0:
                raise ContractError(f"budget {name} must not be negative")
        if self.cost is not None and self.cost < 0:
            raise ContractError("budget cost must not be negative")


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Task intent and the current operator-controlled objective version."""

    task_id: str
    objective: str
    completion_mode: CompletionMode
    success_evidence: str
    budgets: BudgetLimits
    environment_id: str
    evaluation_contract_id: str
    objective_version: int = 1
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("task_id", self.task_id),
            ("objective", self.objective),
            ("success_evidence", self.success_evidence),
            ("environment_id", self.environment_id),
            ("evaluation_contract_id", self.evaluation_contract_id),
        ):
            _nonempty(value, name)
        if self.objective_version < 1:
            raise ContractError("objective_version must be positive")

    def steered(self, objective: str, success_evidence: str) -> "TaskSpec":
        """Return the next durable objective without mutating historical intent."""
        return TaskSpec(
            task_id=self.task_id,
            objective=objective,
            completion_mode=self.completion_mode,
            success_evidence=success_evidence,
            budgets=self.budgets,
            environment_id=self.environment_id,
            evaluation_contract_id=self.evaluation_contract_id,
            objective_version=self.objective_version + 1,
            constraints=self.constraints,
        )


@dataclass(frozen=True, slots=True)
class RuntimeCapabilities:
    """Trusted connector claims; model output cannot expand these capabilities."""

    cancellation: bool = False
    idempotency: bool = False
    reconciliation: bool = False
    revisions: bool = False


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    """One action declared by an external environment contract."""

    name: str
    description: str
    argument_schema: Mapping[str, JsonValue] = field(default_factory=frozen_mapping)

    def __post_init__(self) -> None:
        _nonempty(self.name, "action name")
        _nonempty(self.description, "action description")
        object.__setattr__(
            self, "argument_schema", frozen_mapping(self.argument_schema)
        )


@dataclass(frozen=True, slots=True)
class EnvironmentContract:
    """Mechanical environment state and declared action surface."""

    environment_id: str
    version: str
    initial_state: StateRef
    actions: tuple[ActionDefinition, ...]
    capabilities: RuntimeCapabilities

    def __post_init__(self) -> None:
        _nonempty(self.environment_id, "environment_id")
        _nonempty(self.version, "environment version")
        names = [action.name for action in self.actions]
        if len(names) != len(set(names)):
            raise ContractError("environment action names must be unique")


@dataclass(frozen=True, slots=True)
class UsageMeasurement:
    """Measured resource use. Missing cost remains unknown, never zero by default."""

    measurement_id: str
    actions: int = 0
    model_calls: int = 0
    evaluations: int = 0
    cost: Decimal | None = None

    def __post_init__(self) -> None:
        _nonempty(self.measurement_id, "measurement_id")
        for name, value in (
            ("actions", self.actions),
            ("model_calls", self.model_calls),
            ("evaluations", self.evaluations),
        ):
            if value < 0:
                raise ContractError(f"measured {name} must not be negative")
        if self.cost is not None and self.cost < 0:
            raise ContractError("measured cost must not be negative")


@dataclass(frozen=True, slots=True)
class ResourceReservation:
    """Declared bound recorded before a state-changing external request."""

    reservation_id: str
    operation_id: str
    objective_version: int
    actions: int = 0
    evaluations: int = 0
    cost: Decimal | None = None

    def __post_init__(self) -> None:
        _nonempty(self.reservation_id, "reservation_id")
        _nonempty(self.operation_id, "operation_id")
        if self.objective_version < 1 or self.actions < 0 or self.evaluations < 0:
            raise ContractError("reservation values must be non-negative")
        if self.cost is not None and self.cost < 0:
            raise ContractError("reserved cost must not be negative")


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """A typed proposed effect to send to the separately controlled runtime."""

    proposal_id: str
    session_id: str
    objective_version: int
    attempt_id: str
    action_name: str
    arguments: Mapping[str, JsonValue]
    expected_state: StateRef
    reservation: ResourceReservation
    rationale: str
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("proposal_id", self.proposal_id),
            ("session_id", self.session_id),
            ("attempt_id", self.attempt_id),
            ("action_name", self.action_name),
            ("rationale", self.rationale),
        ):
            _nonempty(value, name)
        if self.objective_version < 1:
            raise ContractError("proposal objective_version must be positive")
        if self.reservation.operation_id != self.proposal_id:
            raise ContractError("reservation operation_id must equal proposal_id")
        object.__setattr__(self, "arguments", frozen_mapping(self.arguments))


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    """An immutable observation from the runtime, including nonterminal status."""

    receipt_id: str
    proposal_id: str
    objective_version: int
    status: ExecutionStatus
    operation_id: str | None = None
    state: StateRef | None = None
    error: str | None = None
    usage: UsageMeasurement | None = None
    raw_artifact: ArtifactRef | None = None

    def __post_init__(self) -> None:
        _nonempty(self.receipt_id, "receipt_id")
        _nonempty(self.proposal_id, "proposal_id")
        if self.objective_version < 1:
            raise ContractError("receipt objective_version must be positive")


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    """An external evaluation request, anchored to a state and lineage head."""

    request_id: str
    session_id: str
    objective_version: int
    attempt_id: str
    evaluated_state: StateRef
    baseline_node_id: str
    evaluator_version: str

    def __post_init__(self) -> None:
        for name, value in (
            ("request_id", self.request_id),
            ("session_id", self.session_id),
            ("attempt_id", self.attempt_id),
            ("baseline_node_id", self.baseline_node_id),
            ("evaluator_version", self.evaluator_version),
        ):
            _nonempty(value, name)
        if self.objective_version < 1:
            raise ContractError("evaluation objective_version must be positive")


@dataclass(frozen=True, slots=True)
class EvaluationReceipt:
    """Native external evaluation result; Vharness does not rescore it."""

    receipt_id: str
    request_id: str
    objective_version: int
    evaluated_state: StateRef
    baseline_node_id: str
    evaluator_version: str
    accepted: bool
    comparison: str
    objectives: Mapping[str, JsonValue] = field(default_factory=frozen_mapping)
    evidence: tuple[ArtifactRef, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("receipt_id", self.receipt_id),
            ("request_id", self.request_id),
            ("baseline_node_id", self.baseline_node_id),
            ("evaluator_version", self.evaluator_version),
            ("comparison", self.comparison),
        ):
            _nonempty(value, name)
        if self.objective_version < 1:
            raise ContractError("evaluation receipt objective_version must be positive")
        object.__setattr__(self, "objectives", frozen_mapping(self.objectives))


@dataclass(frozen=True, slots=True)
class Attempt:
    """One multi-action search trajectory based on a committed lineage state."""

    attempt_id: str
    objective_version: int
    base_node_id: str
    starting_state: StateRef
    disposition: AttemptDisposition = AttemptDisposition.ACTIVE
    result_state: StateRef | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("attempt_id", self.attempt_id),
            ("base_node_id", self.base_node_id),
        ):
            _nonempty(value, name)
        if self.objective_version < 1:
            raise ContractError("attempt objective_version must be positive")


@dataclass(frozen=True, slots=True)
class CommittedNode:
    """A single-parent externally accepted state in the committed lineage."""

    node_id: str
    objective_version: int
    state: StateRef
    parent_id: str | None = None
    evaluation_receipt_id: str | None = None
    objectives: Mapping[str, JsonValue] = field(default_factory=frozen_mapping)

    def __post_init__(self) -> None:
        _nonempty(self.node_id, "node_id")
        if self.objective_version < 1:
            raise ContractError("node objective_version must be positive")
        object.__setattr__(self, "objectives", frozen_mapping(self.objectives))


@dataclass(frozen=True, slots=True)
class Event:
    """Canonical append-only session fact."""

    event_id: str
    session_id: str
    sequence: int
    kind: str
    objective_version: int
    payload: Mapping[str, JsonValue]
    recorded_at: str
    causation_id: str | None = None
    correlation_id: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id),
            ("session_id", self.session_id),
            ("kind", self.kind),
            ("recorded_at", self.recorded_at),
        ):
            _nonempty(value, name)
        if self.sequence < 1 or self.objective_version < 1:
            raise ContractError("event sequence and objective_version must be positive")
        object.__setattr__(self, "payload", frozen_mapping(self.payload))


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A projection digest anchored to the journal cursor it represents."""

    checkpoint_id: str
    session_id: str
    objective_version: int
    cursor: int
    projection_digest: str
    pending_operation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("checkpoint_id", self.checkpoint_id),
            ("session_id", self.session_id),
            ("projection_digest", self.projection_digest),
        ):
            _nonempty(value, name)
        if self.objective_version < 1 or self.cursor < 0:
            raise ContractError("checkpoint objective_version and cursor are invalid")
        if len(self.projection_digest) != 64:
            raise ContractError("checkpoint projection_digest must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class OperatorCommand:
    """Base record for durable human interaction with one session."""

    command_id: str
    session_id: str

    def __post_init__(self) -> None:
        _nonempty(self.command_id, "command_id")
        _nonempty(self.session_id, "command session_id")


@dataclass(frozen=True, slots=True)
class Message(OperatorCommand):
    """A durable operator message that does not alter task acceptance."""

    text: str

    def __post_init__(self) -> None:
        OperatorCommand.__post_init__(self)
        _nonempty(self.text, "message text")


@dataclass(frozen=True, slots=True)
class Steer(OperatorCommand):
    """An objective-changing command that creates a new objective version."""

    objective: str
    success_evidence: str

    def __post_init__(self) -> None:
        OperatorCommand.__post_init__(self)
        _nonempty(self.objective, "steer objective")
        _nonempty(self.success_evidence, "steer success_evidence")


@dataclass(frozen=True, slots=True)
class Pause(OperatorCommand):
    """Prevent new local work while retaining any external operation state."""


@dataclass(frozen=True, slots=True)
class Resume(OperatorCommand):
    """Resume local scheduling after a durable pause."""


@dataclass(frozen=True, slots=True)
class Stop(OperatorCommand):
    """Stop local scheduling without claiming external effects were undone."""


@dataclass(frozen=True, slots=True)
class CheckpointRequest(OperatorCommand):
    """Ask the coordinator to persist a checkpoint at the current cursor."""


@dataclass(frozen=True, slots=True)
class EvaluationCommand(OperatorCommand):
    """Ask the coordinator to request external evaluation of a supplied state."""

    state: StateRef


@dataclass(frozen=True, slots=True)
class SessionView:
    """Immutable projection returned to library callers."""

    session_id: str
    status: SessionStatus
    task: TaskSpec
    cursor: int
    lineage_head: CommittedNode
    active_attempt: Attempt | None
    pending_proposal_id: str | None = None
    wait_reason: str | None = None
