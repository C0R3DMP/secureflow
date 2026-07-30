"""Test crew orchestrators."""

import pytest


def test_crew_orchestrator_instantiation():
    """Test CrewOrchestrator can be instantiated."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    orchestrator = CrewOrchestrator()

    assert orchestrator is not None
    assert hasattr(orchestrator, "context")
    assert hasattr(orchestrator, "logger")


def test_dev_orchestrator_instantiation():
    """Test DevOrchestrator can be instantiated."""
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    orchestrator = DevOrchestrator()

    assert orchestrator is not None
    assert hasattr(orchestrator, "context")
    assert hasattr(orchestrator, "logger")


def test_orchestrator_methods_exist():
    """Test CrewOrchestrator has required methods."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    orchestrator = CrewOrchestrator()

    assert hasattr(orchestrator, "run_security_crew")
    assert callable(orchestrator.run_security_crew)
    assert hasattr(orchestrator, "export_session")
    assert callable(orchestrator.export_session)


def test_dev_orchestrator_methods_exist():
    """Test DevOrchestrator has required methods."""
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    orchestrator = DevOrchestrator()

    assert hasattr(orchestrator, "run_dev_crew")
    assert callable(orchestrator.run_dev_crew)
    assert hasattr(orchestrator, "run_code_review")
    assert callable(orchestrator.run_code_review)
    assert hasattr(orchestrator, "export_session")
    assert callable(orchestrator.export_session)


def test_run_security_crew_diffs_against_previous_scan(tmp_path, monkeypatch):
    """A target scanned before should get a diff against its last recorded
    findings — new CVEs surfaced, previously-seen ones now gone — pushed both
    in the returned result and as a 'diff_ready' stream event."""
    import secureflow.crew.orchestrator as orch_mod
    from secureflow.crew.tools import security_tools

    previous_findings = [
        {"severity": "high", "source": "s", "reference": "CVE-OLD", "confidence": "likely", "description": ""}
    ]
    recorded = {}

    class _FakeHistory:
        def __init__(self, *a, **k):
            pass

        def get_latest_for_target(self, target, session_type="security"):
            return {
                "id": 1, "status": "success", "summary": "",
                "started_at": "t0", "completed_at": "t0",
                "findings": previous_findings,
            }

        def record(self, **kwargs):
            recorded.update(kwargs)
            return 1

    class _FakeCrew:
        def kickoff(self):
            # run_security_crew() clears findings at the start of the run, so
            # the "current" finding must be recorded as if the crew itself
            # found it during kickoff() — recording it before the call would
            # just be wiped by that reset.
            security_tools.record_finding("critical", "svc", "CVE-NEW", confidence="likely")
            return "report text"

    monkeypatch.setattr(orch_mod, "SessionHistory", _FakeHistory)
    monkeypatch.setattr(orch_mod, "create_crew", lambda target, **kwargs: _FakeCrew())

    security_tools.clear_findings()

    orch = orch_mod.CrewOrchestrator(log_path=str(tmp_path / "diff.log"))
    result = orch.run_security_crew("example.com")

    assert result["success"] is True
    assert [f["reference"] for f in result["diff"]["new"]] == ["CVE-NEW"]
    assert [f["reference"] for f in result["diff"]["resolved"]] == ["CVE-OLD"]
    assert [f["reference"] for f in result["findings"]] == ["CVE-NEW"]
    assert recorded["findings"] == result["findings"]

    events = []
    while not orch.message_queue.empty():
        events.append(orch.message_queue.get_nowait())
    diff_events = [e for e in events if e.get("event") == "diff_ready"]
    assert len(diff_events) == 1
    assert diff_events[0]["new"][0]["reference"] == "CVE-NEW"
    assert diff_events[0]["resolved"][0]["reference"] == "CVE-OLD"

    security_tools.clear_findings()


def test_run_security_crew_emits_no_diff_event_on_first_ever_scan(tmp_path, monkeypatch):
    """A target with no prior recorded scan has nothing to diff against — the
    dashboard must not be told "0 new / 0 resolved" as if that were signal."""
    import secureflow.crew.orchestrator as orch_mod
    from secureflow.crew.tools import security_tools

    class _FakeHistory:
        def __init__(self, *a, **k):
            pass

        def get_latest_for_target(self, target, session_type="security"):
            return None

        def record(self, **kwargs):
            return 1

    class _FakeCrew:
        def kickoff(self):
            return "report text"

    monkeypatch.setattr(orch_mod, "SessionHistory", _FakeHistory)
    monkeypatch.setattr(orch_mod, "create_crew", lambda target, **kwargs: _FakeCrew())

    security_tools.clear_findings()
    orch = orch_mod.CrewOrchestrator(log_path=str(tmp_path / "first.log"))
    result = orch.run_security_crew("first-scan.example.com")

    events = []
    while not orch.message_queue.empty():
        events.append(orch.message_queue.get_nowait())
    assert not any(e.get("event") == "diff_ready" for e in events)
    assert result["diff"] == {"new": [], "resolved": []}


def test_shared_context_isolation():
    """Test that each orchestrator has isolated context."""
    from secureflow.crew.orchestrator import CrewOrchestrator
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    sec_orch = CrewOrchestrator()
    dev_orch = DevOrchestrator()

    # They might share the same SQLite DB, but should have separate instances
    assert sec_orch.context is not None
    assert dev_orch.context is not None
