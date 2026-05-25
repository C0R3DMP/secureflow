#!/usr/bin/env python3
import json
import logging
import os
from typing import Any
from fastmcp import FastMCP
from secureflow.config import validate_mcp_secret, MCP_SECRET
from secureflow.crew.orchestrator import CrewOrchestrator
from secureflow.crew.dev_orchestrator import DevOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not MCP_SECRET:
    logger.warning("MCP_SECRET env var not set! Auth disabled (insecure).")

app = FastMCP("secureflow-crew")

class AuthError(Exception):
    """Raised when MCP authentication fails."""
    pass

def check_auth(auth_header: str = None) -> bool:
    """Validate bearer token authentication."""
    if not MCP_SECRET:
        return True

    if not auth_header:
        raise AuthError("Missing Authorization header")

    if not auth_header.startswith("Bearer "):
        raise AuthError("Invalid Authorization header format")

    token = auth_header[7:]
    expected_token = MCP_SECRET

    if token != expected_token:
        raise AuthError("Invalid bearer token")

    return True

@app.tool()
def run_security_crew(target: str) -> dict:
    """
    Execute full collaborative security crew (recon + analysis + reporting) on target.

    Agents work as a team:
    1. Recon scans target and writes findings to shared context
    2. Analyst reads recon findings, performs analysis, asks questions
    3. Reporter reads all findings and generates comprehensive report

    Args:
        target: Target IP, hostname, or URL to assess

    Returns:
        dict with status, findings, session log
    """
    try:
        logger.info(f"🚀 Starting collaborative security crew for target: {target}")

        # Create orchestrator for coordinated multi-agent execution
        orchestrator = CrewOrchestrator()

        # Run the collaborative crew
        result = orchestrator.run_security_crew(target)

        # Try to send Telegram notification if configured
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if telegram_token and telegram_chat_id:
            orchestrator.send_notification(telegram_token, telegram_chat_id)

        return {
            "status": "success" if result.get("success") else "error",
            "target": target,
            "result": result,
            "session_log": orchestrator.log_path if result.get("success") else None,
            "message": "Collaborative security assessment complete" if result.get("success") else result.get("error", "Unknown error"),
        }

    except Exception as e:
        logger.error(f"Security crew failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "target": target,
            "error": str(e),
            "message": "Security crew execution failed"
        }

@app.tool()
def run_recon(target: str) -> dict:
    """
    Execute recon-only crew (fast network scan) on target.
    Useful for quick network discovery without full analysis.

    Args:
        target: Target IP, hostname, or URL to scan

    Returns:
        dict with recon findings
    """
    try:
        logger.info(f"📡 Starting fast recon for target: {target}")

        from crew.tasks import create_recon_crew
        from crewai import Crew

        crew = create_recon_crew(target)
        result = crew.kickoff()

        logger.info(f"✅ Recon complete for {target}")

        return {
            "status": "success",
            "target": target,
            "result": str(result),
            "message": "Fast recon complete"
        }

    except Exception as e:
        logger.error(f"Recon crew failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "target": target,
            "error": str(e),
            "message": "Recon execution failed"
        }

@app.tool()
def crew_status() -> dict:
    """
    Health check endpoint. Returns server status and configuration.

    Returns:
        dict with server status and capabilities
    """
    return {
        "status": "healthy",
        "version": "1.0.0",
        "capabilities": [
            "security_crew",
            "recon",
            "code_dev_crew",
            "code_review",
            "status"
        ],
        "auth_enabled": bool(MCP_SECRET),
        "message": "CrewAI Distributed Crew MCP Server is running"
    }

@app.tool()
def run_dev_crew(task: str, language: str, output_dir: str = "/tmp/dev_output") -> dict:
    """
    Execute full development crew (architect + developer + reviewer) to build an app.

    Three-phase collaborative workflow:
    1. Architect designs system architecture and tech stack
    2. Developer implements the application code
    3. Reviewer checks code quality and suggests improvements

    Args:
        task: Detailed description of what application to build
        language: Programming language (python, javascript, go, rust, typescript, etc.)
        output_dir: Directory where generated files will be saved (default: /tmp/dev_output)

    Returns:
        dict with status, architecture, code, review findings, and output directory
    """
    try:
        logger.info(f"🚀 Starting development crew for task: {task}")

        orchestrator = DevOrchestrator()
        result = orchestrator.run_dev_crew(task, language, output_dir)

        return {
            "status": "success" if result.get("status") == "success" else "error",
            "task": task,
            "language": language,
            "output_dir": output_dir,
            "result": result,
            "session_log": orchestrator.log_path if result.get("status") == "success" else None,
            "message": "Development crew workflow complete" if result.get("status") == "success" else result.get("error", "Unknown error"),
        }

    except Exception as e:
        logger.error(f"Development crew failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "task": task,
            "language": language,
            "error": str(e),
            "message": "Development crew execution failed"
        }

@app.tool()
def run_code_review(code: str, language: str) -> dict:
    """
    Review existing code for quality, bugs, and improvements.

    Uses specialist code reviewer agent to analyze code and suggest improvements.

    Args:
        code: Source code to review
        language: Programming language (python, javascript, go, rust, typescript, etc.)

    Returns:
        dict with review findings, quality score, and improvement suggestions
    """
    try:
        logger.info(f"🔍 Starting code review for {language}")

        orchestrator = DevOrchestrator()
        result = orchestrator.run_code_review(code, language)

        return {
            "status": "success" if result.get("status") == "success" else "error",
            "language": language,
            "code_length": len(code),
            "result": result,
            "message": "Code review complete" if result.get("status") == "success" else result.get("error", "Unknown error"),
        }

    except Exception as e:
        logger.error(f"Code review failed: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "language": language,
            "error": str(e),
            "message": "Code review execution failed"
        }

def main():
    """Run the FastMCP server on 0.0.0.0:5000 with SSE transport."""
    import asyncio

    logger.info("Starting CrewAI Security MCP Server...")
    logger.info(f"Auth enabled: {bool(MCP_SECRET)}")
    logger.info("Transport: SSE")
    logger.info("Host: 0.0.0.0")
    logger.info("Port: 5000")

    asyncio.run(
        app.run_http_async(
            host="0.0.0.0",
            port=5000,
            transport="sse",
            log_level="info"
        )
    )

if __name__ == "__main__":
    main()
