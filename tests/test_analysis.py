"""Tests that the analysis tools measure rather than fabricate.

Before these fixes the dev tools returned fixed values for any input:
`bugs_found: 0`, `quality_score: 85`, `tests_run: 3, tests_passed: 3`. Those
numbers were fed to an LLM as tool output and written into review reports.
"""

import pytest

from secureflow.analysis import analyse_python, review_metrics, syntax_check
from secureflow.crew.tools import DevTools, _cpe_for, _parse_cve

VULNERABLE = '''
import os, subprocess, yaml
API_KEY = "sk-live-abcdef123456"

def transfer(user, amount, log=[]):
    query = "UPDATE acct SET bal = bal - %s WHERE user = '%s'" % (amount, user)
    cursor.execute(query)
    os.system("logger " + user)
    subprocess.run("df -h", shell=True)
    config = yaml.load(open("c.yml"))
    try:
        return eval(input("confirm: "))
    except:
        pass
'''

CLEAN = '''
def add(a, b):
    """Return the sum of two numbers."""
    return a + b
'''


# ---------------------------------------------------------------------------
# Bug detection
# ---------------------------------------------------------------------------

def test_find_bugs_detects_real_vulnerabilities():
    result = DevTools.find_bugs_impl(VULNERABLE, "python")

    assert result["bugs_found"] > 0, "vulnerable code must not report zero bugs"
    kinds = {issue["type"] for issue in result["issues"]}
    for expected in {
        "code_injection",
        "command_injection",
        "sql_injection",
        "hardcoded_secret",
        "unsafe_deserialization",
        "broad_except",
        "mutable_default_arg",
    }:
        assert expected in kinds, f"missed {expected}"


def test_find_bugs_reports_accurate_line_numbers():
    result = DevTools.find_bugs_impl(VULNERABLE, "python")
    lines = VULNERABLE.splitlines()

    for issue in result["issues"]:
        assert issue["line"] > 0
        assert issue["line"] <= len(lines)

    eval_finding = next(i for i in result["issues"] if i["type"] == "code_injection")
    assert "eval" in lines[eval_finding["line"] - 1]


def test_find_bugs_clean_code_reports_none():
    assert DevTools.find_bugs_impl(CLEAN, "python")["bugs_found"] == 0


def test_find_bugs_reports_syntax_errors():
    result = DevTools.find_bugs_impl("def broken(:\n    pass", "python")
    assert result["status"] == "syntax_error"
    assert result["issues"][0]["type"] == "syntax_error"


def test_find_bugs_is_honest_about_unsupported_languages():
    """It must say it cannot analyse Go, not report 0 bugs."""
    result = DevTools.find_bugs_impl("package main\nfunc main(){}", "go")
    assert result["status"] == "unsupported"
    assert result["analysed"] is False
    assert "not implemented" in result["message"]


def test_subprocess_shell_true_flagged_but_list_form_is_not():
    flagged = analyse_python('import subprocess\nsubprocess.run("ls", shell=True)')
    safe = analyse_python('import subprocess\nsubprocess.run(["ls", "-l"])')

    assert any(f["type"] == "command_injection" for f in flagged["findings"])
    assert not any(f["type"] == "command_injection" for f in safe["findings"])


def test_short_literals_are_not_treated_as_secrets():
    """A sentinel like password = "" must not be reported as a credential."""
    result = analyse_python('password = ""\ntoken = "x"')
    assert not any(f["type"] == "hardcoded_secret" for f in result["findings"])


def test_yaml_safe_load_not_flagged():
    result = analyse_python('import yaml\nyaml.load(s, Loader=yaml.SafeLoader)')
    assert not any(f["type"] == "unsafe_deserialization" for f in result["findings"])


# ---------------------------------------------------------------------------
# Quality scoring
# ---------------------------------------------------------------------------

def test_quality_score_varies_with_input():
    """The score was a constant 85 for every input."""
    bad = DevTools.review_code_impl(VULNERABLE, "python")["quality_score"]
    good = DevTools.review_code_impl(CLEAN, "python")["quality_score"]

    assert good > bad
    assert bad < 85


def test_review_reports_measured_metrics():
    metrics = DevTools.review_code_impl(VULNERABLE, "python")["metrics"]

    assert metrics["total_lines"] == len(VULNERABLE.splitlines())
    assert metrics["functions"] == 1
    assert metrics["longest_function"]["name"] == "transfer"


