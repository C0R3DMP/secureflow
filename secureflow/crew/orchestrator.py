"""
Crew orchestrator for collaborative multi-agent security assessment.
Manages agent communication, phases, and inter-agent dependencies.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from queue import Queue
from secureflow.crew.memory import SharedContext
from secureflow.crew.tasks import create_crew
from secureflow.crew.history import SessionHistory

_DEFAULT_LOG = str(Path.home() / ".secureflow" / "crew_session.log")

# Global message queue for SSE streaming
_message_queue: Queue = Queue()

def get_message_queue() -> Queue:
    """Get the global message queue for SSE streaming."""
    return _message_queue

def clear_message_queue() -> None:
    """Clear all messages from the queue."""
    while not _message_queue.empty():
        try:
            _message_queue.get_nowait()
        except:
            break


class CrewOrchestrator:
    """Orchestrates multi-agent collaboration for security assessment."""

    def __init__(self, log_path: str = _DEFAULT_LOG):
        self.context = SharedContext()
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
        clear_message_queue()

        self.log("INFO", f"🚀 Starting security crew for target: {target}")
        self.log("INFO", "=" * 70)

        try:
            def _on_step_complete(step) -> None:
                """Callback fired on each agent step for real-time streaming."""
                try:
                    agent_role = getattr(step, 'agent', None)
                    if agent_role:
                        agent_role = getattr(agent_role, 'role', str(agent_role)).lower()
                        if 'recon' in agent_role:
                            agent_role = 'recon'
                        elif 'analyst' in agent_role or 'analysis' in agent_role:
                            agent_role = 'analyst'
                        elif 'report' in agent_role:
                            agent_role = 'reporter'
                        else:
                            agent_role = 'system'
                    else:
                        agent_role = 'system'

                    step_text = str(step)[:300]
                    _message_queue.put({
                        'type': 'agent_message',
                        'agent': agent_role,
                        'message': step_text,
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    self.log("WARN", f"Error in step callback: {str(e)}")

            def _on_task_complete(task_output) -> None:
                """Callback fired when a task completes."""
                try:
                    agent_name = getattr(task_output, 'task', None)
                    if agent_name:
                        agent_name = str(agent_name).lower()
                        if 'recon' in agent_name:
                            agent_role = 'recon'
                        elif 'analyst' in agent_name or 'analysis' in agent_name:
                            agent_role = 'analyst'
                        elif 'report' in agent_name:
                            agent_role = 'reporter'
                        else:
                            agent_role = 'system'
                    else:
                        agent_role = 'system'

                    output_text = str(task_output.raw_output) if hasattr(task_output, 'raw_output') else str(task_output)
                    message = output_text[:500] if len(output_text) > 500 else output_text

                    _message_queue.put({
                        'type': 'agent_message',
                        'agent': agent_role,
                        'message': message,
                        'timestamp': datetime.now().isoformat()
                    })
                except Exception as e:
                    self.log("WARN", f"Error in task callback: {str(e)}")

            crew = create_crew(target, task_callback=_on_task_complete, step_callback=_on_step_complete)
            result = crew.kickoff()

            self.context.write("session", "target", target)
            self.context.write("session", "result", str(result))
            self.context.write("session", "timestamp", datetime.now().isoformat())

            self.log("INFO", "=" * 70)
            self.log("INFO", "✅ Security crew completed successfully!")
            self.log("INFO", f"Session log: {self.log_path}")

            # Extract report from crew result
            report_content = str(result)
            report_html = self._format_report(target, report_content)

            # Save report to file
            report_path = Path(self.log_path).parent / f"report_{target.replace('/', '_')}.html"
            with open(report_path, 'w') as f:
                f.write(report_html)
            self.log("INFO", f"Report saved to: {report_path}")

            # Record in persistent history
            history = SessionHistory()
            summary = report_content[:500] if report_content else "Assessment complete"
            history.record(
                session_type="security",
                target=target,
                status="success",
                summary=summary
            )

            from secureflow.notifications import NotificationDispatcher
            NotificationDispatcher().dispatch(
                event="scan_complete",
                target=target,
                status="success",
                summary=summary,
                report_path=str(report_path),
            )

            return {
                "success": True,
                "target": target,
                "result": report_content,
                "report_html": report_html,
                "report_path": str(report_path),
                "session_log": self.log_path,
            }

        except Exception as e:
            self.log("ERROR", f"Crew execution failed: {str(e)}")

            history = SessionHistory()
            history.record(
                session_type="security",
                target=target,
                status="error",
                summary=f"Error: {str(e)[:500]}"
            )

            from secureflow.notifications import NotificationDispatcher
            NotificationDispatcher().dispatch(
                event="scan_failed",
                target=target,
                status="error",
                summary=str(e)[:500],
            )

            return {
                "success": False,
                "error": str(e),
                "session_log": self.log_path,
            }

    def _format_report(self, target: str, content: str) -> str:
        """Format crew output as professional HTML report."""
        import html
        from datetime import datetime
        content = html.escape(content)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SecureFlow Security Assessment Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f1419;
            color: #e0e6ed;
            line-height: 1.6;
            padding: 20px;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; background: #1a1f2e; border-radius: 8px; overflow: hidden; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 40px; color: white; }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; font-size: 14px; }}
        .meta {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; padding: 30px; border-bottom: 1px solid #2a3548; }}
        .meta-item h3 {{ font-size: 12px; opacity: 0.6; text-transform: uppercase; margin-bottom: 5px; }}
        .meta-item p {{ font-size: 14px; }}
        .content {{ padding: 30px; }}
        .section {{ margin-bottom: 30px; }}
        .section h2 {{ font-size: 18px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }}
        .section h3 {{ font-size: 14px; margin: 15px 0 8px 0; color: #a0aec0; }}
        .section p {{ margin-bottom: 10px; }}
        pre {{ background: #0f1419; padding: 15px; border-radius: 5px; overflow-x: auto; font-size: 12px; margin: 10px 0; }}
        .footer {{ padding: 20px 30px; background: #111820; border-top: 1px solid #2a3548; font-size: 12px; opacity: 0.7; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔒 Security Assessment Report</h1>
            <p>SecureFlow AI — Professional Security Analysis</p>
        </div>

        <div class="meta">
            <div class="meta-item">
                <h3>Target</h3>
                <p>{target}</p>
            </div>
            <div class="meta-item">
                <h3>Assessment Date</h3>
                <p>{timestamp}</p>
            </div>
        </div>

        <div class="content">
            <div class="section">
                <h2>Executive Summary</h2>
                <p>Comprehensive security assessment completed using automated reconnaissance, vulnerability analysis, and professional reporting workflow.</p>
            </div>

            <div class="section">
                <h2>Assessment Results</h2>
                <h3>Detailed Findings</h3>
                <pre>{content}</pre>
            </div>

            <div class="section">
                <h2>Recommendations</h2>
                <p>Review the detailed findings above and prioritize remediation based on severity and exploitability.</p>
            </div>
        </div>

        <div class="footer">
            <p>SecureFlow AI Report • Generated {timestamp} • Automated Security Assessment</p>
        </div>
    </div>
</body>
</html>"""

        return html

    def export_session(self) -> str:
        """Export full session summary."""
        summary = f"SESSION SUMMARY: {self.target}\n"
        summary += f"Log: {self.log_path}\n"
        summary += f"Started: {datetime.now().isoformat()}\n\n"

        summary += self.context.export_summary()

        return summary
