"""Durable state for interactive security assessments."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .tools import ToolAction, ToolResult


@dataclass(frozen=True)
class AssessmentSession:
    session_id: str
    targets: list[str]
    status: str = "active"
    created_at: float = 0.0


class AssessmentStore:
    """SQLite-backed session, action, and observation store.

    Writes are committed immediately so an interrupted agent can resume from
    the last recorded action. The store contains metadata and normalized
    output; large artifacts should be kept separately and referenced by hash.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, targets_json TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, tool TEXT NOT NULL, target TEXT NOT NULL,
                parameters_json TEXT NOT NULL, purpose TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL,
                FOREIGN KEY(session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS actions_session_fingerprint
                ON actions(session_id, fingerprint);
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY, action_id TEXT NOT NULL,
                status TEXT NOT NULL, output_json TEXT, error TEXT,
                evidence_json TEXT NOT NULL, created_at REAL NOT NULL,
                FOREIGN KEY(action_id) REFERENCES actions(action_id)
            );
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def create_session(self, targets: list[str], session_id: str | None = None) -> AssessmentSession:
        session = AssessmentSession(session_id or uuid.uuid4().hex[:12], list(targets), created_at=time.time())
        self.db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?)",
                        (session.session_id, json.dumps(session.targets), session.status, session.created_at))
        self.db.commit()
        return session

    def record_action(self, session_id: str, action: ToolAction, status: str = "pending") -> None:
        self.db.execute(
            "INSERT INTO actions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (action.action_id, session_id, action.fingerprint, action.tool,
             action.target, json.dumps(action.parameters, sort_keys=True),
             action.purpose, status, time.time()),
        )
        self.db.commit()

    def record_result(self, result: ToolResult) -> None:
        self.db.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex[:12], result.action_id, result.status,
             json.dumps(result.output, default=str) if result.output is not None else None,
             result.error, json.dumps(result.evidence), time.time()),
        )
        self.db.execute("UPDATE actions SET status = ? WHERE action_id = ?",
                        (result.status, result.action_id))
        self.db.commit()

    def action_seen(self, session_id: str, action: ToolAction) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM actions WHERE session_id = ? AND fingerprint = ? LIMIT 1",
            (session_id, action.fingerprint),
        ).fetchone()
        return row is not None

    def session(self, session_id: str) -> AssessmentSession:
        row = self.db.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown assessment session: {session_id}")
        return AssessmentSession(row["session_id"], json.loads(row["targets_json"]),
                                 row["status"], row["created_at"])
