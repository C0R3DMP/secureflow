#!/usr/bin/env python3
import asyncio
import hmac as _hmac
import json
import logging
import os
import socket
import uuid
from queue import Empty, Queue
from typing import Any

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import StreamingResponse

from secureflow.config import MCP_SECRET
from secureflow.crew.orchestrator import CrewOrchestrator
from secureflow.crew.dev_orchestrator import DevOrchestrator
from secureflow.crew.tasks import create_crew

# Active scan registry: scan_id → {status, target, result}
_active_scans: dict = {}
_ACTIVE_SCANS_MAX = 500


def _register_scan(scan_id: str, info: dict) -> None:
    """Add/update a scan entry, evicting oldest entries when limit is reached."""
    _active_scans[scan_id] = info
    if len(_active_scans) > _ACTIVE_SCANS_MAX:
        oldest = next(iter(_active_scans))
        _active_scans.pop(oldest, None)

# OpenCode process tracker for start/stop control
_opencode_process: Any = None

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

    if not _hmac.compare_digest(token, expected_token):
        raise AuthError("Invalid bearer token")

    return True


def _check_request_auth(request: Request):
    """Return JSONResponse(401) if auth fails, None if auth passes."""
    from starlette.responses import JSONResponse
    try:
        check_auth(request.headers.get("Authorization"))
        return None
    except AuthError as exc:
        return JSONResponse(status_code=401, content={"error": str(exc)})


@app.tool()
async def run_security_crew(target: str) -> dict:
    """
    Execute full collaborative security crew (recon + analysis + reporting) on target.

    Agents work as a team:
    1. Recon scans target and writes findings to shared context
    2. Analyst reads recon findings, performs analysis, asks questions
    3. Reporter reads all findings and generates comprehensive report

    Args:
        target: Target IP, hostname, or URL to assess

    Returns:
        dict with status, scan_id, findings, session log
    """
    scan_id = str(uuid.uuid4())
    _register_scan(scan_id, {"status": "running", "target": target})
    logger.info(f"🚀 Starting security crew for target: {target} (scan_id={scan_id})")

    try:
        orchestrator = CrewOrchestrator()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, orchestrator.run_security_crew, target)

        _register_scan(scan_id, {"status": "complete", "target": target})
        return {
            "status": "success" if result.get("success") else "error",
            "scan_id": scan_id,
            "target": target,
            "result": result,
            "session_log": orchestrator.log_path if result.get("success") else None,
            "message": "Collaborative security assessment complete" if result.get("success") else result.get("error", "Unknown error"),
        }

    except Exception as e:
        logger.error(f"Security crew failed: {str(e)}", exc_info=True)
        _register_scan(scan_id, {"status": "error", "target": target, "error": str(e)})
        return {
            "status": "error",
            "scan_id": scan_id,
            "target": target,
            "error": str(e),
            "message": "Security crew execution failed"
        }

@app.tool()
async def run_recon(target: str) -> dict:
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

        loop = asyncio.get_running_loop()
        crew = create_recon_crew(target)
        result = await loop.run_in_executor(None, crew.kickoff)

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

    try:
        result = await future
    except Exception as exc:
        logger.error(f"Security crew stream failed: {exc}", exc_info=True)
        await ctx.info(f"❌ Assessment failed: {exc}")
        return {"status": "error", "target": target, "error": str(exc)}

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
    from starlette.responses import JSONResponse
    from secureflow.crew.orchestrator import get_message_queue, clear_message_queue

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    target = request.path_params["target"]
    if not target or len(target) > 253:
        return JSONResponse(status_code=400, content={"error": "Invalid target"})

    # Get the global message queue from orchestrator
    msg_queue = get_message_queue()
    clear_message_queue()

    loop = asyncio.get_running_loop()

    # Run crew in executor (blocking operation in thread pool)
    def _run_crew():
        orchestrator = CrewOrchestrator()
        return orchestrator.run_security_crew(target)

    future = loop.run_in_executor(None, _run_crew)

    async def _generate():
        yield f"data: {json.dumps({'event': 'start', 'target': target})}\n\n"

        while not future.done():
            await asyncio.sleep(0.2)
            # Drain messages from the global queue
            while not msg_queue.empty():
                try:
                    payload = msg_queue.get_nowait()
                    yield f"data: {json.dumps(payload)}\n\n"
                except Empty:
                    break

        # Drain any remaining messages after crew completes
        while not msg_queue.empty():
            try:
                payload = msg_queue.get_nowait()
                yield f"data: {json.dumps(payload)}\n\n"
            except Empty:
                break

        result = await future

        # Emit report if available
        if result.get('report_html'):
            yield f"data: {json.dumps({'event': 'report_ready', 'report': result.get('report_html'), 'target': target})}\n\n"

        yield f"data: {json.dumps({'event': 'complete', 'result': result.get('message', 'Assessment complete')})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.tool()
