"""
Shared memory system for multi-agent collaboration.
Agents can write/read findings and track conversation flow.
"""

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB = str(Path.home() / ".secureflow" / "crew_context.db")


class SharedContext:
    """Shared memory for agents to collaborate and share findings."""

    def __init__(self, db_path: str = _DEFAULT_DB):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(agent_name, key)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    agent_name TEXT PRIMARY KEY,
                    status TEXT,
                    phase TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def write(self, agent_name: str, key: str, value: Any) -> None:
        """Write a finding to shared context."""
        with self.lock:
            value_json = json.dumps(value)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO findings (agent_name, key, value) VALUES (?, ?, ?)",
                    (agent_name, key, value_json),
                )
                conn.commit()

    def read(self, agent_name: str, key: str) -> Optional[Any]:
        """Read a finding from shared context."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM findings WHERE agent_name = ? AND key = ?",
                    (agent_name, key),
                )
                row = cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except json.JSONDecodeError:
                        return row[0]
                return None

    def get_all(self, agent_name: str) -> Dict[str, Any]:
        """Get all findings from an agent."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT key, value FROM findings WHERE agent_name = ? ORDER BY timestamp",
                    (agent_name,),
                )
                findings = {}
                for key, value in cursor.fetchall():
                    try:
                        findings[key] = json.loads(value)
                    except json.JSONDecodeError:
                        findings[key] = value
                return findings

    def get_latest_findings(self, limit: int = 5) -> Dict[str, Dict[str, Any]]:
        """Get latest findings from all agents."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT DISTINCT agent_name FROM findings
                    ORDER BY timestamp DESC
                    """
                )
                agents = [row[0] for row in cursor.fetchall()]
                findings = {}
                for agent in agents:
                    findings[agent] = self.get_all(agent)
                return findings

    def log_message(self, from_agent: str, to_agent: str, message: str) -> None:
        """Log inter-agent communication."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO messages (from_agent, to_agent, message) VALUES (?, ?, ?)",
                    (from_agent, to_agent, message),
                )
                conn.commit()

    def get_conversation_log(self) -> List[Dict[str, Any]]:
        """Get full conversation log between agents."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT from_agent, to_agent, message, timestamp
                    FROM messages
                    ORDER BY timestamp ASC
                    """
                )
                logs = []
                for from_agent, to_agent, message, timestamp in cursor.fetchall():
                    logs.append({
                        "from": from_agent,
                        "to": to_agent,
                        "message": message,
                        "timestamp": timestamp,
                    })
                return logs

    def set_agent_status(self, agent_name: str, status: str, phase: str = "") -> None:
        """Track agent status and current phase."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO metadata (agent_name, status, phase) VALUES (?, ?, ?)",
                    (agent_name, status, phase),
                )
                conn.commit()

    def get_agent_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Get agent status and phase."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT status, phase, timestamp FROM metadata WHERE agent_name = ?",
                    (agent_name,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "status": row[0],
                        "phase": row[1],
                        "timestamp": row[2],
                    }
                return None

    def clear(self) -> None:
        """Clear all context (for testing)."""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM findings")
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM metadata")
                conn.commit()

    def export_summary(self) -> str:
        """Export a summary of all agent findings (acquired under lock for consistency)."""
        with self.lock:
            summary = "=== CREW COLLABORATION SUMMARY ===\n\n"

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT agent_name, status, phase FROM metadata")
                summary += "AGENT STATUS:\n"
                for agent_name, status, phase in cursor.fetchall():
                    summary += f"  {agent_name}: {status} (phase: {phase})\n"

            summary += "\nAGENT FINDINGS:\n"
            for agent in ["recon", "analyst", "reporter"]:
                findings = self.get_all(agent)
                if findings:
                    summary += f"\n{agent.upper()}:\n"
                    for key, value in findings.items():
                        if isinstance(value, (dict, list)):
                            summary += f"  {key}: {json.dumps(value, indent=2)}\n"
                        else:
                            summary += f"  {key}: {value}\n"

            summary += "\nCONVERSATION LOG:\n"
            for msg in self.get_conversation_log():
                summary += (
                    f"  [{msg['timestamp']}] {msg['from']} → {msg['to']}: "
                    f"{msg['message'][:80]}...\n"
                )

            return summary
