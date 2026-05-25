"""Tests for SessionHistory persistent storage."""

import os
import tempfile
import pytest
from secureflow.crew.history import SessionHistory


@pytest.fixture
def history(tmp_path):
    """SessionHistory backed by a temp DB — isolated per test."""
    db_path = str(tmp_path / "test_history.db")
    h = SessionHistory(db_path=db_path)
    return h


def test_session_history_instantiation(history):
    assert history is not None
    assert history.db_path.endswith("test_history.db")


def test_record_returns_id(history):
    row_id = history.record("security", "192.168.1.1", "success")
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_get_sessions_empty(history):
    sessions = history.get_sessions()
    assert sessions == []


def test_record_and_retrieve(history):
    history.record("security", "scanme.nmap.org", "success", "CVE findings")
    sessions = history.get_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s["type"] == "security"
    assert s["target"] == "scanme.nmap.org"
    assert s["status"] == "success"
    assert s["summary"] == "CVE findings"


def test_multiple_sessions_newest_first(history):
    history.record("security", "host-a", "success")
    history.record("dev", "Build REST API", "failed")
    history.record("security", "host-b", "success")

    sessions = history.get_sessions()
    assert len(sessions) == 3
    assert sessions[0]["target"] == "host-b"
    assert sessions[1]["target"] == "Build REST API"
    assert sessions[2]["target"] == "host-a"


def test_filter_by_type(history):
    history.record("security", "host-a", "success")
    history.record("dev", "Build API", "success")
    history.record("security", "host-b", "failed")

    security_sessions = history.get_sessions(session_type="security")
    assert len(security_sessions) == 2
    assert all(s["type"] == "security" for s in security_sessions)

    dev_sessions = history.get_sessions(session_type="dev")
    assert len(dev_sessions) == 1
    assert dev_sessions[0]["target"] == "Build API"


def test_limit(history):
    for i in range(10):
        history.record("security", f"host-{i}", "success")

    sessions = history.get_sessions(limit=3)
    assert len(sessions) == 3


def test_clear(history):
    history.record("security", "host-a", "success")
    history.record("dev", "task", "failed")
    history.clear()
    assert history.get_sessions() == []


def test_summary_truncated_at_1000_chars(history):
    long_summary = "x" * 2000
    history.record("security", "target", "success", long_summary)
    sessions = history.get_sessions()
    assert len(sessions[0]["summary"]) == 1000


def test_session_has_timestamps(history):
    history.record("security", "target", "success")
    s = history.get_sessions()[0]
    assert s["started_at"] is not None
    assert s["completed_at"] is not None


def test_import_history_module():
    from secureflow.crew import history
    assert hasattr(history, "SessionHistory")
    assert hasattr(history, "_HISTORY_DB")