async def run_dev_crew(task: str, language: str, output_dir: str = "/tmp/dev_output") -> dict:
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
        dict with status, scan_id, architecture, code, review findings, and output directory
    """
    from pathlib import Path
    _ALLOWED_OUTPUT_PREFIXES = ("/tmp/",)
    resolved_output = str(Path(output_dir).resolve())
    if not any(resolved_output.startswith(p) for p in _ALLOWED_OUTPUT_PREFIXES):
        return {
            "status": "error",
            "error": "output_dir must be under /tmp/",
            "message": "Invalid output directory"
        }

    scan_id = str(uuid.uuid4())
    _register_scan(scan_id, {"status": "running", "task": task})
    logger.info(f"🚀 Starting development crew for task: {task} (scan_id={scan_id})")

    try:
        orchestrator = DevOrchestrator()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, orchestrator.run_dev_crew, task, language, output_dir)

        _register_scan(scan_id, {"status": "complete", "task": task})
        return {
            "status": "success" if result.get("status") == "success" else "error",
            "scan_id": scan_id,
            "task": task,
            "language": language,
            "output_dir": output_dir,
            "result": result,
            "session_log": orchestrator.log_path if result.get("status") == "success" else None,
            "message": "Development crew workflow complete" if result.get("status") == "success" else result.get("error", "Unknown error"),
        }

    except Exception as e:
        logger.error(f"Development crew failed: {str(e)}", exc_info=True)
        _register_scan(scan_id, {"status": "error", "task": task, "error": str(e)})
        return {
            "status": "error",
            "scan_id": scan_id,
            "task": task,
            "language": language,
            "error": str(e),
            "message": "Development crew execution failed"
        }

@app.tool()
async def run_code_review(code: str, language: str) -> dict:
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
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, orchestrator.run_code_review, code, language)

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
    from starlette.responses import FileResponse, JSONResponse
    from pathlib import Path

    path = request.path_params.get("path_remaining", "")

    # Try to serve the exact file (with path traversal protection)
    if path:
        base_dir = (Path(__file__).parent / "static" / "dist").resolve()
        asset_path = (base_dir / path).resolve()
        # Ensure resolved path stays within static/dist
        if not str(asset_path).startswith(str(base_dir)):
            return JSONResponse(status_code=403, content={"error": "Forbidden"})
        if asset_path.exists() and asset_path.is_file():
            return FileResponse(str(asset_path))

    # For client-side routing, serve index.html
    index_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")

    return FileResponse(status_code=404, content=b"Not found")

@app.custom_route("/api/reports/export", methods=["GET"])
async def export_report(request: Request):
    """
    Export a completed scan report in the requested format.

    Query params:
      target  — exact target string used during the scan
      format  — html | pdf | json  (default: json)
    """
    from starlette.responses import FileResponse, JSONResponse
    from pathlib import Path
    from secureflow.reports import ReportExporter

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    target = request.query_params.get("target", "")
    fmt = request.query_params.get("format", "json").lower()

    if not target:
        return JSONResponse(status_code=400, content={"error": "target param required"})
    if fmt not in ("html", "pdf", "json"):
        return JSONResponse(status_code=400, content={"error": "format must be html, pdf, or json"})

    # Locate existing HTML report produced by orchestrator
    from pathlib import Path as _Path
    default_log_dir = _Path.home() / ".secureflow"
    stem = target.replace("/", "_").replace(":", "_").replace(" ", "_")
    html_path = default_log_dir / f"report_{stem}.html"

    # Build a minimal result dict so ReportExporter can work
    report_html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    result = {
        "success": bool(report_html),
        "result": report_html,
        "report_html": report_html,
        "report_path": str(html_path),
        "session_log": "",
    }

    try:
        exporter = ReportExporter()
        out_path = exporter.export(fmt, result, target)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    media_types = {"html": "text/html", "pdf": "application/pdf", "json": "application/json"}
    return FileResponse(
        path=out_path,
        media_type=media_types[fmt],
        filename=Path(out_path).name,
    )


def _is_port_open(url: str, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open (no HTTP auth needed)."""
    if not url:
        return False
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 4096
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def _get_providers_dict() -> dict:
    """Get status of all LLM providers (blocking — run in executor)."""
    import subprocess
    from secureflow.config import (
        is_claude_cli_available,
        is_ollama_available,
        GEMINI_API_KEY,
        OPENROUTER_API_KEY,
        ANTHROPIC_API_KEY,
        OPENCODE_URL,
        OPENCODE_SERVER_PASSWORD,
    )
    import requests

    providers = {}

    # Check Claude CLI
    if is_claude_cli_available():
        providers["claude"] = {"available": True, "mode": "cli"}
    elif ANTHROPIC_API_KEY:
        providers["claude"] = {"available": True, "mode": "api"}
    else:
        providers["claude"] = {"available": False}

    # Check Gemini API
    providers["gemini"] = {
        "available": bool(GEMINI_API_KEY),
        "mode": "api" if GEMINI_API_KEY else None
    }

    # Check OpenRouter
    providers["openrouter"] = {
        "available": bool(OPENROUTER_API_KEY),
        "mode": "api" if OPENROUTER_API_KEY else None
    }

    # Check Ollama
    providers["ollama"] = {
        "available": is_ollama_available(),
        "mode": "local"
    }

    # Check OpenCode — TCP connect check (bypasses HTTP auth issues)
    providers["opencode"] = {
        "available": _is_port_open(OPENCODE_URL),
        "mode": "local"
    }

    return providers


