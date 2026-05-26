#!/usr/bin/env python3
import asyncio
import json
import logging
import os
from queue import Empty, Queue
from typing import Any

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import StreamingResponse

from secureflow.config import MCP_SECRET
from secureflow.crew.orchestrator import CrewOrchestrator
from secureflow.crew.dev_orchestrator import DevOrchestrator
from secureflow.crew.tasks import create_crew

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

        from secureflow.crew.tasks import create_recon_crew
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
            "security_crew_stream",
            "recon",
            "code_dev_crew",
            "code_review",
            "status"
        ],
        "auth_enabled": bool(MCP_SECRET),
        "message": "CrewAI Distributed Crew MCP Server is running"
    }


# --- Phase labels for progress reporting ---
_SECURITY_PHASES = ["Reconnaissance", "Vulnerability Analysis", "Report Generation"]


@app.tool()
async def run_security_crew_stream(target: str, ctx: Context) -> dict:
    """
    Execute full security crew with real-time MCP progress events.

    Emits progress notifications after each phase (recon, analysis, reporting).
    Use this tool when the MCP client supports streaming/progress events.

    Args:
        target: Target IP, hostname, or URL to assess

    Returns:
        dict with status, target, result
    """
    event_queue: Queue = Queue()
    phase_idx = [0]

    def _on_task_complete(_task_output) -> None:
        idx = phase_idx[0]
        label = _SECURITY_PHASES[idx] if idx < len(_SECURITY_PHASES) else f"Phase {idx + 1}"
        event_queue.put((label, idx + 1))
        phase_idx[0] += 1

    await ctx.info(f"Starting security assessment of {target}...")
    await ctx.report_progress(0, 3, "Initializing crew")

    loop = asyncio.get_running_loop()
    crew = create_crew(target, task_callback=_on_task_complete)
    future = loop.run_in_executor(None, crew.kickoff)

    while not future.done():
        await asyncio.sleep(0.5)
        while True:
            try:
                label, n = event_queue.get_nowait()
                await ctx.info(f"✅ {label} complete ({n}/{len(_SECURITY_PHASES)})")
                await ctx.report_progress(n, len(_SECURITY_PHASES), f"{label} complete")
            except Empty:
                break

    # drain any remaining events from the queue
    while not event_queue.empty():
        label, n = event_queue.get_nowait()
        await ctx.info(f"✅ {label} complete ({n}/{len(_SECURITY_PHASES)})")
        await ctx.report_progress(n, len(_SECURITY_PHASES), f"{label} complete")

    result = await future
    await ctx.info("✅ Security assessment complete!")

    return {
        "status": "success",
        "target": target,
        "result": str(result),
    }


@app.custom_route("/stream/{target:path}", methods=["GET"])
async def stream_scan_sse(request: Request) -> StreamingResponse:
    """
    HTTP SSE endpoint — streams security scan progress as Server-Sent Events.
    Testable with: curl -N http://localhost:5000/stream/<target>

    Events format: data: {"event": "<name>", ...}\\n\\n
    """
    target = request.path_params["target"]
    event_queue: Queue = Queue()
    phase_idx = [0]

    def _on_task_complete(_task_output) -> None:
        idx = phase_idx[0]
        label = _SECURITY_PHASES[idx] if idx < len(_SECURITY_PHASES) else f"Phase {idx + 1}"
        event_queue.put({"event": "phase_complete", "phase": label, "n": idx + 1, "total": 3})
        phase_idx[0] += 1

    loop = asyncio.get_running_loop()
    crew = create_crew(target, task_callback=_on_task_complete)
    future = loop.run_in_executor(None, crew.kickoff)

    async def _generate():
        yield f"data: {json.dumps({'event': 'start', 'target': target})}\n\n"

        while not future.done():
            await asyncio.sleep(0.5)
            while True:
                try:
                    payload = event_queue.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                except Empty:
                    break

        while not event_queue.empty():
            payload = event_queue.get_nowait()
            yield f"data: {json.dumps(payload)}\n\n"

        result = await future
        yield f"data: {json.dumps({'event': 'complete', 'result': str(result)[:500]})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

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

@app.custom_route("/ui", methods=["GET"])
async def serve_dashboard_root(request: Request):
    """Serve React dashboard root."""
    from starlette.responses import FileResponse
    from pathlib import Path

    # Serve built React app
    react_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if react_path.exists():
        return FileResponse(str(react_path), media_type="text/html")

    # Fallback to old HTML
    fallback_path = Path(__file__).parent / "static" / "index.html"
    if fallback_path.exists():
        return FileResponse(str(fallback_path), media_type="text/html")

    return FileResponse(
        status_code=404,
        content=b"Dashboard not found"
    )

@app.custom_route("/ui/", methods=["GET"])
async def serve_dashboard_root_slash(request: Request):
    """Serve React dashboard root with trailing slash."""
    from starlette.responses import FileResponse
    from pathlib import Path

    react_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if react_path.exists():
        return FileResponse(str(react_path), media_type="text/html")

    fallback_path = Path(__file__).parent / "static" / "index.html"
    if fallback_path.exists():
        return FileResponse(str(fallback_path), media_type="text/html")

    return FileResponse(status_code=404, content=b"Dashboard not found")

@app.custom_route("/ui/{path_remaining:path}", methods=["GET"])
async def serve_dashboard_assets(request: Request):
    """Serve React app assets and handle client-side routing."""
    from starlette.responses import FileResponse
    from pathlib import Path

    path = request.path_params.get("path_remaining", "")

    # Try to serve the exact file
    if path:
        asset_path = Path(__file__).parent / "static" / "dist" / path
        if asset_path.exists() and asset_path.is_file():
            return FileResponse(str(asset_path))

    # For client-side routing, serve index.html
    index_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")

    return FileResponse(status_code=404, content=b"Not found")

@app.custom_route("/api/history", methods=["GET"])
async def get_scan_history(request: Request):
    """Get scan history from persistent storage."""
    from starlette.responses import JSONResponse
    from secureflow.crew.history import SessionHistory

    try:
        history = SessionHistory()
        sessions = history.get_sessions(limit=50)

        return JSONResponse({
            "status": "success",
            "sessions": [
                {
                    "id": s.get("id"),
                    "target": s.get("target"),
                    "timestamp": s.get("started_at"),
                    "status": s.get("status"),
                    "summary": s.get("summary", "")[:200]
                }
                for s in sessions
            ]
        })
    except Exception as e:
        logger.error(f"History fetch failed: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

def main():
    """Run the FastMCP server on 0.0.0.0:5000 with SSE transport."""
    import asyncio

    logger.info("Starting CrewAI Security MCP Server...")
    logger.info(f"Auth enabled: {bool(MCP_SECRET)}")
    logger.info("Transport: SSE")
    logger.info("Host: 0.0.0.0")
    logger.info("Port: 5000")
    logger.info("Dashboard: http://localhost:5000/ui")

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
