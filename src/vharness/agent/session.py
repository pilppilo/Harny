"""Application service coordinating one durable, externally executed session."""

# pylint: disable=too-many-instance-attributes,too-many-arguments
# Session owns explicit external boundaries by design; collapsing them would hide I/O.
# pylint: disable=too-many-locals,too-many-return-statements,too-many-branches
# Rebuild and command dispatch remain local, bounded coordinator responsibilities.
# Rebuild restores several independent durable indexes from one ordered stream.

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from typing import Mapping
from uuid import uuid4

from .artifacts import ArtifactStore
from .codec import canonical_json, to_json_value
from .errors import ContractError, IntegrityError, TransitionError
from .journal import SqliteJournal
from .models import (
    ActionProposal,
    Attempt,
    Checkpoint,
    CheckpointRequest,
    CommittedNode,
    EvaluationReceipt,
    EvaluationCommand,
    EvaluationRequest,
    Event,
    ExecutionReceipt,
    ExecutionStatus,
    Message,
    OperatorCommand,
    Pause,
    PromotionDisposition,
    ResourceReservation,
    Resume,
    SessionStatus,
    SessionView,
    StateRef,
    Steer,
    Stop,
    TaskSpec,
)
from .ports import Environment, Evaluator, Runtime
from .replay import projection_payload, reduce_event, replay
from .session_state import (
    command_from_payload,
    integer_from_payload,
    receipt_from_payload,
    reservation_from_payload,
    string_from_payload,
)
from .transitions import (
    SessionState,
    apply_steer,
    consume_evaluation,
    fail_evaluation_verification,
    intend_action,
    intend_evaluation,
    promote,
    promotion_disposition,
    record_evaluation_intake,
    record_receipt_state,
    start_attempt,
)