@app.custom_route("/api/providers", methods=["GET"])
async def get_providers_status(request: Request):
    """Get status of all LLM providers."""
    from starlette.responses import JSONResponse

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    try:
        loop = asyncio.get_running_loop()
        providers = await loop.run_in_executor(None, _get_providers_dict)
        return JSONResponse(providers)
    except Exception as e:
        logger.error(f"Provider status check failed: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "status": "error"}
        )


@app.custom_route("/api/scans/{scan_id}", methods=["GET"])
async def get_scan_status(request: Request):
    """Get status of a specific scan by scan_id."""
    from starlette.responses import JSONResponse

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    scan_id = request.path_params["scan_id"]
    info = _active_scans.get(scan_id)
    if info is None:
        return JSONResponse(status_code=404, content={"status": "not_found", "scan_id": scan_id})
    return JSONResponse({"scan_id": scan_id, **info})


@app.custom_route("/api/schedules", methods=["GET"])
async def get_schedules(request: Request):
    """List all scheduled scans."""
    from starlette.responses import JSONResponse

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    try:
        from secureflow.scheduler import get_manager
        jobs = get_manager().list_jobs()
        return JSONResponse({"status": "success", "schedules": jobs})
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.custom_route("/api/history", methods=["GET"])
async def get_scan_history(request: Request):
    """Get scan history from persistent storage."""
    from starlette.responses import JSONResponse
    from secureflow.crew.history import SessionHistory

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

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

@app.custom_route("/api/claude-cli-status", methods=["GET"])
async def check_claude_cli_status(request: Request):
    """Check if Claude CLI is available."""
    from starlette.responses import JSONResponse
    import subprocess

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            timeout=5,
            text=True
        )
        if result.returncode == 0:
            version = result.stdout.strip()
            return JSONResponse({
                "available": True,
                "version": version
            })
        else:
            return JSONResponse({
                "available": False,
                "version": None
            })
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"Claude CLI check failed: {str(e)}")
        return JSONResponse({
            "available": False,
            "version": None
        })

