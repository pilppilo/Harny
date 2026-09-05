"""Journal replay and idempotency checks."""

import pytest

from vharness.agent.errors import IntegrityError
from vharness.agent.journal import SqliteJournal
from vharness.agent.models import Event


def test_exact_event_redelivery_is_idempotent(tmp_path):
    journal = SqliteJournal(tmp_path / "journal.sqlite3")
    event = Event(
        event_id="event-1",
        session_id="session-1",
        sequence=1,
        kind="fixture",
        objective_version=1,
        payload={"value": 1},
        recorded_at="2026-09-05T00:00:00+00:00",
    )

    assert journal.append((event,), expected_cursor=0) == 1
    assert journal.append((event,), expected_cursor=1) == 1
    assert journal.events("session-1") == (event,)
    journal.close()


def test_event_id_reuse_rejects_changed_timestamp(tmp_path):
    journal = SqliteJournal(tmp_path / "journal.sqlite3")
    event = Event("event-1", "session-1", 1, "fixture", 1, {"value": 1}, "now")
    journal.append((event,), expected_cursor=0)
    changed = Event("event-1", "session-1", 1, "fixture", 1, {"value": 1}, "later")
    with pytest.raises(IntegrityError, match="reused"):
        journal.append((changed,), expected_cursor=1)
    journal.close()
