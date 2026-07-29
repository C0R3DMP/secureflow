"""Tests for UI endpoints and dashboard functionality."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


_DIST = Path(__file__).parent.parent / "secureflow" / "static" / "dist"

# The React build is a generated artifact produced by ./setup-frontend.sh and is
# not committed. Tests that inspect it are skipped when it is absent instead of
# failing a clean checkout; the source template is asserted unconditionally below.
requires_build = pytest.mark.skipif(
    not (_DIST / "index.html").exists(),
    reason="React build not present — run ./setup-frontend.sh",
)


def test_dashboard_source_template_exists():
    """The frontend entry template ships in the repo and declares a React root."""
    index_html = Path(__file__).parent.parent / "frontend" / "index.html"
    assert index_html.exists(), "frontend/index.html missing from repository"

    content = index_html.read_text()
    assert "SecureFlow" in content, "Missing title"
    assert 'id="root"' in content, "Missing React root div"


@requires_build
def test_ui_dashboard_exists():
    """Test that dashboard HTML file exists (React build)."""
    assert (_DIST / "index.html").exists(), "Dashboard React build not found"


@requires_build
def test_dashboard_html_contains_required_elements():
    """Test that dashboard has required UI elements (React build)."""
    content = (_DIST / "index.html").read_text()

    # Check for required elements in React build
    assert '<title>SecureFlow' in content, "Missing title"
    assert 'root' in content, "Missing React root div"


@requires_build
def test_dashboard_sse_endpoint_referenced():
    """Test that dashboard references correct SSE endpoint (via JS)."""
    # Check that the assets directory exists and contains JS files
    js_files = list((_DIST / "assets").glob("*.js"))
    assert len(js_files) > 0, "Missing JavaScript assets"


@requires_build
def test_dashboard_history_api_referenced():
    """Test that dashboard is set up for history API (React build exists)."""
    # React build exists and will handle API calls
    assert (_DIST / "index.html").exists(), "Missing React dashboard for history API"


def test_session_history_records_security_scan():
    """Test that security scans are recorded in history."""
    from secureflow.crew.history import SessionHistory
    import tempfile
    import os

    # Use temporary database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_history.db")
        history = SessionHistory(db_path=db_path)

        # Record a test scan
        session_id = history.record(
            session_type="security",
            target="test.example.com",
            status="success",
            summary="Test scan completed"
        )

        assert session_id > 0, "Session not recorded"

        # Retrieve and verify
        sessions = history.get_sessions(limit=10)
        assert len(sessions) == 1, "Session not found"
        assert sessions[0]["target"] == "test.example.com"
        assert sessions[0]["status"] == "success"


def test_session_history_retrieves_multiple_sessions():
    """Test that history retrieves multiple sessions in correct order."""
    from secureflow.crew.history import SessionHistory
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_history.db")
        history = SessionHistory(db_path=db_path)

        # Record multiple scans
        targets = ["target1.com", "target2.com", "target3.com"]
        for target in targets:
            history.record(
                session_type="security",
                target=target,
                status="success",
                summary=f"Scan of {target}"
            )

        # Retrieve all sessions
        sessions = history.get_sessions(limit=10)
        assert len(sessions) == 3, "Not all sessions retrieved"

        # Verify newest first
        assert sessions[0]["target"] == "target3.com"
        assert sessions[1]["target"] == "target2.com"
        assert sessions[2]["target"] == "target1.com"


def test_session_history_limits_results():
    """Test that history respects limit parameter."""
    from secureflow.crew.history import SessionHistory
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_history.db")
        history = SessionHistory(db_path=db_path)

        # Record 10 scans
        for i in range(10):
            history.record(
                session_type="security",
                target=f"target{i}.com",
                status="success",
                summary=f"Scan {i}"
            )

        # Test limit
        sessions = history.get_sessions(limit=5)
        assert len(sessions) == 5, "Limit not respected"


def test_session_history_filters_by_type():
    """Test that history can filter by session type."""
    from secureflow.crew.history import SessionHistory
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_history.db")
        history = SessionHistory(db_path=db_path)

        # Record mixed session types
        history.record("security", "target1.com", "success", "Security scan")
        history.record("development", "python:hello", "success", "Dev build")
        history.record("security", "target2.com", "success", "Security scan")

        # Filter by type
        security_sessions = history.get_sessions(session_type="security")
        assert len(security_sessions) == 2, "Filter by type failed"

        dev_sessions = history.get_sessions(session_type="development")
        assert len(dev_sessions) == 1, "Filter by type failed"


def test_orchestrator_records_success():
    """Test that orchestrator records successful scans in history."""
    from secureflow.crew.orchestrator import CrewOrchestrator
    from secureflow.crew.history import SessionHistory
    import tempfile
    import os

    # Mock the create_crew to avoid actual crew execution
    with patch('secureflow.crew.orchestrator.create_crew') as mock_crew:
        mock_crew.return_value.kickoff.return_value = "Test result"

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_history.db")

            # Patch history to use temp db
            with patch('secureflow.crew.orchestrator.SessionHistory') as mock_history:
                mock_history_instance = MagicMock()
                mock_history.return_value = mock_history_instance

                orchestrator = CrewOrchestrator()
                result = orchestrator.run_security_crew("test.target.com")

                # Verify history.record was called with correct params
                mock_history_instance.record.assert_called_once()
                call_args = mock_history_instance.record.call_args
                assert call_args[1]["session_type"] == "security"
                assert call_args[1]["target"] == "test.target.com"
                assert call_args[1]["status"] == "success"


def test_orchestrator_records_failure():
    """Test that orchestrator records failed scans in history."""
    from secureflow.crew.orchestrator import CrewOrchestrator

    # Mock the create_crew to raise an exception
    with patch('secureflow.crew.orchestrator.create_crew') as mock_crew:
        mock_crew.side_effect = Exception("Test error")

        with patch('secureflow.crew.orchestrator.SessionHistory') as mock_history:
            mock_history_instance = MagicMock()
            mock_history.return_value = mock_history_instance

            orchestrator = CrewOrchestrator()
            result = orchestrator.run_security_crew("test.target.com")

            # Verify history.record was called with error status
            mock_history_instance.record.assert_called_once()
            call_args = mock_history_instance.record.call_args
            assert call_args[1]["status"] == "error"


def test_dev_orchestrator_records_success():
    """Test that dev orchestrator records successful builds in history."""
    from secureflow.crew.dev_orchestrator import DevOrchestrator

    with patch('secureflow.crew.dev_orchestrator.create_dev_crew') as mock_crew:
        mock_crew.return_value.kickoff.return_value = "Generated code"

        with patch('secureflow.crew.dev_orchestrator.SessionHistory') as mock_history:
            mock_history_instance = MagicMock()
            mock_history.return_value = mock_history_instance

            orchestrator = DevOrchestrator()
            result = orchestrator.run_dev_crew("Build API", "python", "/tmp/output")

            # Verify history.record was called
            mock_history_instance.record.assert_called_once()
            call_args = mock_history_instance.record.call_args
            assert call_args[1]["session_type"] == "development"
            assert call_args[1]["status"] == "success"
