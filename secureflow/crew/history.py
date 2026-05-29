"""Persistent session history — survives process restarts."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_HISTORY_DB = str(Path.home() / ".secureflow" / "history.db")


class SessionHistory:
    """SQLite-backed store for completed scan/dev sessions."""

    def __init__(self, db_path: str = _HISTORY_DB):
        self.db_path = db_path
        self._lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
                    session_type TEXT     NOT NULL,
                    target       TEXT     NOT NULL,
                    status       TEXT     NOT NULL,
                    summary      TEXT     DEFAULT '',
                    started_at   DATETIME NOT NULL,
                    completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def record(
        self,
        session_type: str,
        target: str,
        status: str,
        summary: str = "",
        started_at: Optional[str] = None,
    ) -> int:
        """Persist a completed session. Returns inserted row id."""
        ts = started_at or datetime.now().isoformat()
        with self._lock, sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO sessions (session_type, target, status, summary, started_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_type, target, status, summary[:1000], ts),
            )
            conn.commit()
            return cursor.lastrowid

    def get_sessions(
        self,
        limit: int = 20,
        session_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return most recent sessions, newest first."""
        with self._lock, sqlite3.connect(self.db_path) as conn:
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
        with self._lock, sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM sessions")
            conn.commit()
