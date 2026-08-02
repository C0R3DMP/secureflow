"""Tests for the /api/reports/export route — historical export, not a live scan."""

import asyncio
import json
from pathlib import Path

import pytest


def _make_request(query_string: bytes):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/reports/export",
        "headers": [],
        "query_string": query_string,
        "path_params": {},
    }
    return Request(scope)


@pytest.fixture
def report_dir(tmp_path, monkeypatch):
    """Point both Path.home() (used for the saved-report lookup) and
    SessionHistory (used for structured findings) at an isolated tmp dir."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    secureflow_dir = tmp_path / ".secureflow"
    secureflow_dir.mkdir()
    return secureflow_dir


def _write_report(report_dir, target, html="<html><body>ok</body></html>"):
    from secureflow.security import report_stem

    (report_dir / f"report_{report_stem(target)}.html").write_text(html)


def test_export_missing_report_is_404(report_dir):
    from secureflow import server

    response = asyncio.run(server.export_report(_make_request(b"target=never-scanned.example&format=json")))
    assert response.status_code == 404


def test_export_requires_target(report_dir):
    from secureflow import server

    response = asyncio.run(server.export_report(_make_request(b"format=json")))
    assert response.status_code == 400


def test_export_rejects_unsupported_format(report_dir):
    from secureflow import server

    _write_report(report_dir, "example.com")
    response = asyncio.run(server.export_report(_make_request(b"target=example.com&format=docx")))
    assert response.status_code == 400


def test_export_json_pulls_structured_findings_from_history(report_dir, monkeypatch):
    """The prose report only exists as a saved HTML file — structured findings
    live in SessionHistory, recorded separately at scan completion. A JSON
    export of a *past* scan must pull them in, not just re-wrap the HTML."""
    import secureflow.crew.history as history_mod
    from secureflow import server

    _write_report(report_dir, "example.com")

    persisted_findings = [
        {"severity": "critical", "source": "openssh 8.0", "reference": "CVE-2024-0001",
         "confidence": "likely", "description": "d"}
    ]

    class _FakeHistory:
        def __init__(self, *a, **k):
            pass

        def get_latest_for_target(self, target, session_type="security"):
            assert target == "example.com"
            return {"findings": persisted_findings}

    monkeypatch.setattr(history_mod, "SessionHistory", _FakeHistory)

    response = asyncio.run(server.export_report(_make_request(b"target=example.com&format=json")))
    assert response.status_code == 200
    data = json.loads(Path(response.path).read_text())
    assert data["findings"] == persisted_findings


def test_export_sarif_uses_correct_media_type(report_dir, monkeypatch):
    import secureflow.crew.history as history_mod
    from secureflow import server

    _write_report(report_dir, "example.com")

    class _FakeHistory:
        def __init__(self, *a, **k):
            pass

        def get_latest_for_target(self, target, session_type="security"):
            return None

    monkeypatch.setattr(history_mod, "SessionHistory", _FakeHistory)

    response = asyncio.run(server.export_report(_make_request(b"target=example.com&format=sarif")))
    assert response.status_code == 200
    assert response.media_type == "application/sarif+json"
    assert response.path.endswith(".sarif")
