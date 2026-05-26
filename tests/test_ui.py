"""Tests for UI endpoints and dashboard functionality."""

import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


def test_ui_dashboard_exists():
    """Test that dashboard HTML file exists."""
    dashboard_path = Path(__file__).parent.parent / "secureflow" / "static" / "index.html"
    assert dashboard_path.exists(), "Dashboard HTML file not found"


def test_dashboard_html_contains_required_elements():
    """Test that dashboard has required UI elements."""
    dashboard_path = Path(__file__).parent.parent / "secureflow" / "static" / "index.html"
    with open(dashboard_path, 'r') as f:
        content = f.read()

    # Check for required elements
    assert '<title>SecureFlow' in content, "Missing title"
    assert 'Security Scan' in content, "Missing scan section"
    assert 'Scan History' in content, "Missing history section"
    assert 'startSSEStream' in content, "Missing SSE stream handler"
    assert 'loadHistory' in content, "Missing history loader"
    assert 'target' in content, "Missing target input"


def test_dashboard_sse_endpoint_referenced():
    """Test that dashboard references correct SSE endpoint."""
    dashboard_path = Path(__file__).parent.parent / "secureflow" / "static" / "index.html"
    with open(dashboard_path, 'r') as f:
        content = f.read()

    assert '/stream/' in content, "Missing SSE stream endpoint reference"


def test_dashboard_history_api_referenced():
    """Test that dashboard references history API."""
    dashboard_path = Path(__file__).parent.parent / "secureflow" / "static" / "index.html"
    with open(dashboard_path, 'r') as f:
        content = f.read()

    assert '/api/history' in content, "Missing history API reference"


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
