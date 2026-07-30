"""Tests for M9: report export (HTML, PDF, JSON)."""

import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

# weasyprint ships in the optional 'export' extra, so PDF tests skip rather than
# fail when only the base dependencies are installed.
requires_weasyprint = pytest.mark.skipif(
    importlib.util.find_spec("weasyprint") is None,
    reason="PDF export needs the optional 'export' extra: pip install 'secureflow[export]'",
)


_MOCK_RESULT = {
    "success": True,
    "target": "test.local",
    "result": "Open ports: 22, 80\nCVE-2024-0001: critical",
    "report_html": "<html><body><h1>Report</h1><pre>Open ports: 22, 80</pre></body></html>",
    "report_path": "/tmp/report_test.local.html",
    "session_log": "/tmp/crew.log",
}


def _exporter(tmp_dir):
    from secureflow.reports import ReportExporter
    return ReportExporter(output_dir=str(tmp_dir))


def test_export_html_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_html(_MOCK_RESULT, "test.local")
        assert Path(path).exists()
        assert Path(path).suffix == ".html"
        assert "<html>" in Path(path).read_text()


def test_export_html_content_is_escaped():
    """Report HTML must not contain raw unescaped script tags from LLM output."""
    from secureflow.reports import ReportExporter
    evil_result = {**_MOCK_RESULT, "report_html": ""}
    evil_result["result"] = "<script>alert(1)</script>"
    with tempfile.TemporaryDirectory() as tmp:
        path = ReportExporter(output_dir=tmp).to_html(evil_result, "xss.test")
        content = Path(path).read_text()
        assert "<script>" not in content
        assert "&lt;script&gt;" in content


def test_export_json_creates_valid_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_json(_MOCK_RESULT, "test.local")
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["meta"]["target"] == "test.local"
        assert data["meta"]["tool"] == "SecureFlow AI"
        assert data["status"] == "success"
        assert "timestamp" in data["meta"]


def test_export_json_includes_structured_findings():
    with_findings = {
        **_MOCK_RESULT,
        "findings": [
            {"severity": "critical", "source": "openssh 8.0", "reference": "CVE-2024-0001",
             "confidence": "likely", "description": "d"}
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_json(with_findings, "test.local")
        data = json.loads(Path(path).read_text())
        assert data["findings"][0]["reference"] == "CVE-2024-0001"
        assert data["findings"][0]["confidence"] == "likely"


def test_export_json_findings_default_to_empty_list():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_json(_MOCK_RESULT, "test.local")
        data = json.loads(Path(path).read_text())
        assert data["findings"] == []


def test_export_json_failed_scan():
    failed = {**_MOCK_RESULT, "success": False}
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_json(failed, "fail.test")
        data = json.loads(Path(path).read_text())
        assert data["status"] == "error"


@requires_weasyprint
def test_export_pdf_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_pdf(_MOCK_RESULT, "test.local")
        assert Path(path).exists()
        assert Path(path).suffix == ".pdf"
        assert Path(path).stat().st_size > 0


def test_export_sarif_creates_valid_file():
    with_findings = {
        **_MOCK_RESULT,
        "findings": [
            {"severity": "critical", "source": "openssh 8.0", "reference": "CVE-2024-0001",
             "confidence": "confirmed", "description": "Remote code execution"},
            {"severity": "medium", "source": "http", "reference": "CVE-2024-0002",
             "confidence": "possible", "description": ""},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_sarif(with_findings, "test.local")
        assert Path(path).suffix == ".sarif"
        data = json.loads(Path(path).read_text())

        assert data["version"] == "2.1.0"
        run = data["runs"][0]
        assert run["tool"]["driver"]["name"] == "SecureFlow"
        rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
        assert rule_ids == {"CVE-2024-0001", "CVE-2024-0002"}

        results_by_rule = {r["ruleId"]: r for r in run["results"]}
        assert results_by_rule["CVE-2024-0001"]["level"] == "error"
        assert results_by_rule["CVE-2024-0001"]["properties"]["confidence"] == "confirmed"
        assert results_by_rule["CVE-2024-0002"]["level"] == "warning"


def test_export_sarif_with_no_findings_is_still_valid():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_sarif(_MOCK_RESULT, "test.local")
        data = json.loads(Path(path).read_text())
        assert data["runs"][0]["results"] == []


def test_export_dispatch_sarif():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).export("sarif", _MOCK_RESULT, "test.local")
        assert path.endswith(".sarif")


def test_export_dispatch_html():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).export("html", _MOCK_RESULT, "test.local")
        assert path.endswith(".html")


def test_export_dispatch_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).export("json", _MOCK_RESULT, "test.local")
        assert path.endswith(".json")


@requires_weasyprint
def test_export_dispatch_pdf():
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).export("pdf", _MOCK_RESULT, "test.local")
        assert path.endswith(".pdf")


def test_export_invalid_format_raises():
    import pytest
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="Unsupported format"):
            _exporter(tmp).export("docx", _MOCK_RESULT, "test.local")


def test_export_target_with_slashes():
    """Targets with slashes must not create subdirectories."""
    with tempfile.TemporaryDirectory() as tmp:
        path = _exporter(tmp).to_json(_MOCK_RESULT, "192.168.1.1/admin")
        assert "/" not in Path(path).name


def test_scan_cli_has_format_option():
    """CLI scan command must expose --format option."""
    from click.testing import CliRunner
    from secureflow.cli import scan

    runner = CliRunner()
    result = runner.invoke(scan, ["--help"])
    assert "--format" in result.output
    assert "html" in result.output
    assert "pdf" in result.output
    assert "json" in result.output
    assert "sarif" in result.output
