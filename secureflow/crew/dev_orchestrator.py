import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from secureflow.crew.memory import SharedContext
from secureflow.crew.tasks import create_dev_crew, create_code_review_tasks
from secureflow.crew.agents import DevAgents
from secureflow.crew.history import SessionHistory
from crewai import Crew

_DEFAULT_LOG = str(Path.home() / ".secureflow" / "dev_session.log")


class DevOrchestrator:
    """Orchestrate collaborative development workflow with three agents."""

    def __init__(self, log_path: str = _DEFAULT_LOG):
        self.context = SharedContext()
        self.log_path = log_path
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        self.logger = self._init_logger()
        self.task: Optional[str] = None
        self.language: Optional[str] = None
        self.output_dir: Optional[str] = None

    def _init_logger(self) -> logging.Logger:
        """Initialize logger for session."""
        logger = logging.getLogger("DevCrew")
        logger.setLevel(logging.DEBUG)

        # File handler
        fh = logging.FileHandler(self.log_path)
        fh.setLevel(logging.DEBUG)

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)

        logger.addHandler(fh)
        logger.addHandler(ch)

        return logger

    def run_dev_crew(
        self,
        task: str,
        language: str,
        output_dir: str = "/tmp/dev_output"
    ) -> Dict[str, Any]:
        """Execute full development workflow (architect → developer → reviewer) as single Crew."""
        self.logger.info("🚀 Starting collaborative development crew")
        self.logger.info(f"Task: {task}")
        self.logger.info(f"Language: {language}")
        self.logger.info(f"Output: {output_dir}")

        self.task = task
        self.language = language
        self.output_dir = output_dir

        os.makedirs(output_dir, exist_ok=True)

        try:
            crew = create_dev_crew(task, language, output_dir)
            result = crew.kickoff()

            self.context.write("session", "result", str(result))
            self.context.write("session", "output_dir", output_dir)
            self.context.set_agent_status("session", "complete", "done")

            self.logger.info("=" * 80)
            self.logger.info("🎉 DEVELOPMENT WORKFLOW COMPLETE")
            self.logger.info("=" * 80)

            # Record in persistent history
            history = SessionHistory()
            summary = str(result)[:500] if result else "Development complete"
            history.record(
                session_type="development",
                target=f"{language}: {task[:100]}",
                status="success",
                summary=summary
            )

            return self._format_final_result(str(result), "success")

        except Exception as e:
            self.logger.error(f"Dev crew failed: {str(e)}", exc_info=True)

            # Record failed session in history
            history = SessionHistory()
            history.record(
                session_type="development",
                target=f"{language}: {task[:100]}",
                status="error",
                summary=f"Error: {str(e)[:500]}"
            )

            return self._format_final_result(str(e), "error")

    def run_code_review(self, code: str, language: str) -> Dict[str, Any]:
        """Execute quick code review workflow."""
        self.logger.info("🔍 Starting code review")
        self.logger.info(f"Language: {language}")
        self.logger.info(f"Code length: {len(code)} characters")

        try:
            tasks = create_code_review_tasks(code, language)
            reviewer = DevAgents.create_reviewer_agent()

            review_crew = Crew(
                agents=[reviewer],
                tasks=[tasks["review"]],
                verbose=True,
            )

            result = review_crew.kickoff()
            self.context.write("reviewer", "code_review", str(result))
            self.logger.info("✓ Code review complete")

            return {
                "status": "success",
                "result": str(result),
                "language": language,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Code review failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "language": language
            }

    def _format_final_result(self, result: str, status: str) -> Dict[str, Any]:
        """Format final result dict."""
        return {
            "status": status,
            "task": self.task,
            "language": self.language,
            "output_dir": self.output_dir,
            "result": result,
            "session_log": self.log_path,
            "message": "Development workflow complete" if status == "success" else "Development workflow failed",
            "timestamp": datetime.now().isoformat()
        }

    def export_session(self) -> str:
        """Export full session summary with all interactions."""
        summary = []
        summary.append("=" * 80)
        summary.append("DEVELOPMENT CREW SESSION EXPORT")
        summary.append("=" * 80)
        summary.append(f"Task: {self.task}")
        summary.append(f"Language: {self.language}")
        summary.append(f"Output: {self.output_dir}")
        summary.append("")

        # Export shared context
        context_summary = self.context.export_summary()
        summary.append("FINDINGS:")
        summary.append(context_summary)

        return "\n".join(summary)
