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

def test_cpe_for_is_pure_string_formatting():
    """_cpe_for no longer resolves a vendor itself — that's _resolve_cpe_vendor's
    job now (queried dynamically against NVD). This is just formatting."""
    assert _cpe_for("openbsd", "openssh", "8.0") == "cpe:2.3:a:openbsd:openssh:8.0"
    assert _cpe_for("igor_sysoev", "nginx", "1.18.0") == "cpe:2.3:a:igor_sysoev:nginx:1.18.0"


def test_cpe_sanitises_hostile_input():
    cpe = _cpe_for("evil; rm -rf /", "product", "1.0")
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
    # Isolate this test to CVE-search construction — vendor resolution has its
    # own dedicated tests below. Also stub OSV: it calls requests.post, which
    # this test never mocked, so it was silently making a real network call.
    monkeypatch.setattr(tools_mod.SecurityTools, "_resolve_cpe_vendor", lambda self, p: "openbsd")
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])

    tools_mod.SecurityTools().lookup_cve("openssh", "8.0")

    cpe_calls = [p for p in seen if "virtualMatchString" in p]
    assert cpe_calls, f"no CPE-strategy call was made: {seen}"
    assert cpe_calls[0]["virtualMatchString"] == "cpe:2.3:a:openbsd:openssh:8.0"
    # And it must not send the old all-tokens-must-match keyword query.
    assert all(p.get("keywordSearch") != "openssh 8.0" for p in seen)


# ---------------------------------------------------------------------------
# Dynamic CPE vendor resolution against NVD's own dictionary
#
# The previous static table was never checked against real data and was
# simply wrong for several common products — verified directly:
#   mysql -> "oracle" (real: "mysql"), nginx -> "nginx" (real: "igor_sysoev"),
#   vsftpd -> "vsftpd" (real: "vsftpd_project"), redis had no entry at all and
#   a naive first-keyword-hit resolves to an unrelated "att" product.
# ---------------------------------------------------------------------------

def _cpe_dict_response(entries):
    """Build a fake NVD CPE dictionary response from (vendor, product) pairs."""
    return {
        "products": [
            {"cpe": {"cpeName": f"cpe:2.3:a:{vendor}:{product}:1.0:*:*:*:*:*:*:*"}}
            for vendor, product in entries
        ]
    }


def test_resolve_cpe_vendor_majority_votes_exact_product_matches(monkeypatch):
    """A naive 'trust the first hit' approach is unreliable — keywordSearch is
    full-text and its top result can be an unrelated product. Filtering to
    exact product-field matches and taking the majority vendor is what
    actually resolves correctly (verified against real NVD data: redis ->
    pivotal_software, 18/20 exact matches agreeing)."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response(
                [("pivotal_software", "redis")] * 4
                + [("att", "redis-something-else")] * 3  # different product field
            )

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe_vendor("redis") == "pivotal_software"


def test_resolve_cpe_vendor_falls_back_to_static_table_when_nvd_unreachable(monkeypatch):
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise tools_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe_vendor("openssh") == "openbsd"


def test_resolve_cpe_vendor_falls_back_to_product_name_when_totally_unknown(monkeypatch):
    """No network, and not in the static table either — must not crash."""
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise tools_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe_vendor("some_totally_unknown_product") == "some_totally_unknown_product"


def test_resolve_cpe_vendor_caches_and_does_not_requery(monkeypatch):
    import secureflow.crew.tools as tools_mod

    calls = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response([("mysql", "mysql")])

    def _fake_get(*a, **k):
        calls.append(1)
        return _Resp()

    monkeypatch.setattr(tools_mod.requests, "get", _fake_get)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe_vendor("mysql") == "mysql"
    assert tools._resolve_cpe_vendor("mysql") == "mysql"
    assert len(calls) == 1, "second call must be served from cache, not re-queried"


def test_resolve_cpe_vendor_ignores_no_exact_product_match(monkeypatch):
    """If nothing in the dictionary response has a matching product field,
    that's not a resolution — fall back rather than trust an unrelated hit."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response([("adobe", "totally_different_product")])

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    # "php" is in the static fallback table and correct there.
    assert tools._resolve_cpe_vendor("php") == "php"


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
    # OSV is queried via POST; leaving it unstubbed lets the test hit the network.
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
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


# ---------------------------------------------------------------------------
# OSV complement to NVD
# ---------------------------------------------------------------------------

def test_osv_lookup_needs_a_version():
    """Without a version there is nothing to match on; don't call the API."""
    from secureflow.crew.tools import _osv_lookup

    assert _osv_lookup("openssh", "") == []


def test_osv_prefers_the_cve_alias_so_results_dedupe(monkeypatch):
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "vulns": [
                    {
                        "id": "GHSA-aaaa-bbbb-cccc",
                        "aliases": ["CVE-2020-15778"],
                        "summary": "scp injection",
                        "severity": [{"type": "CVSS_V3", "score": "7.4"}],
                    }
                ]
            }

    monkeypatch.setattr(tools_mod.requests, "post", lambda *a, **k: _Resp())
    findings = tools_mod._osv_lookup("openssh", "8.0")

    assert findings[0]["id"] == "CVE-2020-15778"
    assert findings[0]["severity"] == "high"
    assert findings[0]["source"] == "osv"


