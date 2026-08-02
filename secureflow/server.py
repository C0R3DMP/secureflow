#!/usr/bin/env python3
import asyncio
import json
import logging
import os
import socket
import uuid
from collections import OrderedDict
from queue import Empty, Queue
from typing import Any

from fastmcp import Context, FastMCP
from starlette.requests import Request
from starlette.responses import StreamingResponse

from secureflow import config
from secureflow.config import MCP_SECRET
from secureflow.crew.orchestrator import CrewOrchestrator
from secureflow.crew.dev_orchestrator import DevOrchestrator
from secureflow.crew.tasks import create_crew
from secureflow.security import (
    BearerAuthMiddleware,
    InvalidTarget,
    generate_token,
    report_stem,
    safe_join,
    validate_target,
)

__version__ = "0.1.0"

# Active scan registry: scan_id → {status, target, result}. Bounded — an
# unbounded dict grows for the lifetime of the process, one entry per scan.
MAX_TRACKED_SCANS = 500
_active_scans: "OrderedDict[str, dict]" = OrderedDict()

# OpenCode process tracker for start/stop control
_opencode_process: Any = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastMCP("secureflow-crew")


class AuthError(Exception):
    """Raised when MCP authentication fails."""
    pass


def _record_scan(scan_id: str, info: dict) -> None:
    """Record scan state, evicting the oldest entries past MAX_TRACKED_SCANS."""
    _active_scans[scan_id] = info
    _active_scans.move_to_end(scan_id)
    while len(_active_scans) > MAX_TRACKED_SCANS:
        _active_scans.popitem(last=False)


def _invalid_target_result(target: Any, exc: Exception, **extra) -> dict:
    """Uniform error payload for a rejected scan target."""
    logger.warning(f"Rejected invalid target {target!r}: {exc}")
    return {
        "status": "error",
        "target": str(target),
        "error": str(exc),
        "message": "Invalid target",
        **extra,
    }

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

    try:
        target = validate_target(target)
    except InvalidTarget as exc:
        return _invalid_target_result(target, exc, scan_id=scan_id)

    _record_scan(scan_id, {"status": "running", "target": target})
    logger.info(f"🚀 Starting security crew for target: {target} (scan_id={scan_id})")

    try:
        orchestrator = CrewOrchestrator()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, orchestrator.run_security_crew, target)

        _record_scan(scan_id, {"status": "complete", "target": target})
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
        _record_scan(scan_id, {"status": "error", "target": target, "error": str(e)})
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
        target = validate_target(target)
    except InvalidTarget as exc:
        return _invalid_target_result(target, exc)

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
        "version": __version__,
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
    try:
        target = validate_target(target)
    except InvalidTarget as exc:
        return _invalid_target_result(target, exc)

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

    # crew.kickoff() raises directly (there is no orchestrator wrapper on this
    # path), so a failed run — e.g. no LLM provider reachable — must be
    # reported through the MCP error channel rather than left to propagate as
    # an unhandled exception out of a @app.tool() call.
    try:
        result = await future
    except Exception as exc:
        logger.error(f"Security crew stream failed: {exc}", exc_info=True)
        await ctx.error(f"Security assessment failed: {exc}")
        return {
            "status": "error",
            "target": target,
            "error": str(exc),
            "message": "Security assessment failed",
        }

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

    raw_target = request.path_params["target"]
    try:
        target = validate_target(raw_target)
    except InvalidTarget as exc:
        logger.warning(f"Rejected invalid stream target {raw_target!r}: {exc}")
        return JSONResponse(status_code=400, content={"error": "invalid target", "detail": str(exc)})

    # Each scan owns its queue — a single process-wide queue let concurrent
    # scans consume each other's events.
    orchestrator = CrewOrchestrator()
    msg_queue = orchestrator.message_queue

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, orchestrator.run_security_crew, target)

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

        # run_security_crew()'s failure branch returns {"success": False,
        # "error": ...} with no "message" key, so result.get('message', ...)
        # previously always fell through to a hardcoded default and reported
        # "Assessment complete" even when the crew never ran — e.g. because no
        # LLM provider was reachable. Verified live: a scan with no provider
        # configured showed all three phases green with zero agent messages
        # and no report. Surface the real failure instead.
        if result.get('success'):
            message = result.get('message', 'Assessment complete')
            yield f"data: {json.dumps({'event': 'complete', 'result': message})}\n\n"
        else:
            error = result.get('error', 'Assessment failed for an unknown reason')
            yield f"data: {json.dumps({'event': 'error', 'message': error})}\n\n"

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
    scan_id = str(uuid.uuid4())
    _active_scans[scan_id] = {"status": "running", "task": task}
    logger.info(f"🚀 Starting development crew for task: {task} (scan_id={scan_id})")

    try:
        orchestrator = DevOrchestrator()
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, orchestrator.run_dev_crew, task, language, output_dir)

        _active_scans[scan_id] = {"status": "complete", "task": task}
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
        _active_scans[scan_id] = {"status": "error", "task": task, "error": str(e)}
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
    from starlette.responses import FileResponse, PlainTextResponse
    from pathlib import Path

    # Serve built React app
    react_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if react_path.exists():
        return FileResponse(str(react_path), media_type="text/html")

    # Fallback to old HTML
    fallback_path = Path(__file__).parent / "static" / "index.html"
    if fallback_path.exists():
        return FileResponse(str(fallback_path), media_type="text/html")

    # FileResponse takes a path, not a body — the old FileResponse(status_code=,
    # content=) call raised TypeError (HTTP 500) instead of returning a 404.
    return PlainTextResponse("Dashboard not found. Run ./setup-frontend.sh to build it.", status_code=404)