def test_review_metrics_counts_real_lines():
    code = "# comment\n\ndef f():\n    return 1\n"
    metrics = review_metrics(code, "python")

    assert metrics["total_lines"] == 4
    assert metrics["comment_lines"] == 1
    assert metrics["blank_lines"] == 1
    assert metrics["functions"] == 1


def test_review_is_honest_about_unsupported_languages():
    result = DevTools.review_code_impl("func main(){}", "go")
    assert result["status"] == "unsupported"
    assert "quality_score" not in result


# ---------------------------------------------------------------------------
# Syntax check must not claim tests ran
# ---------------------------------------------------------------------------

def test_check_syntax_never_claims_tests_passed():
    result = DevTools.check_syntax_impl(CLEAN, "python")

    assert result["tests_executed"] == 0
    assert "tests_passed" not in result
    assert "coverage" not in result
    assert result["syntax_valid"] is True


def test_check_syntax_detects_invalid_source():
    result = DevTools.check_syntax_impl("def f(:\n  pass", "python")
    assert result["status"] == "error"
    assert result["syntax_valid"] is False
    assert result["error"]["line"] == 1


def test_syntax_check_unsupported_language_is_explicit():
    result = syntax_check("func main(){}", "go")
    assert result["checked"] is False
    assert result["valid"] is None


def test_write_code_tool_no_longer_exists():
    """It returned a `def main(): pass` stub for every specification."""
    import secureflow.crew.tools as tools_mod

    assert not hasattr(tools_mod, "write_code")
    assert not hasattr(DevTools, "write_code_impl")


# ---------------------------------------------------------------------------
# Suggestions are grounded in findings
# ---------------------------------------------------------------------------

def test_suggestions_reference_actual_findings():
    result = DevTools.suggest_improvements_impl(VULNERABLE, "python")
    categories = {s["category"] for s in result["suggestions"]}

    assert "security" in categories
    for suggestion in result["suggestions"]:
        assert suggestion["occurrences"] >= 1


def test_suggestions_empty_for_clean_code():
    result = DevTools.suggest_improvements_impl(CLEAN, "python")
    security = [s for s in result["suggestions"] if s["category"] == "security"]
    assert security == []


# ---------------------------------------------------------------------------
# CVE lookup query construction
# ---------------------------------------------------------------------------

def test_cpe_uses_known_vendor_prefix():
    """NVD CPEs are vendor-qualified; a bare product name matches nothing."""
    assert _cpe_for("openssh", "8.0") == "cpe:2.3:a:openbsd:openssh:8.0"
    assert _cpe_for("nginx", "1.18.0") == "cpe:2.3:a:nginx:nginx:1.18.0"


def test_cpe_sanitises_hostile_input():
    cpe = _cpe_for("evil; rm -rf /", "1.0")
    assert ";" not in cpe and " " not in cpe


def test_versioned_lookup_uses_cpe_not_keyword(monkeypatch):
    """keywordSearch='openssh 8.0' matched nothing, silently returning 0 CVEs."""
    import secureflow.crew.tools as tools_mod

    seen = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    def _fake_get(url, params=None, **kwargs):
        seen.append(params)
        return _Resp()

    monkeypatch.setattr(tools_mod.requests, "get", _fake_get)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools_mod.SecurityTools().lookup_cve("openssh", "8.0")

    assert "virtualMatchString" in seen[0]
    assert seen[0]["virtualMatchString"] == "cpe:2.3:a:openbsd:openssh:8.0"
    # And it must not send the old all-tokens-must-match keyword query.
    assert all(p.get("keywordSearch") != "openssh 8.0" for p in seen)


def test_parse_cve_falls_back_through_cvss_versions():
    """Only v3.1 was read before; everything else scored 0."""
    v2_only = {
        "cve": {
            "id": "CVE-2011-0001",
            "descriptions": [{"lang": "en", "value": "old bug"}],
            "metrics": {"cvssMetricV2": [{"cvssData": {"baseScore": 7.5}, "baseSeverity": "HIGH"}]},
        }
    }
    parsed = _parse_cve(v2_only)
    assert parsed["score"] == 7.5
    assert parsed["severity"] == "HIGH"


def test_parse_cve_survives_empty_metric_list():
    """metrics present but empty used to raise IndexError."""
    entry = {"cve": {"id": "CVE-X", "descriptions": [], "metrics": {"cvssMetricV31": []}}}
    parsed = _parse_cve(entry)
    assert parsed["score"] == 0
    assert parsed["id"] == "CVE-X"


def test_parse_cve_prefers_english_description():
    entry = {
        "cve": {
            "id": "CVE-Y",
            "descriptions": [
                {"lang": "es", "value": "descripcion"},
                {"lang": "en", "value": "english text"},
            ],
            "metrics": {},
        }
    }
    assert _parse_cve(entry)["description"] == "english text"


