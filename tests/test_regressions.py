"""Regression tests for logic defects found during the project review.

These are not security issues, but each one produced wrong behaviour:
  - orchestrator loggers re-attached handlers on every instantiation
  - concurrent scans shared one process-wide SSE queue
  - the in-memory scan registry grew without bound
  - /api/settings wrote env vars that config never re-read
  - the /ui 404 fallback called FileResponse with an unsupported signature
"""

import logging
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Logger handler duplication
# ---------------------------------------------------------------------------

def test_crew_orchestrator_does_not_stack_log_handlers(tmp_path):
    from secureflow.crew.orchestrator import CrewOrchestrator

    log_path = str(tmp_path / "crew.log")
    CrewOrchestrator(log_path=log_path)
    baseline = len(logging.getLogger("CrewOrchestrator").handlers)

    for _ in range(5):
        CrewOrchestrator(log_path=log_path)

    assert len(logging.getLogger("CrewOrchestrator").handlers) == baseline


def test_dev_orchestrator_does_not_stack_log_handlers(tmp_path):
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    log_path = str(tmp_path / "dev.log")
    DevOrchestrator(log_path=log_path)
    baseline = len(logging.getLogger("DevCrew").handlers)

    for _ in range(5):
        DevOrchestrator(log_path=log_path)

    assert len(logging.getLogger("DevCrew").handlers) == baseline


def test_orchestrator_logs_once_per_message(tmp_path):
    """Duplicated handlers previously wrote each line N times."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    log_path = tmp_path / "crew.log"
    for _ in range(3):
        orch = CrewOrchestrator(log_path=str(log_path))

    orch.log("INFO", "UNIQUE_MARKER_LINE")

    for handler in logging.getLogger("CrewOrchestrator").handlers:
        handler.flush()

    assert log_path.read_text().count("UNIQUE_MARKER_LINE") == 1


# ---------------------------------------------------------------------------
# Per-scan event queues
# ---------------------------------------------------------------------------

def test_each_orchestrator_owns_its_message_queue(tmp_path):
    """Concurrent scans must not consume each other's stream events."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    a = CrewOrchestrator(log_path=str(tmp_path / "a.log"))
    b = CrewOrchestrator(log_path=str(tmp_path / "b.log"))

    assert a.message_queue is not b.message_queue

    a.message_queue.put({"scan": "a"})
    assert b.message_queue.empty()
    assert a.message_queue.get_nowait() == {"scan": "a"}


def test_clear_message_queue_accepts_explicit_queue():
    from queue import Queue

    from secureflow.crew.orchestrator import clear_message_queue

    q = Queue()
    q.put(1)
    q.put(2)
    clear_message_queue(q)
    assert q.empty()


def test_orchestrator_rejects_invalid_target(tmp_path):
    from secureflow.crew.orchestrator import CrewOrchestrator

    orch = CrewOrchestrator(log_path=str(tmp_path / "c.log"))
    result = orch.run_security_crew("--script=/tmp/evil.nse")

    assert result["success"] is False
    assert "error" in result


# ---------------------------------------------------------------------------
# Bounded scan registry
# ---------------------------------------------------------------------------

def test_scan_registry_is_bounded():
    from secureflow import server

    server._active_scans.clear()
    try:
        for i in range(server.MAX_TRACKED_SCANS + 50):
            server._record_scan(f"scan-{i}", {"status": "complete", "target": "example.com"})

        assert len(server._active_scans) == server.MAX_TRACKED_SCANS
        # Oldest evicted, newest retained
        assert "scan-0" not in server._active_scans
        assert f"scan-{server.MAX_TRACKED_SCANS + 49}" in server._active_scans
    finally:
        server._active_scans.clear()


# ---------------------------------------------------------------------------
# Settings actually take effect
# ---------------------------------------------------------------------------

