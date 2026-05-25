"""
Crew orchestrator for collaborative multi-agent security assessment.
Manages agent communication, phases, and inter-agent dependencies.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from secureflow.crew.memory import SharedContext
from secureflow.crew.chat import AgentCommunicator
from secureflow.crew.tasks import create_crew

_DEFAULT_LOG = str(Path.home() / ".secureflow" / "crew_session.log")


class CrewOrchestrator:
    """Orchestrates multi-agent collaboration for security assessment."""

    def __init__(self, log_path: str = _DEFAULT_LOG):
        self.context = SharedContext()
        self.communicator = AgentCommunicator(self.context)
        self.log_path = log_path
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        self.logger = self._init_logger()
        self.target: Optional[str] = None

    def _init_logger(self) -> logging.Logger:
        """Initialize logging for crew collaboration."""
        logger = logging.getLogger("CrewOrchestrator")
        logger.setLevel(logging.INFO)

        handler = logging.FileHandler(self.log_path)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Also console output
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

        return logger

    def log(self, level: str, message: str) -> None:
        """Log a message at the given level."""
        getattr(self.logger, level.lower())(message)

    def run_security_crew(self, target: str) -> Dict[str, Any]:
        """Run full security crew (recon → analysis → reporting) as a single unified Crew."""
        self.target = target
        self.context.clear()

        self.log("INFO", f"🚀 Starting security crew for target: {target}")
        self.log("INFO", "=" * 70)

        try:
            crew = create_crew(target)
            result = crew.kickoff()

            self.context.write("session", "target", target)
            self.context.write("session", "result", str(result))
            self.context.write("session", "timestamp", datetime.now().isoformat())

            self.log("INFO", "=" * 70)
            self.log("INFO", "✅ Security crew completed successfully!")
            self.log("INFO", f"Session log: {self.log_path}")

            return {
                "success": True,
                "target": target,
                "result": str(result),
                "session_log": self.log_path,
            }

        except Exception as e:
            self.log("ERROR", f"Crew execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "session_log": self.log_path,
            }

    def send_notification(self, telegram_token: str = "", telegram_chat_id: str = ""):
        """Send completion notification via Telegram (optional)."""
        if not telegram_token or not telegram_chat_id:
            self.log("INFO", "Telegram notification skipped (no credentials)")
            return

        try:
            import requests

            message = (
                f"🤖 Security Crew Completed\n"
                f"Target: {self.target}\n"
                f"Session: {self.log_path}\n"
                f"Timestamp: {datetime.now().isoformat()}"
            )

            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = {"chat_id": telegram_chat_id, "text": message}

            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                self.log("INFO", "✅ Telegram notification sent")
            else:
                self.log("WARN", f"Telegram notification failed: {response.status_code}")

        except Exception as e:
            self.log("WARN", f"Could not send Telegram notification: {str(e)}")

    def export_session(self) -> str:
        """Export full session summary."""
        summary = f"SESSION SUMMARY: {self.target}\n"
        summary += f"Log: {self.log_path}\n"
        summary += f"Started: {datetime.now().isoformat()}\n\n"

        summary += self.context.export_summary()
        summary += "\n" + self.communicator.export_chat_log()

        return summary