def test_osv_network_failure_is_not_fatal(monkeypatch):
    """OSV is a complement; if it is unreachable the NVD result still stands."""
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise tools_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(tools_mod.requests, "post", _boom)
    assert tools_mod._osv_lookup("openssh", "8.0") == []


def test_lookup_merges_osv_findings_without_duplicating_nvd(monkeypatch):
    import secureflow.crew.tools as tools_mod

    nvd_payload = {
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-SHARED",
                    "descriptions": [{"lang": "en", "value": "shared"}],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 7.4, "baseSeverity": "HIGH"}}
                        ]
                    },
                }
            }
        ],
    }

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return nvd_payload

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        tools_mod,
        "_osv_lookup",
        lambda *a, **k: [
            {"id": "CVE-SHARED", "severity": "high", "score": 7.4, "source": "osv"},
            {"id": "CVE-OSV-ONLY", "severity": "critical", "score": 9.8, "source": "osv"},
        ],
    )

    result = tools_mod.SecurityTools().lookup_cve("openssh", "8.0")
    ids = sorted(c["id"] for c in result["cves"])

    assert ids == ["CVE-OSV-ONLY", "CVE-SHARED"]
    assert result["cve_count"] == 2
    assert "osv" in result["sources"]


def test_severity_label_thresholds():
    from secureflow.crew.tools import _label_for_score

    assert _label_for_score(9.8) == "critical"
    assert _label_for_score(7.4) == "high"
    assert _label_for_score(5.3) == "medium"
    assert _label_for_score(2.1) == "low"


# ---------------------------------------------------------------------------
# CVE lookup must refuse a meaningless bare-protocol-name query
#
# Live-verified: nmap isn't installed in this environment, so the socket-scan
# fallback only ever returns a generic label like "http"/"https" with no
# version. lookup_cve("http", "") fell through to NVD's keywordSearch on that
# single common word, matching 10 of 17,631 CVEs that happen to mention "http"
# somewhere in 25 years of NVD history — arbitrary, not findings for the
# actual target. A real end-to-end crew run against scanme.nmap.org (using a
# genuine Gemini key) wrote these into the report as CRITICAL/HIGH findings
# for 1999-2001-era products (a defunct antivirus proxy, an abandoned web
# server) almost certainly not running on that host.
# ---------------------------------------------------------------------------

def test_lookup_cve_refuses_bare_protocol_label_without_version():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    result = tools.lookup_cve("http", "")

    assert result["status"] == "insufficient_data"
    assert result["cve_count"] == 0
    assert result["cves"] == []
    assert "nmap" in result["message"]


def test_lookup_cve_refuses_every_generic_service_label(monkeypatch):
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise AssertionError("must not reach the network for a bare protocol label")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.requests, "post", _boom)

    tools = tools_mod.SecurityTools()
    for label in ("ssh", "https", "ftp", "telnet", "smtp", "rdp", "vnc"):
        result = tools.lookup_cve(label, "")
        assert result["status"] == "insufficient_data", label


def test_lookup_cve_with_real_product_and_version_is_unaffected(monkeypatch):
    """The refusal must be specific to bare labels, not swallow real lookups."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    result = tools_mod.SecurityTools().lookup_cve("openssh", "8.0")
    assert result["status"] == "success"


def test_lookup_cve_with_version_for_generic_label_is_unaffected(monkeypatch):
    """A version turns a generic label into a real query — e.g. 'http' isn't
    usually versioned, but 'ssh 8.0' or similar should still be attempted."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    result = tools_mod.SecurityTools().lookup_cve("ssh", "8.0")
    assert result["status"] == "success"


def test_assess_vulnerability_reports_unknown_not_low_when_data_is_insufficient():
    """Missing data must read as 'we don't know', never as a clean bill of health."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    result = tools.assess_vulnerability("80/tcp", "http", "")

    assert result["risk_level"] == "unknown"
    assert result["cve_data"]["status"] == "insufficient_data"


def test_assess_vulnerability_still_reports_low_for_a_real_clean_result(monkeypatch):
    """A genuinely-checked product/version with zero CVEs is real signal — must
    stay 'low', not be swept into the new 'unknown' bucket."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    result = tools.assess_vulnerability("22/tcp", "openssh", "99.9-fake-clean-version")

    assert result["risk_level"] == "low"
    assert result["cve_data"]["status"] == "success"


def test_generate_recommendations_flags_unknown_risk_services():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    recs = tools.generate_recommendations([{"risk_level": "unknown"}])

    assert any("UNKNOWN" in r and "nmap" in r for r in recs)


def test_lookup_cve_catches_nmap_ssl_tunnel_notation():
    """nmap denotes an SSL/TLS-wrapped service as 'tunnel/protocol' (e.g.
    'ssl/http'), its own documented convention. Live-verified against a real
    nmap -sV scan of scanme.nmap.org: it reported exactly 'ssl/http', which
    the exact-match generic-label check missed, and the query fell through to
    the unbounded keyword search this whole guard exists to prevent."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    for label in ("ssl/http", "ssl/https", "ssl/imap", "tls/ftp"):
        result = tools.lookup_cve(label, "")
        assert result["status"] == "insufficient_data", label