def test_reload_settings_picks_up_environment(monkeypatch):
    """Settings were frozen at import, making /api/settings a no-op."""
    from secureflow import config

    original = config.GEMINI_API_KEY
    try:
        monkeypatch.setenv("GEMINI_API_KEY", "runtime-key-abc")
        # Point at a non-existent .env so it cannot override the test value.
        monkeypatch.setattr(config, "_secureflow_env", Path("/nonexistent/.env"))
        config.reload_settings()
        assert config.GEMINI_API_KEY == "runtime-key-abc"
    finally:
        config.GEMINI_API_KEY = original


def test_provider_metadata_has_no_cached_availability():
    """PROVIDERS must not cache availability — it fired network I/O on import."""
    from secureflow.config import LLMProviderStatus

    for name, info in LLMProviderStatus.PROVIDERS.items():
        assert "available" not in info, f"{name} caches a stale availability flag"


def test_fallback_chain_only_includes_configured_providers(monkeypatch):
    from secureflow import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")

    chain = config.get_fallback_chain()
    models = [entry["model"] for entry in chain]

    assert all("gemini/" not in m for m in models)
    assert all("openrouter/" not in m for m in models)
    # Ollama needs no credentials, so it always remains as the local fallback.
    assert any("ollama" in m for m in models)


def test_fallback_chain_uses_valid_anthropic_prefix(monkeypatch):
    """'claude/...' is not a litellm provider prefix; 'anthropic/...' is."""
    from secureflow import config

    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "key")
    models = [e["model"] for e in config.get_fallback_chain()]

    assert not any(m.startswith("claude/") for m in models)
    assert any(m.startswith("anthropic/") for m in models)


# ---------------------------------------------------------------------------
# NVD throttle
# ---------------------------------------------------------------------------

def test_cve_lookup_does_not_sleep_when_interval_elapsed(monkeypatch):
    """The old code slept a flat 3s per lookup and never read last_api_call."""
    import time

    import secureflow.crew.tools as tools_mod

    slept = []
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: slept.append(s))

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": []}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())

    tools = tools_mod.SecurityTools()
    # Pretend the last call was long ago — no wait should be owed.
    tools.last_api_call = time.time() - 3600
    tools.lookup_cve("openssh", "8.0")

    assert all(s <= 0 for s in slept) or not slept


def test_cve_lookup_uses_cache_without_network(monkeypatch):
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):  # pragma: no cover
        raise AssertionError("cached lookup must not hit the network")

    tools = tools_mod.SecurityTools()
    tools.cve_cache["openssh:8.0"] = {"status": "success", "cve_count": 0}
    monkeypatch.setattr(tools_mod.requests, "get", _boom)

    assert tools.lookup_cve("openssh", "8.0")["status"] == "success"


# ---------------------------------------------------------------------------
# Dashboard 404 fallback
# ---------------------------------------------------------------------------

def test_missing_dashboard_returns_404_not_500(monkeypatch, tmp_path):
    """FileResponse(status_code=, content=) raised TypeError → HTTP 500."""
    import asyncio

    from starlette.requests import Request

    from secureflow import server

    # Point the handler at an empty directory so both build and fallback miss.
    monkeypatch.setattr(server, "__file__", str(tmp_path / "server.py"))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ui",
        "headers": [],
        "query_string": b"",
        "path_params": {},
    }
    response = asyncio.run(server.serve_dashboard_root(Request(scope)))

    assert response.status_code == 404


def test_ui_asset_traversal_blocked_by_handler(monkeypatch, tmp_path):
    import asyncio

    from starlette.requests import Request

    from secureflow import server

    dist = tmp_path / "static" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("SECRET")

    monkeypatch.setattr(server, "__file__", str(tmp_path / "server.py"))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ui/x",
        "headers": [],
        "query_string": b"",
        "path_params": {"path_remaining": "../../outside_secret.txt"},
    }
    response = asyncio.run(server.serve_dashboard_assets(Request(scope)))

    assert response.status_code == 404