class Session:
    """A synchronously driven, single-writer durable session application API."""

    def __init__(
        self,
        session_id: str,
        state: SessionState,
        cursor: int,
        *,
        journal: SqliteJournal,
        artifacts: ArtifactStore,
        environment: Environment,
        runtime: Runtime,
        evaluator: Evaluator,
    ) -> None:
        self._session_id = session_id
        self._state = state
        self._cursor = cursor
        self._journal = journal
        self._artifacts = artifacts
        self._environment = environment
        self._runtime = runtime
        self._evaluator = evaluator
        self._inbox: list[OperatorCommand] = []
        self._reservations: dict[str, ResourceReservation] = {}
        self._receipts: dict[str, ExecutionReceipt] = {}
        self._commands: dict[str, OperatorCommand] = {}
        self._proposal_attempts: dict[str, tuple[str, int]] = {}
        self._settled_operations: set[str] = set()

    @classmethod
    def create(
        cls,
        session_id: str,
        task: TaskSpec,
        *,
        journal: SqliteJournal,
        artifacts: ArtifactStore,
        environment: Environment,
        runtime: Runtime,
        evaluator: Evaluator,
    ) -> "Session":
        """Persist a seeded root without starting autonomous work or external I/O."""
        contract = environment.describe()
        if contract.environment_id != task.environment_id:
            raise ContractError(
                "task environment_id does not match environment contract"
            )
        root = CommittedNode(
            node_id=f"root-{session_id}",
            objective_version=task.objective_version,
            state=contract.initial_state,
        )
        state = SessionState(task=task, status=SessionStatus.CREATED, lineage_head=root)
        session = cls(
            session_id,
            state,
            0,
            journal=journal,
            artifacts=artifacts,
            environment=environment,
            runtime=runtime,
            evaluator=evaluator,
        )
        session._persist(
            "session_created",
            state,
            {"task": task, "root_node": root, "environment": contract},
        )
        return session

    @classmethod
    def open(
        cls,
        session_id: str,
        *,
        journal: SqliteJournal,
        artifacts: ArtifactStore,
        environment: Environment,
        runtime: Runtime,
        evaluator: Evaluator,
    ) -> "Session":
        """Rebuild validated state from journal facts without external submission."""
        events: list[Event] = []
        cursor = 0
        while True:
            page = journal.events(session_id, after_sequence=cursor, limit=100)
            if not page:
                break
            events.extend(page)
            cursor = page[-1].sequence
        if not events:
            raise IntegrityError(f"session {session_id!r} has no creation event")
        state = replay(events)
        session = cls(
            session_id,
            state,
            cursor,
            journal=journal,
            artifacts=artifacts,
            environment=environment,
            runtime=runtime,
            evaluator=evaluator,
        )
        admitted: dict[str, OperatorCommand] = {}
        applied: set[str] = set()
        for event in events:
            reservation = event.payload.get("reservation")
            if isinstance(reservation, Mapping):
                parsed = reservation_from_payload(reservation)
                session._reservations[parsed.operation_id] = parsed
            proposal = event.payload.get("proposal")
            if event.kind == "action_intended" and isinstance(proposal, Mapping):
                session._proposal_attempts[
                    string_from_payload(proposal, "proposal_id")
                ] = (
                    string_from_payload(proposal, "attempt_id"),
                    integer_from_payload(proposal, "objective_version"),
                )
            receipt = event.payload.get("receipt")
            if event.kind == "receipt_received" and isinstance(receipt, Mapping):
                parsed_receipt = receipt_from_payload(receipt)
                session._receipts[parsed_receipt.receipt_id] = parsed_receipt
            command_data = event.payload.get("command")
            if event.kind == "command_admitted" and isinstance(command_data, Mapping):
                command = command_from_payload(command_data)
                admitted[command.command_id] = command
            if event.kind in ("command_applied", "command_rejected"):
                command_id = event.payload.get("command_id")
                if isinstance(command_id, str):
                    applied.add(command_id)
            if event.kind != "command_admitted" and isinstance(command_data, Mapping):
                applied.add(string_from_payload(command_data, "command_id"))
            if event.kind == "receipt_received":
                receipt_data = event.payload.get("receipt")
                if isinstance(receipt_data, Mapping):
                    status = string_from_payload(receipt_data, "status")
                    if status not in ("accepted", "running"):
                        proposal_id = string_from_payload(receipt_data, "proposal_id")
                        session._settled_operations.add(proposal_id)
        session._commands = admitted
        session._inbox = [
            command
            for command_id, command in admitted.items()
            if command_id not in applied
        ]
        return session

    @property
    def session_id(self) -> str:
        """Return the stable session identity."""
        return self._session_id

    def view(self) -> SessionView:
        """Return a read-only view at the current durable cursor."""
        return SessionView(
            session_id=self._session_id,
            status=self._state.status,
            task=self._state.task,
            cursor=self._cursor,
            lineage_head=self._state.lineage_head,
            active_attempt=self._state.active_attempt,
            pending_proposal_id=self._state.pending_proposal_id,
            wait_reason=self._state.wait_reason,
        )

    def events(self, after_sequence: int = 0, limit: int = 100) -> tuple[Event, ...]:
        """Return a bounded durable observation stream without causing new work."""
        return self._journal.events(
            self._session_id, after_sequence=after_sequence, limit=limit
        )

    def enqueue(self, command: OperatorCommand) -> str:
        """Admit a command for the next bounded coordinator advancement."""
        if command.session_id != self._session_id:
            raise ContractError("command belongs to another session")
        existing = self._commands.get(command.command_id)
        if existing is not None:
            if existing != command:
                raise ContractError("command ID was reused with different content")
            return command.command_id
        self._persist("command_admitted", self._state, {"command": command})
        self._commands[command.command_id] = command
        self._inbox.append(command)
        return command.command_id

    def advance(self) -> SessionView:
        """Apply queued operator commands; it never sleeps or dispatches new work."""
        controls = (Pause, Steer, Stop)
        commands = sorted(
            self._inbox,
            key=lambda command: 0 if isinstance(command, controls) else 1,
        )
        for command in commands:
            try:
                self._apply_command(command)
            except (ContractError, TransitionError) as exc:
                self._persist(
                    "command_rejected",
                    self._state,
                    {"command_id": command.command_id, "reason": str(exc)},
                    causation_id=command.command_id,
                )
            else:
                self._persist(
                    "command_applied",
                    self._state,
                    {"command_id": command.command_id},
                    causation_id=command.command_id,
                )
            self._inbox.remove(command)
        return self.view()

    def begin_attempt(self, attempt_id: str | None = None) -> Attempt:
        """Start one scripted phase-one trajectory from the current committed head."""
        self._require_schedulable()
        state = start_attempt(self._state, attempt_id or _new_id("attempt"))
        self._persist("attempt_started", state, {"attempt": state.active_attempt})
        if state.active_attempt is None:  # pragma: no cover - transition guarantee
            raise IntegrityError("attempt transition did not create an attempt")
        return state.active_attempt

    def submit_action(
        self,
        action_name: str,
        arguments: Mapping[str, object],
        *,
        rationale: str,
        reservation_cost: Decimal | None = None,
        proposal_id: str | None = None,
    ) -> ExecutionReceipt:
        """Record intent before proposing one action to the external runtime."""
        self._require_schedulable()
        attempt = self._require_active_attempt()
        contract = self._environment.describe()
        action = next(
            (item for item in contract.actions if item.name == action_name), None
        )
        if action is None:
            raise ContractError(f"unknown environment action {action_name!r}")
        _validate_action_arguments(arguments, action.argument_schema)
        proposal_id = proposal_id or _new_id("proposal")
        reservation = ResourceReservation(
            reservation_id=_new_id("reservation"),
            operation_id=proposal_id,
            objective_version=self._state.task.objective_version,
            actions=1,
            cost=reservation_cost,
        )
        intended = intend_action(
            self._state, proposal_id, attempt.attempt_id, reservation
        )
        proposal = ActionProposal(
            proposal_id=proposal_id,
            session_id=self._session_id,
            objective_version=self._state.task.objective_version,
            attempt_id=attempt.attempt_id,
            action_name=action_name,
            arguments=to_json_value(arguments),
            expected_state=attempt.result_state or attempt.starting_state,
            reservation=reservation,
            rationale=rationale,
            idempotency_key=proposal_id if contract.capabilities.idempotency else None,
        )
        self._reservations[proposal_id] = reservation
        self._proposal_attempts[proposal_id] = (
            attempt.attempt_id,
            self._state.task.objective_version,
        )
        self._persist(
            "action_intended",
            intended,
            {"proposal": proposal, "reservation": reservation},
        )
        receipt = self._runtime.submit(proposal)
        self.receive_receipt(receipt)
        return receipt

    def receive_receipt(self, receipt: ExecutionReceipt) -> SessionView:
        """Durably ingest one runtime receipt before its state becomes visible."""
        existing = self._receipts.get(receipt.receipt_id)
        if existing is not None:
            if existing != receipt:
                raise ContractError("receipt ID was reused with different content")
            return self.view()
        reservation = self._reservations.get(receipt.proposal_id)
        if reservation is None:
            raise ContractError("receipt does not correlate to a known proposal")
        if receipt.objective_version != reservation.objective_version:
            raise ContractError("receipt objective_version does not match its proposal")
        state = record_receipt_state(
            self._state, receipt.proposal_id, receipt.status.value
        )
        proposal_attempt = self._proposal_attempts.get(receipt.proposal_id)
        if proposal_attempt is None:
            raise IntegrityError("receipt is missing durable proposal ownership")
        applies_to_active_attempt = (
            proposal_attempt
            == (
                self._state.active_attempt.attempt_id,
                self._state.task.objective_version,
            )
            if self._state.active_attempt is not None
            else False
        )
        if (
            receipt.state is not None
            and receipt.status
            not in (ExecutionStatus.ACCEPTED, ExecutionStatus.RUNNING)
            and applies_to_active_attempt
        ):
            state = replace(
                state,
                active_attempt=replace(
                    state.active_attempt, result_state=receipt.state
                ),
            )
        settles_operation = (
            receipt.status not in (ExecutionStatus.ACCEPTED, ExecutionStatus.RUNNING)
            and receipt.proposal_id not in self._settled_operations
        )
        if settles_operation:
            state = replace(
                state, ledger=state.ledger.settle(reservation, receipt.usage)
            )
            state = replace(
                state,
                action_operations=tuple(
                    (
                        (*operation[:4], True)
                        if operation[0] == receipt.proposal_id
                        else operation
                    )
                    for operation in state.action_operations
                ),
            )
        self._persist(
            "receipt_received",
            state,
            {"receipt": receipt},
        )
        self._receipts[receipt.receipt_id] = receipt
        if receipt.status not in (ExecutionStatus.ACCEPTED, ExecutionStatus.RUNNING):
            self._settled_operations.add(receipt.proposal_id)
        return self.view()

    def request_evaluation(self, state: StateRef | None = None) -> EvaluationReceipt:
        """Request external evaluation and promote only an applicable result."""
        self._require_schedulable()
        attempt = self._require_active_attempt()
        evaluated_state = state or attempt.result_state or attempt.starting_state
        request = EvaluationRequest(
            request_id=_new_id("evaluation"),
            session_id=self._session_id,
            objective_version=self._state.task.objective_version,
            attempt_id=attempt.attempt_id,
            evaluated_state=evaluated_state,
            baseline_node_id=self._state.lineage_head.node_id,
            evaluator_version=self._state.task.evaluation_contract_id,
        )
        reservation = ResourceReservation(
            reservation_id=_new_id("reservation"),
            operation_id=request.request_id,
            objective_version=request.objective_version,
            evaluations=1,
        )
        pending = intend_evaluation(self._state, request, reservation)
        self._reservations[request.request_id] = reservation
        self._persist(
            "evaluation_intended",
            pending,
            {"request": request, "reservation": reservation},
        )
        receipt = self._evaluator.evaluate(request)
        disposition = promotion_disposition(self._state, request, receipt)
        self._persist(
            "evaluation_intake",
            record_evaluation_intake(
                self._state,
                request.request_id,
                receipt.receipt_id,
                canonical_json(receipt),
            ),
            {
                "request_id": request.request_id,
                "receipt_id": receipt.receipt_id,
                "raw_receipt": canonical_json(receipt),
            },
        )
        try:
            for evidence in receipt.evidence:
                self._artifacts.read(evidence)
        except IntegrityError as exc:
            self._persist(
                "evaluation_verification_failed",
                fail_evaluation_verification(
                    self._state, request.request_id, receipt.receipt_id
                ),
                {
                    "request_id": request.request_id,
                    "receipt_id": receipt.receipt_id,
                    "reason": str(exc),
                },
            )
            raise
        self._persist(
            "evaluation_received",
            consume_evaluation(self._state, receipt, disposition),
            {
                "receipt": receipt,
                "disposition": disposition.value,
            },
        )
        if disposition is PromotionDisposition.ACCEPTED:
            promoted = promote(self._state, request, receipt, _new_id("node"))
            self._persist(
                "lineage_promoted",
                promoted,
                {
                    "node": promoted.lineage_head,
                    "evaluation_receipt_id": receipt.receipt_id,
                },
            )
        return receipt

    def reconcile_pending(self) -> SessionView:
        """Ask once about an interrupted operation; never blindly resend it."""
        proposal_id = self._state.pending_proposal_id
        if proposal_id is None:
            return self.view()
        result = self._runtime.reconcile(proposal_id)
        if result.receipt is not None:
            return self.receive_receipt(result.receipt)
        state = replace(
            self._state,
            status=SessionStatus.WAITING,
            wait_reason=f"runtime reconciliation: {result.kind.value}",
        )
        self._persist("proposal_reconciled", state, {"result": result.kind.value})
        return self.view()

    def checkpoint(self) -> Checkpoint:
        """Persist an explicit checkpoint marker at the current durable state."""
        snapshot = projection_payload(self._state)
        checkpoint = Checkpoint(
            checkpoint_id=_new_id("checkpoint"),
            session_id=self._session_id,
            objective_version=self._state.task.objective_version,
            cursor=self._cursor,
            projection_digest=hashlib.sha256(
                canonical_json(snapshot).encode()
            ).hexdigest(),
            pending_operation_ids=(
                (self._state.pending_proposal_id,)
                if self._state.pending_proposal_id
                else ()
            ),
        )
        self._persist("checkpoint", self._state, {"checkpoint": checkpoint})
        return checkpoint

    def _apply_command(self, command: OperatorCommand) -> None:
        if isinstance(command, Message):
            self._persist("operator_message", self._state, {"command": command})
            return
        if isinstance(command, Steer):
            self._persist(
                "objective_steered",
                apply_steer(self._state, command.objective, command.success_evidence),
                {"command": command},
                causation_id=command.command_id,
            )
            return
        if isinstance(command, Pause):
            self._persist(
                "session_paused",
                replace(self._state, status=SessionStatus.PAUSED),
                {"command": command},
                causation_id=command.command_id,
            )
            return
        if isinstance(command, Resume):
            status = (
                SessionStatus.WAITING
                if self._state.pending_proposal_id
                else SessionStatus.RUNNING
            )
            self._persist(
                "session_resumed",
                replace(self._state, status=status),
                {"command": command},
                causation_id=command.command_id,
            )
            return
        if isinstance(command, Stop):
            self._persist(
                "session_stopped",
                replace(self._state, status=SessionStatus.STOPPED),
                {"command": command},
                causation_id=command.command_id,
            )
            return
        if isinstance(command, CheckpointRequest):
            self.checkpoint()
            return
        if isinstance(command, EvaluationCommand):
            self.request_evaluation(command.state)
            return
        raise ContractError(f"unsupported phase-one command: {type(command).__name__}")

    def _persist(
        self,
        kind: str,
        state: SessionState,
        fields: Mapping[str, object],
        *,
        causation_id: str | None = None,
    ) -> Event:
        event = Event(
            event_id=_new_id("event"),
            session_id=self._session_id,
            sequence=self._cursor + 1,
            kind=kind,
            objective_version=state.task.objective_version,
            payload=to_json_value(fields),
            recorded_at=datetime.now(timezone.utc).isoformat(),
            causation_id=causation_id,
        )
        derived = reduce_event(None if self._cursor == 0 else self._state, event)
        if derived != state:
            raise IntegrityError(
                f"{kind} does not derive the requested durable session projection"
            )
        self._cursor = self._journal.append((event,), expected_cursor=self._cursor)
        self._state = derived
        return event

    def _require_schedulable(self) -> None:
        if self._state.status not in (SessionStatus.CREATED, SessionStatus.RUNNING):
            raise TransitionError(
                f"session is not schedulable while {self._state.status.value}"
            )

    def _require_active_attempt(self) -> Attempt:
        if self._state.active_attempt is None:
            raise TransitionError("no active attempt")
        return self._state.active_attempt


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _validate_action_arguments(
    arguments: Mapping[str, object], schema: Mapping[str, object]
) -> None:
    """Validate the small object-schema subset advertised by Phase 1 actions."""
    if not isinstance(arguments, Mapping) or not all(
        isinstance(key, str) for key in arguments
    ):
        raise ContractError("action arguments must be a string-keyed object")
    required = schema.get("required", ())
    if not isinstance(required, (tuple, list)) or not all(
        isinstance(key, str) for key in required
    ):
        raise ContractError("action schema required must be an array of strings")
    absent = set(required) - set(arguments)
    if absent:
        raise ContractError(f"action arguments omit required fields: {sorted(absent)}")
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise ContractError("action schema properties must be an object")
    unsupported = {
        key
        for key in schema
        if key not in {"type", "required", "properties", "additionalProperties"}
    }
    if schema.get("type", "object") != "object" or unsupported:
        raise ContractError("action schema uses unsupported constructs")
    additional = schema.get("additionalProperties", True)
    if not isinstance(additional, bool):
        raise ContractError("action schema additionalProperties must be a boolean")
    if not additional and set(arguments) - set(properties):
        raise ContractError("action arguments include undeclared fields")
    for name, property_schema in properties.items():
        if not isinstance(name, str) or not isinstance(property_schema, Mapping):
            raise ContractError("action schema property must be a named object")
        if property_schema.get("type") not in ("string", "integer", "boolean"):
            raise ContractError(f"action schema has unsupported type for {name!r}")
        if set(property_schema) != {"type"}:
            raise ContractError(
                f"action schema property {name!r} uses unsupported constructs"
            )
    for name, value in arguments.items():
        property_schema = properties.get(name)
        if not isinstance(property_schema, Mapping):
            continue
        declared_type = property_schema.get("type")
        if declared_type == "string" and not isinstance(value, str):
            raise ContractError(f"action argument {name!r} must be a string")
        if declared_type == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ContractError(f"action argument {name!r} must be an integer")
        if declared_type == "boolean" and not isinstance(value, bool):
            raise ContractError(f"action argument {name!r} must be a boolean")
