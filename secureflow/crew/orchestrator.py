"""
Crew orchestrator for collaborative multi-agent security assessment.
Manages agent communication, phases, and inter-agent dependencies.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from secureflow.crew.memory import SharedContext
from secureflow.crew.chat import AgentCommunicator
from crewai import Crew
from secureflow.crew.tasks import create_security_tasks, create_recon_tasks, create_crew
from secureflow.crew.agents import create_agents


class CrewOrchestrator:
    """Orchestrates multi-agent collaboration for security assessment."""

    def __init__(self, log_path: str = "/tmp/crew_session.log"):
        self.context = SharedContext()
        self.communicator = AgentCommunicator(self.context)
        self.log_path = log_path
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
        """Run full security crew with agent collaboration."""
        self.target = target
        self.context.clear()  # Fresh context for this crew run

        self.log("INFO", f"🚀 Starting security crew for target: {target}")
        self.log("INFO", "=" * 70)

        try:
            # Phase 1: Recon
            recon_result = self._run_recon_phase()
            if not recon_result["success"]:
                return {"success": False, "error": "Recon phase failed"}

            # Phase 2: Analysis
            analysis_result = self._run_analysis_phase()
            if not analysis_result["success"]:
                return {"success": False, "error": "Analysis phase failed"}

            # Phase 3: Reporting
            report_result = self._run_reporting_phase()
            if not report_result["success"]:
                return {"success": False, "error": "Reporting phase failed"}

            # Summary
            self.log("INFO", "=" * 70)
            self.log("INFO", "✅ Security crew completed successfully!")
            self.log("INFO", f"Session log: {self.log_path}")

            return {
                "success": True,
                "target": target,
                "recon": recon_result,
                "analysis": analysis_result,
                "report": report_result,
                "session_log": self.log_path,
            }

        except Exception as e:
            self.log("ERROR", f"Crew execution failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "session_log": self.log_path,
            }

    def _run_recon_phase(self) -> Dict[str, Any]:
        """Phase 1: Recon agent scans target and writes findings."""
        self.log("INFO", "\n📡 PHASE 1: RECONNAISSANCE")
        self.log("INFO", "-" * 70)

        self.context.set_agent_status("recon", "running", "discovery")
        self.communicator.broadcast_message(
            "recon",
            f"Starting reconnaissance on {self.target}",
        )

        try:
            # Create and execute recon tasks
            agents = create_agents()
            tasks = create_recon_tasks(self.target)

            # Create recon crew
            recon_crew = Crew(
                agents=[agents["recon"]],
                tasks=[tasks["recon"]],
                verbose=True,
            )

            # Execute recon
            recon_result = recon_crew.kickoff()
            self.log("INFO", f"Recon result: {str(recon_result)[:200]}")

            # Write findings to context
            self.context.write("recon", "target", self.target)
            self.context.write("recon", "scan_result", str(recon_result))
            self.context.write("recon", "timestamp", datetime.now().isoformat())

            self.context.set_agent_status("recon", "complete", "discovery")
            self.communicator.broadcast_message(
                "recon",
                "Reconnaissance complete. Findings written to shared context.",
            )

            self.log("INFO", "✅ Recon phase complete")

            return {
                "success": True,
                "phase": "recon",
                "findings": self.context.get_all("recon"),
            }

        except Exception as e:
            self.log("ERROR", f"Recon phase failed: {str(e)}")
            self.context.set_agent_status("recon", "failed", "discovery")
            return {"success": False, "error": str(e)}

    def _run_analysis_phase(self) -> Dict[str, Any]:
        """Phase 2: Analyst reads recon findings and performs analysis."""
        self.log("INFO", "\n🔍 PHASE 2: ANALYSIS")
        self.log("INFO", "-" * 70)

        self.context.set_agent_status("analyst", "running", "analysis")

        try:
            # Analyst reads recon findings
            recon_findings = self.context.get_all("recon")
            self.log("INFO", f"Analyst reading recon findings: {list(recon_findings.keys())}")

            # Send request to analyst
            question = (
                f"Analyze the reconnaissance findings from target {self.target}. "
                f"Review the scan results and identify vulnerabilities."
            )
            msg = self.communicator.send_message(
                "orchestrator",
                "analyst",
                question,
                requires_response=True,
            )

            # Create analysis tasks with context
            agents = create_agents()
            tasks = create_security_tasks(self.target)

            # Create analyst crew
            analysis_crew = Crew(
                agents=[agents["analyst"]],
                tasks=[tasks["analysis"]],
                verbose=True,
            )

            # Execute analysis
            analysis_result = analysis_crew.kickoff()

            self.log("INFO", f"Analysis result: {str(analysis_result)[:200]}")

            # Write findings to context
            self.context.write("analyst", "target", self.target)
            self.context.write("analyst", "analysis_result", str(analysis_result))
            self.context.write("analyst", "timestamp", datetime.now().isoformat())

            # Respond to orchestrator question
            self.communicator.respond_to_message(
                msg,
                f"Analysis complete. Identified vulnerabilities and risks.",
            )

            self.context.set_agent_status("analyst", "complete", "analysis")

            self.log("INFO", "✅ Analysis phase complete")

            return {
                "success": True,
                "phase": "analysis",
                "findings": self.context.get_all("analyst"),
            }

        except Exception as e:
            self.log("ERROR", f"Analysis phase failed: {str(e)}")
            self.context.set_agent_status("analyst", "failed", "analysis")
            return {"success": False, "error": str(e)}

    def _run_reporting_phase(self) -> Dict[str, Any]:
        """Phase 3: Reporter reads all findings and generates report."""
        self.log("INFO", "\n📊 PHASE 3: REPORTING")
        self.log("INFO", "-" * 70)

        self.context.set_agent_status("reporter", "running", "reporting")

        try:
            # Reporter reads all findings
            all_findings = self.context.get_latest_findings()
            self.log("INFO", f"Reporter reading findings from: {list(all_findings.keys())}")

            # Send request to reporter
            summary = "Summary of findings: "
            for agent, findings in all_findings.items():
                if findings:
                    summary += f"\n{agent}: {len(findings)} findings"

            question = (
                f"Create a comprehensive security report for {self.target} based on "
                f"the findings from recon and analysis phases. "
                f"{summary}"
            )

            msg = self.communicator.send_message(
                "orchestrator",
                "reporter",
                question,
                requires_response=True,
            )

            # Create reporting tasks
            agents = create_agents()
            tasks = create_security_tasks(self.target)

            # Create reporter crew
            reporter_crew = Crew(
                agents=[agents["reporter"]],
                tasks=[tasks["reporting"]],
                verbose=True,
            )

            # Execute reporting
            report_result = reporter_crew.kickoff()

            self.log("INFO", f"Report generated: {str(report_result)[:200]}")

            # Write findings to context
            self.context.write("reporter", "target", self.target)
            self.context.write("reporter", "report", str(report_result))
            self.context.write("reporter", "timestamp", datetime.now().isoformat())

            # Respond to orchestrator
            self.communicator.respond_to_message(
                msg,
                "Report generation complete. All findings documented.",
            )

            self.context.set_agent_status("reporter", "complete", "reporting")

            self.log("INFO", "✅ Reporting phase complete")

            return {
                "success": True,
                "phase": "reporting",
                "findings": self.context.get_all("reporter"),
            }

        except Exception as e:
            self.log("ERROR", f"Reporting phase failed: {str(e)}")
            self.context.set_agent_status("reporter", "failed", "reporting")
            return {"success": False, "error": str(e)}

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
