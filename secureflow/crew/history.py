"""Persistent session history — survives process restarts."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_HISTORY_DB = str(Path.home() / ".secureflow" / "history.db")


class SessionHistory:
    """SQLite-backed store for completed scan/dev sessions."""

    def __init__(self, db_path: str = _HISTORY_DB):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                    session_type TEXT     NOT NULL,
                    target       TEXT     NOT NULL,
                    status       TEXT     NOT NULL,
                    summary      TEXT     DEFAULT '',
                    started_at   DATETIME NOT NULL,
                    completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    findings_json TEXT    DEFAULT '[]'
                )
            """)
            # Databases created before findings_json existed need migrating —
            # SQLite has no "ADD COLUMN IF NOT EXISTS", so check first.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
            if "findings_json" not in columns:
                conn.execute("ALTER TABLE sessions ADD COLUMN findings_json TEXT DEFAULT '[]'")
            conn.commit()

    def record(
        self,
        session_type: str,
        target: str,
        status: str,
        summary: str = "",
        started_at: Optional[str] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        """Persist a completed session. Returns inserted row id.

        `findings` are the structured, per-CVE results (severity, confidence,
        reference, source, description) from SecurityTools.get_findings() —
        stored so a later scan of the same target can diff against them (see
        get_latest_for_target) and so a historical export has real structured
        data to work with, not just the prose summary.
        """
        ts = started_at or datetime.now().isoformat()
        findings_json = json.dumps(findings or [])
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO sessions (session_type, target, status, summary, started_at, findings_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_type, target, status, summary[:1000], ts, findings_json),
            )
            conn.commit()
            return cursor.lastrowid

    def get_latest_for_target(
        self, target: str, session_type: str = "security"
    ) -> Optional[Dict[str, Any]]:
        """Most recent recorded session for this exact target, with its
        structured findings — used to diff a new scan against the last one."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id, status, summary, started_at, completed_at, findings_json "
                "FROM sessions WHERE session_type = ? AND target = ? "
                "ORDER BY id DESC LIMIT 1",
                (session_type, target),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        try:
            findings = json.loads(row[5] or "[]")
        except (TypeError, ValueError):
            findings = []
        return {
            "id": row[0],
            "status": row[1],
            "summary": row[2],
            "started_at": row[3],
            "completed_at": row[4],
            "findings": findings,
        }

    def get_sessions(
        self,
        limit: int = 20,
        session_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return most recent sessions, newest first."""
        with sqlite3.connect(self.db_path) as conn:
            if session_type:
                cursor = conn.execute(
                    "SELECT id, session_type, target, status, summary, started_at, completed_at "
                    "FROM sessions WHERE session_type = ? ORDER BY id DESC LIMIT ?",
                    (session_type, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT id, session_type, target, status, summary, started_at, completed_at "
                    "FROM sessions ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()

        return [
            {
                "id": r[0],
                "type": r[1],
                "target": r[2],
                "status": r[3],
                "summary": r[4],
                "started_at": r[5],
                "completed_at": r[6],
            }
            for r in rows
        ]

    def clear(self) -> None:
        """Delete all session records (used in tests)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()
