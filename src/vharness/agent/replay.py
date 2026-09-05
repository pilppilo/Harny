"""Validated, pure reconstruction of durable session projections."""

from __future__ import annotations

from typing import Iterable, Mapping

from .errors import IntegrityError
from .models import Event
from .session_state import state_from_snapshot
from .transitions import SessionState


def reduce_event(previous: SessionState | None, event: Event) -> SessionState:
    """Apply one canonical event to a projection without performing I/O."""
    if previous is None and event.kind != "session_created":
        raise IntegrityError("the first event must create the session")
    if (
        previous is not None
        and event.objective_version < previous.task.objective_version
    ):
        raise IntegrityError("event objective version regresses the projection")
    snapshot = event.payload.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise IntegrityError("event has no projection payload")
    state = state_from_snapshot(snapshot)
    if state.task.objective_version != event.objective_version:
        raise IntegrityError("event objective version disagrees with its projection")
    return state


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
