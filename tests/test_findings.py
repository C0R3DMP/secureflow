"""Tests for the pure previous-vs-current findings diff helper."""

from secureflow.findings import diff_findings


def test_diff_findings_empty_previous_is_all_new():
    current = [{"reference": "CVE-1", "severity": "high", "source": "s"}]
    diff = diff_findings([], current)
    assert diff["new"] == current
    assert diff["resolved"] == []


def test_diff_findings_identical_scans_have_no_changes():
    findings = [{"reference": "CVE-1", "severity": "high", "source": "s"}]
    diff = diff_findings(findings, findings)
    assert diff["new"] == []
    assert diff["resolved"] == []


def test_diff_findings_detects_new_and_resolved():
    previous = [
        {"reference": "CVE-OLD", "severity": "medium", "source": "s"},
        {"reference": "CVE-STILL-HERE", "severity": "high", "source": "s"},
    ]
    current = [
        {"reference": "CVE-STILL-HERE", "severity": "high", "source": "s"},
        {"reference": "CVE-NEW", "severity": "critical", "source": "s"},
    ]
    diff = diff_findings(previous, current)
    assert [f["reference"] for f in diff["new"]] == ["CVE-NEW"]
    assert [f["reference"] for f in diff["resolved"]] == ["CVE-OLD"]


def test_diff_findings_falls_back_to_source_and_severity_without_a_reference():
    """A finding with no CVE id (rare, but possible) still needs a stable key —
    the same source+severity dedup key severity_counts()/get_findings() use."""
    previous = [{"reference": "", "severity": "low", "source": "banner-only-x"}]
    current = [{"reference": "", "severity": "low", "source": "banner-only-x"}]
    diff = diff_findings(previous, current)
    assert diff["new"] == []
    assert diff["resolved"] == []


def test_diff_findings_current_empty_resolves_everything():
    previous = [{"reference": "CVE-1", "severity": "high", "source": "s"}]
    diff = diff_findings(previous, [])
    assert diff["new"] == []
    assert diff["resolved"] == previous
