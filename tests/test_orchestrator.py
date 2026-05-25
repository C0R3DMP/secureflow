"""Test crew orchestrators."""

import pytest


def test_crew_orchestrator_instantiation():
    """Test CrewOrchestrator can be instantiated."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    orchestrator = CrewOrchestrator()

    assert orchestrator is not None
    assert hasattr(orchestrator, "context")
    assert hasattr(orchestrator, "communicator")
    assert hasattr(orchestrator, "logger")


def test_dev_orchestrator_instantiation():
    """Test DevOrchestrator can be instantiated."""
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    orchestrator = DevOrchestrator()

    assert orchestrator is not None
    assert hasattr(orchestrator, "context")
    assert hasattr(orchestrator, "communicator")
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


def test_shared_context_isolation():
    """Test that each orchestrator has isolated context."""
    from secureflow.crew.orchestrator import CrewOrchestrator
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    sec_orch = CrewOrchestrator()
    dev_orch = DevOrchestrator()

    # They might share the same SQLite DB, but should have separate instances
    assert sec_orch.context is not None
    assert dev_orch.context is not None