@app.custom_route("/ui/", methods=["GET"])
async def serve_dashboard_root_slash(request: Request):
    """Serve React dashboard root with trailing slash."""
    from starlette.responses import FileResponse, PlainTextResponse
    from pathlib import Path

    react_path = Path(__file__).parent / "static" / "dist" / "index.html"
    if react_path.exists():
        return FileResponse(str(react_path), media_type="text/html")

    fallback_path = Path(__file__).parent / "static" / "index.html"
    if fallback_path.exists():
        return FileResponse(str(fallback_path), media_type="text/html")

    return PlainTextResponse("Dashboard not found. Run ./setup-frontend.sh to build it.", status_code=404)

@app.custom_route("/ui/{path_remaining:path}", methods=["GET"])
async def serve_dashboard_assets(request: Request):
    """Serve React app assets and handle client-side routing."""
    from starlette.responses import FileResponse, PlainTextResponse
    from pathlib import Path

    path = request.path_params.get("path_remaining", "")
    dist_root = Path(__file__).parent / "static" / "dist"

    # Try to serve the exact file. safe_join rejects any path that escapes the
    # dist directory — joining the raw param allowed '..%2f' traversal and
    # served arbitrary files off the host filesystem.
    if path:
        asset_path = safe_join(dist_root, path)
        if asset_path is None:
            logger.warning(f"Blocked path traversal attempt: /ui/{path!r}")
            from starlette.responses import PlainTextResponse
            return PlainTextResponse("Not found", status_code=404)
        if asset_path.exists() and asset_path.is_file():
            return FileResponse(str(asset_path))

    # For client-side routing, serve index.html
    index_path = dist_root / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path), media_type="text/html")

    return PlainTextResponse("Not found", status_code=404)

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

    target = request.query_params.get("target", "")
    fmt = request.query_params.get("format", "json").lower()

    if not target:
        return JSONResponse(status_code=400, content={"error": "target param required"})
    if fmt not in ("html", "pdf", "json", "sarif"):
        return JSONResponse(status_code=400, content={"error": "format must be html, pdf, json, or sarif"})

    try:
        target = validate_target(target)
    except InvalidTarget as exc:
        return JSONResponse(status_code=400, content={"error": "invalid target", "detail": str(exc)})

    # Locate existing HTML report produced by orchestrator. Both sides derive the
    # filename from security.report_stem; hand-rolling the sanitisation here made
    # export miss any report whose target contained ':' or a space.
    default_log_dir = Path.home() / ".secureflow"
    html_path = default_log_dir / f"report_{report_stem(target)}.html"

    if not html_path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "no report found for target", "target": target},
        )

    # Build a minimal result dict so ReportExporter can work. The prose report
    # only exists as a saved HTML file, but structured findings are persisted
    # separately in SessionHistory (recorded by the orchestrator at scan
    # completion) — pull those in too so a JSON/SARIF export of a *past* scan
    # isn't limited to the live-scan-only fields the exporter also accepts.
    from secureflow.crew.history import SessionHistory

    report_html = html_path.read_text(encoding="utf-8")
    session = SessionHistory().get_latest_for_target(target, session_type="security")
    result = {
        "success": bool(report_html),
        "result": report_html,
        "report_html": report_html,
        "report_path": str(html_path),
        "session_log": "",
        "findings": session["findings"] if session else [],
    }

    try:
        exporter = ReportExporter()
        out_path = exporter.export(fmt, result, target)
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

    media_types = {
        "html": "text/html",
        "pdf": "application/pdf",
        "json": "application/json",
        "sarif": "application/sarif+json",
    }
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
    from secureflow import quota
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

    # Best-effort, locally-tracked request budget — see secureflow/quota.py.
    # Verified live: a Gemini free-tier key's *daily* quota (separate from the
    # well-known 5/min limit) was exhausted by a single scan, with the raw
    # 429 the only signal it ever happened. Surface whatever this process has
    # observed so far, clearly marked as an estimate.
    #
    # litellm's model prefix ("anthropic") differs from this dict's provider
    # key ("claude") for that one entry; every other key already matches.
    quota_keys = {"gemini": "gemini", "openrouter": "openrouter", "ollama": "ollama", "claude": "anthropic"}
    for provider_key, quota_key in quota_keys.items():
        if provider_key in providers:
            providers[provider_key]["quota"] = quota.snapshot(quota_key)

    return providers


