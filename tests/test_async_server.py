"""Tests for M8: non-blocking async server tools."""

import asyncio
import uuid
from unittest.mock import MagicMock, patch


def test_server_tools_are_async():
    """All long-running tools must be async coroutines."""
    import inspect
    from secureflow.server import run_security_crew, run_dev_crew, run_recon, run_code_review

    assert inspect.iscoroutinefunction(run_security_crew), "run_security_crew must be async"
    assert inspect.iscoroutinefunction(run_dev_crew), "run_dev_crew must be async"
    assert inspect.iscoroutinefunction(run_recon), "run_recon must be async"
    assert inspect.iscoroutinefunction(run_code_review), "run_code_review must be async"


def test_scan_id_in_security_crew_response():
    """run_security_crew response must include a valid UUID scan_id."""
    mock_result = {
        "success": True,
        "target": "test.local",
        "result": "report",
        "report_html": "<html/>",
        "report_path": "/tmp/report.html",
        "session_log": "/tmp/crew.log",
    }

    with patch("secureflow.server.CrewOrchestrator") as mock_cls:
        mock_orch = MagicMock()
        mock_orch.run_security_crew.return_value = mock_result
        mock_orch.log_path = "/tmp/crew.log"
        mock_cls.return_value = mock_orch

        result = asyncio.run(run_security_crew_fn("test.local"))

    assert "scan_id" in result
    try:
        uuid.UUID(result["scan_id"])
    except ValueError:
        raise AssertionError(f"scan_id is not a valid UUID: {result['scan_id']}")
    assert result["status"] == "success"


def test_scan_id_in_dev_crew_response():
    """run_dev_crew response must include a valid UUID scan_id."""
    mock_result = {"status": "success", "result": "code", "task": "build api", "language": "python"}

    with patch("secureflow.server.DevOrchestrator") as mock_cls:
        mock_orch = MagicMock()
        mock_orch.run_dev_crew.return_value = mock_result
        mock_orch.log_path = "/tmp/dev.log"
        mock_cls.return_value = mock_orch

        result = asyncio.run(run_dev_crew_fn("build api", "python"))

    assert "scan_id" in result
    uuid.UUID(result["scan_id"])


def test_active_scans_registry_populated():
    """_active_scans registry must be updated during and after a run."""
    from secureflow.server import _active_scans

    mock_result = {
        "success": True,
        "target": "registry.test",
        "result": "ok",
        "report_html": "",
        "report_path": "",
        "session_log": "",
    }

    with patch("secureflow.server.CrewOrchestrator") as mock_cls:
        mock_orch = MagicMock()
        mock_orch.run_security_crew.return_value = mock_result
        mock_orch.log_path = ""
        mock_cls.return_value = mock_orch

        result = asyncio.run(run_security_crew_fn("registry.test"))

    scan_id = result["scan_id"]
    assert scan_id in _active_scans
    assert _active_scans[scan_id]["status"] == "complete"


def test_concurrent_scans_get_unique_scan_ids():
    """Two concurrent scan calls must produce distinct scan_ids."""
    mock_result = {
        "success": True,
        "target": "target",
        "result": "ok",
        "report_html": "",
        "report_path": "",
        "session_log": "",
    }

    async def _run_two():
        with patch("secureflow.server.CrewOrchestrator") as mock_cls:
            mock_orch = MagicMock()
            mock_orch.run_security_crew.return_value = mock_result
            mock_orch.log_path = ""
            mock_cls.return_value = mock_orch

            r1, r2 = await asyncio.gather(
                run_security_crew_fn("target1"),
                run_security_crew_fn("target2"),
            )
        return r1, r2

    r1, r2 = asyncio.run(_run_two())
    assert r1["scan_id"] != r2["scan_id"], "Concurrent scans must have unique scan_ids"


# ---------------------------------------------------------------------------
# Helpers: unwrap FastMCP-decorated functions to their underlying coroutines
# ---------------------------------------------------------------------------

def _unwrap(tool_fn):
    """Return the underlying coroutine function from a FastMCP tool."""
    fn = getattr(tool_fn, "fn", None) or getattr(tool_fn, "_fn", None) or tool_fn
    return fn


def run_security_crew_fn(target):
    fn = _unwrap(__import__("secureflow.server", fromlist=["run_security_crew"]).run_security_crew)
    return fn(target)


def run_dev_crew_fn(task, language, output_dir="/tmp/dev_output"):
    fn = _unwrap(__import__("secureflow.server", fromlist=["run_dev_crew"]).run_dev_crew)
    return fn(task, language, output_dir)