# ---------------------------------------------------------------------------
# Shared-context handoff
# ---------------------------------------------------------------------------

def test_missing_context_key_reports_not_found(tmp_path, monkeypatch):
    """A failed handoff returned status 'success' with findings=None."""
    from secureflow.crew.memory import SharedContext
    from secureflow.crew.tools import ContextManager

    monkeypatch.setattr(
        ContextManager, "_context", SharedContext(db_path=str(tmp_path / "ctx.db"))
    )
    ContextManager.save_findings("recon", "scan_results", "ports 22,80")

    hit = ContextManager.read_findings("recon", "scan_results")
    assert hit["status"] == "success"
    assert hit["findings"] == "ports 22,80"

    miss = ContextManager.read_findings("recon", "wrong_key")
    assert miss["status"] == "not_found"
    assert miss["findings"] is None
    assert "scan_results" in miss["available_keys"]


def test_agents_and_tasks_agree_on_context_keys():
    """The agent backstory and the task prompt named different keys."""
    from pathlib import Path

    root = Path(__file__).parent.parent / "secureflow" / "crew"
    agents_src = (root / "agents.py").read_text()
    tasks_src = (root / "tasks.py").read_text()

    assert "recon_scan_results" not in agents_src
    assert "scan_results" in agents_src
    assert "scan_results" in tasks_src


# ---------------------------------------------------------------------------
# Severity tally feeding the dashboard
# ---------------------------------------------------------------------------

def test_severity_counts_start_empty():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    assert tools.severity_counts() == {"critical": 0, "high": 0, "medium": 0, "low": 0}


def test_record_finding_tallies_by_severity():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("HIGH", "openssh", "CVE-1")
    tools.record_finding("critical", "apache", "CVE-2")
    tools.record_finding("Medium", "apache", "CVE-3")

    counts = tools.severity_counts()
    assert counts["high"] == 1
    assert counts["critical"] == 1
    assert counts["medium"] == 1


def test_findings_deduplicate_by_reference():
    """The same CVE seen twice must not inflate the count."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    for _ in range(3):
        tools.record_finding("high", "openssh", "CVE-2020-15778")

    assert tools.severity_counts()["high"] == 1


def test_unknown_severity_is_ignored_not_guessed():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("UNKNOWN", "x", "CVE-9")
    tools.record_finding("", "y", "CVE-10")
    tools.record_finding(None, "z", "CVE-11")

    assert sum(tools.severity_counts().values()) == 0


def test_clear_findings_resets_between_scans():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("critical", "x", "CVE-1")
    tools.clear_findings()

    assert sum(tools.severity_counts().values()) == 0


def test_cve_lookup_records_real_cvss_severities(monkeypatch):
    """Counts come from NVD baseSeverity, not from keywords in agent prose."""
    import secureflow.crew.tools as tools_mod

    payload = {
        "totalResults": 2,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-A",
                    "descriptions": [{"lang": "en", "value": "a"}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}
                        ]
                    },
                }
            },
            {
                "cve": {
                    "id": "CVE-B",
                    "descriptions": [{"lang": "en", "value": "b"}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 5.3, "baseSeverity": "MEDIUM"}}
                        ]
                    },
                }
            },
        ],
    }

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return payload

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    tools.lookup_cve("openssh", "8.0")

    counts = tools.severity_counts()
    assert counts["critical"] == 1
    assert counts["medium"] == 1
    assert counts["high"] == 0


def test_orchestrator_emits_findings_event(tmp_path, monkeypatch):
    from secureflow.crew.orchestrator import CrewOrchestrator
    from secureflow.crew.tools import security_tools

    security_tools.clear_findings()
    security_tools.record_finding("high", "openssh", "CVE-2020-15778")

    orch = CrewOrchestrator(log_path=str(tmp_path / "c.log"))
    orch._emit_findings()

    event = orch.message_queue.get_nowait()
    assert event["event"] == "findings"
    assert event["counts"]["high"] == 1
    security_tools.clear_findings()


def test_orchestrator_emits_nothing_when_no_findings(tmp_path):
    """An empty tally must not push a misleading all-zero summary."""
    from secureflow.crew.orchestrator import CrewOrchestrator
    from secureflow.crew.tools import security_tools

    security_tools.clear_findings()
    orch = CrewOrchestrator(log_path=str(tmp_path / "d.log"))
    orch._emit_findings()

    assert orch.message_queue.empty()