@app.custom_route("/api/providers", methods=["GET"])
async def get_providers_status(request: Request):
    """Get status of all LLM providers."""
    from starlette.responses import JSONResponse

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

    scan_id = request.path_params["scan_id"]
    info = _active_scans.get(scan_id)
    if info is None:
        return JSONResponse(status_code=404, content={"status": "not_found", "scan_id": scan_id})
    return JSONResponse({"scan_id": scan_id, **info})


@app.custom_route("/api/schedules", methods=["GET"])
async def get_schedules(request: Request):
    """List all scheduled scans."""
    from starlette.responses import JSONResponse
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
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
    import subprocess

    from starlette.responses import JSONResponse
    global _opencode_process

    if _opencode_process is None:
        # Only processes this server started are ours to stop. The previous
        # `pkill -f "opencode.*4096"` matched on any user's command line and
        # could kill unrelated processes.
        return JSONResponse({
            "status": "not_running",
            "message": "No OpenCode process was started by this server",
        })

    try:
        _opencode_process.terminate()
        try:
            _opencode_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("OpenCode did not exit in 5s — sending SIGKILL")
            _opencode_process.kill()
            _opencode_process.wait(timeout=5)
        _opencode_process = None
        return JSONResponse({"status": "stopped"})
    except Exception as e:
        logger.error(f"Failed to stop OpenCode: {e}")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})


@app.custom_route("/api/chat", methods=["POST"])
async def chat(request: Request):
    """Stream a chat reply from the configured LLM as Server-Sent Events.

    Body: {"messages": [{"role": "user"|"assistant", "content": str}, ...],
           "target": optional str — pulls that scan's findings in as context}

    Events: {"type":"token","text":...} · {"type":"done"} · {"type":"error","message":...}
    """
    from starlette.responses import JSONResponse

    from secureflow.chat import (
        ChatError,
        NoProviderConfigured,
        normalise_history,
        scan_context_for,
        stream_reply,
    )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "body must be valid JSON"})

    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "body must be a JSON object"})

    try:
        messages = normalise_history(body.get("messages"))
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    # Optional grounding in a specific scan's results.
    context = None
    raw_target = body.get("target")
    if raw_target:
        try:
            context = scan_context_for(validate_target(str(raw_target)))
        except InvalidTarget as exc:
            return JSONResponse(
                status_code=400, content={"error": "invalid target", "detail": str(exc)}
            )

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    _SENTINEL = object()

    def _produce() -> None:
        """Consume the blocking litellm stream on a worker thread."""
        try:
            for chunk in stream_reply(messages, context=context):
                loop.call_soon_threadsafe(queue.put_nowait, ("token", chunk))
        except NoProviderConfigured as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
        except ChatError as exc:
            loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))
        except Exception as exc:  # unexpected — surface rather than hang
            logger.error(f"Chat stream failed: {exc}", exc_info=True)
            loop.call_soon_threadsafe(queue.put_nowait, ("error", f"Unexpected error: {exc}"))
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    async def _generate():
        loop.run_in_executor(None, _produce)
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            kind, payload = item
            if kind == "token":
                yield f"data: {json.dumps({'type': 'token', 'text': payload})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': payload})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.custom_route("/api/settings", methods=["POST"])
