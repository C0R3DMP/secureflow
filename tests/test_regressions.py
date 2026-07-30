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


# ---------------------------------------------------------------------------
# A failed crew run must be reported as a failure, not as success
#
# Live-verified during a manual dashboard test: with no LLM provider reachable,
# run_security_crew()'s exception branch returns {"success": False, "error":
# ...} with no "message" key. stream_scan_sse used to do
# result.get('message', 'Assessment complete'), which fell through to that
# hardcoded default on every failure. The dashboard showed all three phases
# green with zero agent messages and no report — a scan that produced nothing
# but declared total success. run_security_crew_stream (the MCP-protocol
# equivalent) had a related but different bug: it awaited crew.kickoff()'s
# future with no try/except at all, so a failure would propagate as an
# unhandled exception out of an @app.tool() coroutine instead of a clean error.
# ---------------------------------------------------------------------------

def _drain_sse(async_gen):
    """Collect an async generator of `data: {...}\\n\\n` frames into dicts."""
    import asyncio
    import json

    async def _run():
        return [chunk async for chunk in async_gen]

    frames = asyncio.run(_run())
    events = []
    for frame in frames:
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def test_stream_emits_error_event_on_crew_failure(monkeypatch):
    from secureflow import server

    class _FakeOrchestrator:
        message_queue = __import__("queue").Queue()

        def run_security_crew(self, target):
            return {"success": False, "error": "No LLM providers available!", "session_log": "x"}

    monkeypatch.setattr(server, "CrewOrchestrator", _FakeOrchestrator)

    import asyncio

    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/stream/example.com",
        "headers": [],
        "query_string": b"",
        "path_params": {"target": "example.com"},
    }
    response = asyncio.run(server.stream_scan_sse(Request(scope)))
    events = _drain_sse(response.body_iterator)

    kinds = [e.get("event") for e in events]
    assert "error" in kinds, f"expected an error event, got: {events}"
    assert "complete" not in kinds, "a failed crew run must not report 'complete'"

    error_event = next(e for e in events if e.get("event") == "error")
    assert error_event["message"] == "No LLM providers available!"


def test_stream_emits_complete_event_on_crew_success(monkeypatch):
    from secureflow import server

    class _FakeOrchestrator:
        message_queue = __import__("queue").Queue()

        def run_security_crew(self, target):
            return {"success": True, "message": "Collaborative security assessment complete"}

    monkeypatch.setattr(server, "CrewOrchestrator", _FakeOrchestrator)

    import asyncio

    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/stream/example.com",
        "headers": [],
        "query_string": b"",
        "path_params": {"target": "example.com"},
    }
    response = asyncio.run(server.stream_scan_sse(Request(scope)))
    events = _drain_sse(response.body_iterator)

    kinds = [e.get("event") for e in events]
    assert "complete" in kinds
    assert "error" not in kinds


def test_mcp_stream_tool_reports_crew_failure_instead_of_raising(monkeypatch):
    """run_security_crew_stream must not let crew.kickoff()'s exception escape."""
    import asyncio

    from secureflow import server

    def _boom(target, task_callback=None):
        class _Crew:
            def kickoff(self):
                raise RuntimeError("Failed to connect to OpenAI API: Connection error.")

        return _Crew()

    monkeypatch.setattr(server, "create_crew", _boom)

    class _FakeCtx:
        async def info(self, msg):
            pass

        async def error(self, msg):
            self.last_error = msg

        async def report_progress(self, *a, **k):
            pass

    ctx = _FakeCtx()
    result = asyncio.run(server.run_security_crew_stream("example.com", ctx))

    assert result["status"] == "error"
    assert "Connection error" in result["error"]
    assert ctx.last_error  # ctx.error() was actually called, not just swallowed


# ---------------------------------------------------------------------------
# A provider that reports itself available but fails to construct must not
# take down the whole fallback chain.
#
# Live-verified: with a real GEMINI_API_KEY set, get_best_available_llm()
# raised ImportError from CrewAI's Gemini native-provider import (a missing
# optional dependency, crewai[google-genai], now added to pyproject.toml).
# Before this fix, that exception propagated straight out of the function —
# it never reached the "always try Ollama" fallback the code's own comment
# promises, even though get_available_providers() had already reported
# ['gemini'] and nothing else, so there was nowhere left to fall through to.
# ---------------------------------------------------------------------------

def test_broken_provider_falls_through_instead_of_crashing(monkeypatch):
    import secureflow.config as config_mod

    monkeypatch.setattr(
        config_mod.LLMProviderStatus,
        "get_available_providers",
        staticmethod(lambda: [("gemini", 1)]),
    )
    monkeypatch.setattr(config_mod, "GEMINI_API_KEY", "fake-key")

    def _broken(*a, **k):
        raise ImportError("Google Gen AI native provider not available")

    monkeypatch.setattr(config_mod, "get_llm_with_rate_limit_fallback", _broken)
    monkeypatch.setattr(config_mod, "is_ollama_available", lambda *a, **k: True)

    # Fell through to the Ollama safety net instead of the ImportError escaping
    # out of the function. CrewAI's LLM.__new__ returns a provider-specific
    # completion subclass rather than the base LLM class, so check the
    # resolved model/base_url instead of the exact type.
    llm = config_mod.get_best_available_llm()

    assert "qwen2.5-coder" in llm.model
    assert config_mod.OLLAMA_BASE_URL in (llm.base_url or "")