@app.custom_route("/api/opencode/start", methods=["POST"])
async def start_opencode_server(request: Request):
    """Start the OpenCode server on port 4096."""
    from starlette.responses import JSONResponse
    global _opencode_process

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    if _opencode_process is not None:
        return JSONResponse({"status": "already_running", "pid": _opencode_process.pid})

    if _is_port_open("http://127.0.0.1:4096"):
        return JSONResponse({"status": "already_running", "pid": -1})

    try:
        import subprocess
        from secureflow.config import OPENCODE_SERVER_PASSWORD
        _opencode_process = subprocess.Popen(
            ["opencode", "serve", "--port", "4096"],
            env={**os.environ, "OPENCODE_SERVER_PASSWORD": OPENCODE_SERVER_PASSWORD or "secureflow"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info(f"OpenCode started via API (PID: {_opencode_process.pid})")
        return JSONResponse({"status": "started", "pid": _opencode_process.pid})
    except FileNotFoundError:
        return JSONResponse(status_code=500, content={"status": "error", "message": "opencode not installed"})
    except Exception as e:
        logger.error(f"Failed to start OpenCode: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.custom_route("/api/opencode/stop", methods=["POST"])
async def stop_opencode_server(request: Request):
    """Stop the OpenCode server."""
    from starlette.responses import JSONResponse
    global _opencode_process

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    if _opencode_process is None:
        # Try to find and kill any opencode process on port 4096
        try:
            import subprocess
            subprocess.run(["pkill", "-f", "opencode.*4096"], check=False)
            return JSONResponse({"status": "stopped", "message": "Killed opencode processes on port 4096"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

    try:
        _opencode_process.terminate()
        try:
            _opencode_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _opencode_process.kill()
            _opencode_process.wait(timeout=2)
    except Exception as e:
        logger.error(f"Failed to stop OpenCode: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
    finally:
        _opencode_process = None
    return JSONResponse({"status": "stopped"})


@app.custom_route("/api/settings", methods=["POST"])
async def save_settings(request: Request):
    """Save provider settings to environment."""
    from starlette.responses import JSONResponse
    from pathlib import Path

    auth_err = _check_request_auth(request)
    if auth_err:
        return auth_err

    try:
        body = await request.json()

        def _sanitize(value: str) -> str:
            """Strip newlines and carriage returns to prevent .env injection."""
            return str(value).replace("\n", "").replace("\r", "").strip()

        # Extract and sanitize settings
        claude_key = _sanitize(body.get("claudeKey", ""))
        claude_mode = _sanitize(body.get("claudeMode", "api"))
        gemini_key = _sanitize(body.get("geminiKey", ""))
        gemini_model = _sanitize(body.get("geminiModel", "gemini-2.5-flash"))
        openrouter_key = _sanitize(body.get("openrouterKey", ""))
        openrouter_model = _sanitize(body.get("openrouterModel", ""))
        ollama_url = _sanitize(body.get("ollamaUrl", "http://localhost:11434"))

        # Update environment
        import os
        if claude_key:
            os.environ["ANTHROPIC_API_KEY"] = claude_key
        os.environ["CLAUDE_MODE"] = claude_mode
        if gemini_key:
            os.environ["GEMINI_API_KEY"] = gemini_key
        os.environ["GEMINI_MODEL"] = gemini_model
        if openrouter_key:
            os.environ["OPENROUTER_API_KEY"] = openrouter_key
        if openrouter_model:
            os.environ["OPENROUTER_MODEL"] = openrouter_model
        if ollama_url:
            os.environ["OLLAMA_BASE_URL"] = ollama_url

        # Try to update .env file
        env_path = Path.home() / ".secureflow" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        env_content = ""
        if claude_key:
            env_content += f"ANTHROPIC_API_KEY={claude_key}\n"
        env_content += f"CLAUDE_MODE={claude_mode}\n"
        if gemini_key:
            env_content += f"GEMINI_API_KEY={gemini_key}\n"
        env_content += f"GEMINI_MODEL={gemini_model}\n"
        if openrouter_key:
            env_content += f"OPENROUTER_API_KEY={openrouter_key}\n"
        if openrouter_model:
            env_content += f"OPENROUTER_MODEL={openrouter_model}\n"
        if ollama_url:
            env_content += f"OLLAMA_BASE_URL={ollama_url}\n"

        with open(env_path, "w") as f:
            f.write(env_content)

        logger.info(f"Settings saved to {env_path}")

        return JSONResponse({
            "status": "success",
            "message": "Settings saved successfully",
            "settings": {
                "claude_mode": claude_mode,
                "gemini_model": gemini_model,
                "ollama_url": ollama_url
            }
        })

    except Exception as e:
        logger.error(f"Failed to save settings: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

def main():
    """Run the FastMCP server on 0.0.0.0:5000 with SSE transport."""
    import asyncio
    import subprocess
    from secureflow.config import OPENCODE_SERVER_PASSWORD
    global _opencode_process

    logger.info("Starting CrewAI Security MCP Server...")
    logger.info(f"Auth enabled: {bool(MCP_SECRET)}")
    logger.info("Transport: SSE")
    logger.info("Host: 0.0.0.0")
    logger.info("Port: 5000")
    logger.info("Dashboard: http://localhost:5000/ui")

    # Auto-start OpenCode if available and not already running
    if _is_port_open(OPENCODE_URL or "http://127.0.0.1:4096"):
        logger.info("OpenCode already running on port 4096, skipping startup.")
    else:
        try:
            logger.info("Attempting to start OpenCode server...")
            _opencode_process = subprocess.Popen(
                ["opencode", "serve", "--port", "4096"],
                env={**os.environ, "OPENCODE_SERVER_PASSWORD": OPENCODE_SERVER_PASSWORD or "secureflow"},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            logger.info(f"OpenCode started (PID: {_opencode_process.pid})")
        except FileNotFoundError:
            logger.warning("OpenCode not installed. Continuing without OpenCode support.")
        except Exception as e:
            logger.warning(f"Failed to start OpenCode: {e}")

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