async def save_settings(request: Request):
    """Save provider settings to environment."""
    from starlette.responses import JSONResponse
    from pathlib import Path

    try:
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"status": "error", "message": "body must be a JSON object"})

        # Map request fields → env var names. Only keys actually present in the
        # request are touched: the previous version rebuilt the whole file from
        # defaults, so saving one provider silently erased the others' keys.
        field_map = {
            "claudeKey": "ANTHROPIC_API_KEY",
            "claudeMode": "CLAUDE_MODE",
            "geminiKey": "GEMINI_API_KEY",
            "geminiModel": "GEMINI_MODEL",
            "openrouterKey": "OPENROUTER_API_KEY",
            "openrouterModel": "OPENROUTER_MODEL",
            "ollamaUrl": "OLLAMA_BASE_URL",
        }

        updates = {}
        for field, env_var in field_map.items():
            if field not in body:
                continue
            value = body[field]
            if value is None:
                continue
            value = str(value).strip()
            # Reject newlines: they would let one field inject extra .env lines.
            if "\n" in value or "\r" in value:
                return JSONResponse(
                    status_code=400,
                    content={"status": "error", "message": f"{field} must not contain newlines"},
                )
            updates[env_var] = value

        if not updates:
            return JSONResponse(status_code=400, content={"status": "error", "message": "no known settings supplied"})

        env_path = Path.home() / ".secureflow" / ".env"
        env_path.parent.mkdir(parents=True, exist_ok=True)

        # Merge with whatever is already on disk rather than overwriting.
        existing: dict = {}
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                existing[key.strip()] = val.strip()
        existing.update(updates)

        env_path.write_text(
            "".join(f"{k}={v}\n" for k, v in sorted(existing.items())),
            encoding="utf-8",
        )
        # API keys live in this file — keep it owner-only.
        os.chmod(env_path, 0o600)

        # Apply in-process. Writing os.environ alone was a no-op: config's
        # module-level constants were captured at import and never re-read.
        os.environ.update(updates)
        config.reload_settings()

        logger.info(f"Settings saved to {env_path}: {sorted(updates)}")

        return JSONResponse({
            "status": "success",
            "message": "Settings saved successfully",
            "updated": sorted(updates.keys()),
        })

    except Exception as e:
        logger.error(f"Failed to save settings: {str(e)}")
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )

def resolve_auth_secret() -> str:
    """Determine the bearer secret the server will enforce.

    A penetration-testing server that runs unauthenticated is a remote scanning
    proxy for anyone who can reach the port, so "no secret configured" must not
    mean "no auth". If MCP_SECRET is unset we mint an ephemeral one and print it,
    unless the operator explicitly opts out with SECUREFLOW_ALLOW_ANONYMOUS=1.
    """
    secret = os.getenv("MCP_SECRET", "") or MCP_SECRET
    if secret:
        return secret

    if os.getenv("SECUREFLOW_ALLOW_ANONYMOUS", "").lower() in ("1", "true", "yes"):
        logger.warning(
            "SECUREFLOW_ALLOW_ANONYMOUS is set — the API is UNAUTHENTICATED. "
            "Anyone who can reach this port can launch scans against arbitrary targets."
        )
        return ""

    secret = generate_token()
    os.environ["MCP_SECRET"] = secret
    config.reload_settings()
    logger.warning("MCP_SECRET was not set — generated an ephemeral token for this run:")
    logger.warning("    MCP_SECRET=%s", secret)
    logger.warning("    Use it as: Authorization: Bearer %s   (or ?token=... for SSE)", secret)
    logger.warning("    Set MCP_SECRET in your .env to keep a stable token across restarts.")
    return secret


def main():
    """Run the FastMCP server with SSE transport."""
    import asyncio
    import subprocess

    # OPENCODE_URL is read below; importing only OPENCODE_SERVER_PASSWORD here
    # made `secureflow server` die with NameError before it ever bound a port.
    from secureflow.config import OPENCODE_SERVER_PASSWORD, OPENCODE_URL
    global _opencode_process

    secret = resolve_auth_secret()

    # Default to loopback. Binding 0.0.0.0 exposes the scanning API to the whole
    # network; opt in explicitly via SECUREFLOW_HOST when that is intended.
    host = os.getenv("SECUREFLOW_HOST", "127.0.0.1")
    try:
        port = int(os.getenv("SECUREFLOW_PORT", "5000"))
    except ValueError:
        logger.warning("Invalid SECUREFLOW_PORT, falling back to 5000")
        port = 5000

    logger.info("Starting CrewAI Security MCP Server...")
    logger.info(f"Auth enabled: {bool(secret)}")
    logger.info("Transport: SSE")
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Dashboard: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/ui")
    if host == "0.0.0.0" and not secret:
        logger.error(
            "Refusing configuration guidance: bound to all interfaces with auth disabled. "
            "Set MCP_SECRET before exposing this server."
        )

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

    from starlette.middleware import Middleware

    # Auth is enforced here, as ASGI middleware in front of every route —
    # including the MCP transport endpoints. The previous check_auth() helper
    # was never called from anywhere, so MCP_SECRET had no effect at all.
    middleware = [Middleware(BearerAuthMiddleware, secret=secret)] if secret else []

    asyncio.run(
        app.run_http_async(
            host=host,
            port=port,
            transport="sse",
            log_level="info",
            middleware=middleware,
        )
    )

if __name__ == "__main__":
    main()
