"""SQLite append-only journal for canonical session events."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Iterable

from .codec import canonical_json, parse_json_object
from .errors import IntegrityError, PersistenceError
from .models import Event


class SqliteJournal:
    """Owns one SQLite connection and atomic ordered event appends."""

    def __init__(self, path: str | Path) -> None:
        try:
            self._connection = sqlite3.connect(str(path))
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._create_schema()
        except sqlite3.Error as exc:
            raise PersistenceError(f"could not open journal {path}: {exc}") from exc

    def close(self) -> None:
        """Close the locally owned SQLite connection."""
        self._connection.close()

    def __enter__(self) -> "SqliteJournal":
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def append(self, events: Iterable[Event], *, expected_cursor: int) -> int:
        """Atomically append consecutive events after an expected session cursor."""
        batch = tuple(events)
        if not batch:
            return expected_cursor
        session_ids = {event.session_id for event in batch}
        if len(session_ids) != 1:
            raise PersistenceError("an event batch must belong to one session")
        if self._is_duplicate_batch(batch):
            return self.cursor(batch[0].session_id)
        expected_sequences = tuple(
            range(expected_cursor + 1, expected_cursor + len(batch) + 1)
        )
        if tuple(event.sequence for event in batch) != expected_sequences:
            raise PersistenceError("event batch sequences must be consecutive")
        session_id = batch[0].session_id
        try:
            with self._connection:
                current = self.cursor(session_id)
                if current != expected_cursor:
                    raise PersistenceError(
                        "journal cursor conflict for "
                        f"{session_id}: expected {expected_cursor}, found {current}"
                    )
                self._connection.execute(
                    """
                    INSERT INTO sessions (session_id, cursor, schema_version)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO NOTHING
                    """,
                    (session_id, 0, batch[0].schema_version),
                )
                self._connection.executemany(
                    """
                    INSERT INTO events (
                        event_id, session_id, sequence, kind, schema_version,
                        objective_version, payload, recorded_at, causation_id,
                        correlation_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            event.event_id,
                            event.session_id,
                            event.sequence,
                            event.kind,
                            event.schema_version,
                            event.objective_version,
                            canonical_json(event.payload),
                            event.recorded_at,
                            event.causation_id,
                            event.correlation_id,
                        )
                        for event in batch
                    ],
                )
                self._connection.execute(
                    """
                    INSERT INTO sessions (session_id, cursor, schema_version)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET cursor = excluded.cursor
                    """,
                    (session_id, batch[-1].sequence, batch[-1].schema_version),
                )
        except PersistenceError:
            raise
        except sqlite3.IntegrityError as exc:
            raise IntegrityError(f"journal integrity failure: {exc}") from exc
        except sqlite3.Error as exc:
            raise PersistenceError(f"could not append journal events: {exc}") from exc
        return batch[-1].sequence

    def _is_duplicate_batch(self, batch: tuple[Event, ...]) -> bool:
        """Recognize an exact redelivery without accepting conflicting ID reuse."""
        rows = self._connection.execute(
            "SELECT event_id, session_id, sequence, kind, objective_version, payload "
            f"FROM events WHERE event_id IN ({','.join('?' for _ in batch)})",
            tuple(event.event_id for event in batch),
        ).fetchall()
        if not rows:
            return False
        if len(rows) != len(batch):
            raise IntegrityError("event batch mixes new and already-used event IDs")
        existing = {row[0]: row for row in rows}
        for event in batch:
            row = existing[event.event_id]
            expected = (
                event.event_id,
                event.session_id,
                event.sequence,
                event.kind,
                event.objective_version,
                canonical_json(event.payload),
            )
            if row != expected:
                raise IntegrityError("event ID was reused with different content")
        return True

    def cursor(self, session_id: str) -> int:
        """Return the latest durable sequence, or zero for an unseen session."""
        try:
            row = self._connection.execute(
                "SELECT cursor FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceError(f"could not read journal cursor: {exc}") from exc
        return int(row[0]) if row else 0

    def events(
        self, session_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> tuple[Event, ...]:
        """Read a bounded ordered event window."""
        if after_sequence < 0 or limit < 1:
            raise PersistenceError("event query bounds are invalid")
        try:
            rows = self._connection.execute(
                """
                SELECT event_id, session_id, sequence, kind, objective_version, payload,
                       recorded_at, causation_id, correlation_id, schema_version
                FROM events
                WHERE session_id = ? AND sequence > ?
                ORDER BY sequence
                LIMIT ?
                """,
                (session_id, after_sequence, limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise PersistenceError(f"could not read journal events: {exc}") from exc
        return tuple(
            Event(
                event_id=row[0],
                session_id=row[1],
                sequence=row[2],
                kind=row[3],
                objective_version=row[4],
                payload=parse_json_object(row[5]),
                recorded_at=row[6],
                causation_id=row[7],
                correlation_id=row[8],
                schema_version=row[9],
            )
            for row in rows
        )

    def _create_schema(self) -> None:
        with closing(self._connection.cursor()) as cursor:
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    cursor INTEGER NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    objective_version INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    causation_id TEXT,
                    correlation_id TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id),
                    UNIQUE(session_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS events_by_correlation
                    ON events(session_id, correlation_id, sequence);
                CREATE INDEX IF NOT EXISTS events_by_kind
                    ON events(session_id, kind, sequence);
                """)
