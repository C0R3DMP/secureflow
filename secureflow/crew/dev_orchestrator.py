import logging
import os
from typing import Dict, Any, Optional
from datetime import datetime
from secureflow.crew.memory import SharedContext
from secureflow.crew.chat import AgentCommunicator
from secureflow.crew.tasks import create_dev_crew, create_code_review_crew
from crewai import Crew


class DevOrchestrator:
    """Orchestrate collaborative development workflow with three agents."""

    def __init__(self, log_path: str = "/tmp/dev_session.log"):
        self.context = SharedContext()
        self.communicator = AgentCommunicator(self.context)
        self.log_path = log_path
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

    def _run_architecture_phase(self) -> Dict[str, Any]:
        """Phase 1: Architecture Design."""
        self.logger.info("=" * 80)
        self.logger.info("PHASE 1: ARCHITECTURE DESIGN")
        self.logger.info("=" * 80)
        self.logger.info(f"Task: {self.task}")
        self.logger.info(f"Language: {self.language}")

        try:
            # Broadcast phase start
            self.communicator.broadcast_message(
                "DevOrchestrator",
                f"Starting architecture design phase for {self.language} project"
            )

            # Create lightweight crew for architecture design
            from secureflow.crew.tasks import create_dev_tasks
            from secureflow.crew.agents import DevAgents

            tasks = create_dev_tasks(self.task, self.language, self.output_dir)
            architect = DevAgents.create_architect_agent()

            architect_crew = Crew(
                agents=[architect],
                tasks=[tasks["architecture"]],
                verbose=True,
            )

            self.logger.info("Architecture crew created")
            result = architect_crew.kickoff()

            # Store architecture in shared context
            self.context.write("architect", "architecture", str(result))
            self.context.set_agent_status("architect", "complete", "phase_1")

            self.logger.info("✓ Architecture phase complete")
            self.logger.info("-" * 80)

            return {
                "status": "success",
                "phase": "architecture",
                "result": str(result),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Architecture phase failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "phase": "architecture",
                "error": str(e)
            }

    def _run_implementation_phase(self) -> Dict[str, Any]:
        """Phase 2: Code Implementation."""
        self.logger.info("=" * 80)
        self.logger.info("PHASE 2: CODE IMPLEMENTATION")
        self.logger.info("=" * 80)

        try:
            # Broadcast phase start and share architecture
            architecture = self.context.read("architect", "architecture")
            self.communicator.broadcast_message(
                "DevOrchestrator",
                f"Starting implementation phase. Architecture: {str(architecture)[:100]}..."
            )

            # Create developer crew
            from secureflow.crew.tasks import create_dev_tasks
            from secureflow.crew.agents import DevAgents

            tasks = create_dev_tasks(self.task, self.language, self.output_dir)
            architect = DevAgents.create_architect_agent()
            developer = DevAgents.create_developer_agent()

            dev_crew = Crew(
                agents=[developer],
                tasks=[tasks["implementation"]],
                verbose=True,
            )

            self.logger.info("Developer crew created")
            result = dev_crew.kickoff()

            # Store implementation in shared context
            self.context.write("developer", "implementation", str(result))
            self.context.write("developer", "output_dir", self.output_dir)
            self.context.set_agent_status("developer", "complete", "phase_2")

            self.logger.info("✓ Implementation phase complete")
            self.logger.info("-" * 80)

            return {
                "status": "success",
                "phase": "implementation",
                "result": str(result),
                "output_dir": self.output_dir,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Implementation phase failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "phase": "implementation",
                "error": str(e)
            }

    def _run_review_phase(self) -> Dict[str, Any]:
        """Phase 3: Code Review."""
        self.logger.info("=" * 80)
        self.logger.info("PHASE 3: CODE REVIEW")
        self.logger.info("=" * 80)

        try:
            # Broadcast phase start
            implementation = self.context.read("developer", "implementation")
            self.communicator.broadcast_message(
                "DevOrchestrator",
                f"Starting code review phase for {self.language} code"
            )

            # Create reviewer crew
            from secureflow.crew.tasks import create_dev_tasks
            from secureflow.crew.agents import DevAgents

            tasks = create_dev_tasks(self.task, self.language, self.output_dir)
            reviewer = DevAgents.create_reviewer_agent()

            review_crew = Crew(
                agents=[reviewer],
                tasks=[tasks["review"]],
                verbose=True,
            )

            self.logger.info("Reviewer crew created")
            result = review_crew.kickoff()

            # Store review in shared context
            self.context.write("reviewer", "review", str(result))
            self.context.set_agent_status("reviewer", "complete", "phase_3")

            self.logger.info("✓ Review phase complete")
            self.logger.info("-" * 80)

            return {
                "status": "success",
                "phase": "review",
                "result": str(result),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            self.logger.error(f"Review phase failed: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "phase": "review",
                "error": str(e)
            }

    def run_dev_crew(
        self,
        task: str,
        language: str,
        output_dir: str = "/tmp/dev_output"
    ) -> Dict[str, Any]:
        """Execute full three-phase development workflow."""
        self.logger.info("🚀 Starting collaborative development crew")
        self.logger.info(f"Task: {task}")
        self.logger.info(f"Language: {language}")
        self.logger.info(f"Output: {output_dir}")

        self.task = task
        self.language = language
        self.output_dir = output_dir

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        phases_results = []

        # Phase 1: Architecture Design
        architecture_result = self._run_architecture_phase()
        phases_results.append(architecture_result)
        if architecture_result["status"] != "success":
            self.logger.error("Architecture phase failed, stopping workflow")
            return self._format_final_result(phases_results, "error")

        # Phase 2: Implementation
        implementation_result = self._run_implementation_phase()
        phases_results.append(implementation_result)
        if implementation_result["status"] != "success":
            self.logger.error("Implementation phase failed, stopping workflow")
            return self._format_final_result(phases_results, "error")

        # Phase 3: Code Review
        review_result = self._run_review_phase()
        phases_results.append(review_result)

        # Summary
        self.logger.info("=" * 80)
        self.logger.info("🎉 DEVELOPMENT WORKFLOW COMPLETE")
        self.logger.info("=" * 80)

        return self._format_final_result(phases_results, "success")

    def run_code_review(self, code: str, language: str) -> Dict[str, Any]:
        """Execute quick code review workflow."""
        self.logger.info("🔍 Starting code review")
        self.logger.info(f"Language: {language}")
        self.logger.info(f"Code length: {len(code)} characters")

        try:
            from secureflow.crew.tasks import create_code_review_tasks
            from secureflow.crew.agents import DevAgents

            tasks = create_code_review_tasks(code, language)
            reviewer = DevAgents.create_reviewer_agent()

            review_crew = Crew(
                agents=[reviewer],
                tasks=[tasks["review"]],
                verbose=True,
            )

            self.logger.info("Code review crew created")
            result = review_crew.kickoff()

            # Store review in shared context
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

    def _format_final_result(
        self,
        phases_results: list,
        status: str
    ) -> Dict[str, Any]:
        """Format final result from all phases."""
        return {
            "status": status,
            "task": self.task,
            "language": self.language,
            "output_dir": self.output_dir,
            "phases": phases_results,
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
        summary.append("")

        # Export chat log
        chat_log = self.communicator.export_chat_log()
        summary.append("COMMUNICATION LOG:")
        summary.append(chat_log)

        return "\n".join(summary)
