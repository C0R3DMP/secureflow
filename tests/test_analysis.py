"""Tests that the analysis tools measure rather than fabricate.

Before these fixes the dev tools returned fixed values for any input:
`bugs_found: 0`, `quality_score: 85`, `tests_run: 3, tests_passed: 3`. Those
numbers were fed to an LLM as tool output and written into review reports.
"""

import json

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
    """_cpe_for no longer resolves a vendor itself — that's _resolve_cpe's
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
    monkeypatch.setattr(tools_mod.SecurityTools, "_resolve_cpe", lambda self, p: ("openbsd", "openssh"))
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


def test_resolve_cpe_prefers_exact_product_matches_over_raw_majority(monkeypatch):
    """A plain majority vote picks whichever product happens to have the most
    version rows — verified live against real NVD data, that resolves "php" to
    php:blog_cms. Preferring results whose product field exactly equals the
    query is what actually resolves correctly."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response(
                [("php", "blog_cms")] * 9  # more rows, but the wrong product
                + [("php", "php")] * 2     # fewer rows, but an exact match
            )

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe("php") == ("php", "php")


def test_resolve_cpe_resolves_the_product_half_not_just_the_vendor(monkeypatch):
    """NVD's CPE product field often differs from the scanner's name.
    Live-verified: nmap reports "Apache httpd", whose real CPE product is
    "http_server" — keeping the caller's own string built
    apache_httpd:apache_httpd, which matches nothing, so a correct versioned
    lookup still found zero of the 108 real CVEs for that version."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response([("apache", "http_server")] * 5)

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe("Apache httpd") == ("apache", "http_server")


def test_resolve_cpe_queries_with_the_raw_string_not_the_underscored_one(monkeypatch):
    """keywordSearch is a natural-language text search: live-verified,
    "apache_httpd" returns 0 results where "apache http server" returns 574.
    Normalising before querying silently broke every multi-word product."""
    import secureflow.crew.tools as tools_mod

    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return _cpe_dict_response([("apache", "http_server")])

    def _fake_get(url, params=None, **k):
        seen["keyword"] = (params or {}).get("keywordSearch")
        return _Resp()

    monkeypatch.setattr(tools_mod.requests, "get", _fake_get)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools_mod.SecurityTools()._resolve_cpe("Apache httpd")
    assert "_" not in seen["keyword"], f"queried NVD with {seen['keyword']!r}"


def test_resolve_cpe_falls_back_to_static_table_when_nvd_unreachable(monkeypatch):
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise tools_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe("openssh") == ("openbsd", "openssh")


def test_resolve_cpe_falls_back_to_product_name_when_totally_unknown(monkeypatch):
    """No network, and not in the static table either — must not crash."""
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise tools_mod.requests.exceptions.ConnectionError("offline")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe("some_totally_unknown_product") == (
        "some_totally_unknown_product",
        "some_totally_unknown_product",
    )


def test_resolve_cpe_falls_back_when_the_dictionary_returns_nothing(monkeypatch):
    """An empty result set is not a resolution — fall back to the static
    table rather than inventing one."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"products": []}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    assert tools._resolve_cpe("openssh") == ("openbsd", "openssh")


def test_resolve_cpe_caches_and_does_not_requery(monkeypatch):
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
    assert tools._resolve_cpe("mysql") == ("mysql", "mysql")
    assert tools._resolve_cpe("mysql") == ("mysql", "mysql")
    assert len(calls) == 1, "second call must be served from cache, not re-queried"


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


def test_record_finding_defaults_to_likely_confidence():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("high", "openssh", "CVE-1")

    [finding] = tools.get_findings()
    assert finding["confidence"] == "likely"


def test_get_findings_returns_structured_deduplicated_list():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("critical", "openssh", "CVE-1", confidence="possible", description="d")
    tools.record_finding("critical", "openssh", "CVE-1", confidence="possible", description="d")  # dup

    findings = tools.get_findings()
    assert len(findings) == 1
    assert findings[0] == {
        "severity": "critical",
        "source": "openssh",
        "reference": "CVE-1",
        "confidence": "possible",
        "description": "d",
    }


def test_mark_confirmed_upgrades_matching_finding_only():
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    tools.record_finding("high", "openssh", "CVE-1", confidence="likely")
    tools.record_finding("high", "apache", "CVE-2", confidence="likely")
    tools.mark_confirmed("CVE-1")

    by_ref = {f["reference"]: f["confidence"] for f in tools.get_findings()}
    assert by_ref["CVE-1"] == "confirmed"
    assert by_ref["CVE-2"] == "likely"


def test_verify_with_nuclei_confirmed_upgrades_confidence(monkeypatch):
    """A real active-probe match must upgrade the passive finding it confirms,
    not just report success in isolation — that's the whole point of tracking
    confidence as a field the rest of the tool can act on."""
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")

    finding_line = json.dumps({"template-id": "CVE-2021-41773", "matched-at": "http://x/"})

    class _Match:
        returncode = 0
        stdout = finding_line + "\n"
        stderr = ""

    monkeypatch.setattr(tools_mod.subprocess, "run", lambda *a, **k: _Match())

    tools = tools_mod.SecurityTools()
    tools.record_finding("critical", "apache 2.4", "CVE-2021-41773", confidence="likely")
    tools.verify_with_nuclei("example.com", "CVE-2021-41773")

    [finding] = tools.get_findings()
    assert finding["confidence"] == "confirmed"


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


def test_cve_lookup_records_possible_confidence_when_cpe_misses_and_keyword_hits(monkeypatch):
    """A version IS known, but the CPE match found nothing and the keyword
    fallback did — that's a much looser match than an exact CPE hit, and must
    be recorded as "possible", not "likely"."""
    import secureflow.crew.tools as tools_mod

    keyword_payload = {
        "totalResults": 1,
        "vulnerabilities": [{
            "cve": {
                "id": "CVE-KEYWORD",
                "descriptions": [{"lang": "en", "value": "d"}],
                "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 5.0, "baseSeverity": "MEDIUM"}}]},
            }
        }],
    }

    calls = {"n": 0}

    class _Resp:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def _fake_get(*a, **k):
        calls["n"] += 1
        # First call is the CPE attempt (misses); second is the keyword fallback.
        if calls["n"] == 1:
            return _Resp({"vulnerabilities": [], "totalResults": 0})
        return _Resp(keyword_payload)

    monkeypatch.setattr(tools_mod.requests, "get", _fake_get)
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(tools_mod.SecurityTools, "_resolve_cpe", lambda self, p: ("vendor", "product"))

    tools = tools_mod.SecurityTools()
    result = tools.lookup_cve("some-obscure-product", "1.0")

    assert result["match_strategy"] == "keyword"
    [finding] = tools.get_findings()
    assert finding["confidence"] == "possible"


def test_cve_lookup_refuses_any_unversioned_lookup_even_for_a_specific_sounding_product(monkeypatch):
    """Live-verified this week: the recon agent guessed the product name
    'Apache HTTP Server' for a service nmap could only fingerprint as
    'ssl/http', and cve_lookup('Apache HTTP Server', '') matched 10 of 471
    CVEs spanning that product's entire history — none tied to the actual
    target. A specific-sounding invented name defeats any check keyed on
    known-generic strings; only refusing every unversioned lookup holds."""
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise AssertionError("must not query NVD/OSV without a version")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.requests, "post", _boom)

    tools = tools_mod.SecurityTools()
    result = tools.lookup_cve("Apache HTTP Server", "")

    assert result["status"] == "insufficient_data"
    assert result["cve_count"] == 0


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
    assert "version" in result["message"].lower()


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
    assert result["confidence"] == "insufficient_data"
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
    assert result["confidence"] == "high"  # a real check ran and found nothing
    assert result["cve_data"]["status"] == "success"


def test_assess_vulnerability_reports_unknown_confidence_on_lookup_error(monkeypatch):
    """A failed lookup (network error, non-200) is a different kind of unknown
    than never having enough data to check — both map to risk 'unknown', but
    confidence must say which one happened rather than collapsing them."""
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(
        tools_mod.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(tools_mod.requests.exceptions.ConnectionError("boom")),
    )
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)

    tools = tools_mod.SecurityTools()
    result = tools.assess_vulnerability("22/tcp", "openssh", "8.0")

    assert result["risk_level"] == "unknown"
    assert result["confidence"] == "unknown"
    assert result["cve_data"]["status"] == "error"


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


# ---------------------------------------------------------------------------
# The agent-facing tools must be able to pass a version at all.
#
# Live-verified root cause: the recon agent correctly fingerprinted
# "Apache httpd 2.4.7" (the genuine banner on scanme.nmap.org) but called
# lookup_cves("Apache httpd 2.4.7") — because the tool signature had no
# version parameter, so there was nowhere else to put it. Every lookup the
# crew could physically make was therefore version-less: fabricated CVEs
# before the unversioned-lookup guard, and zero findings after it.
# ---------------------------------------------------------------------------

def test_agent_facing_tools_accept_a_version_argument():
    import secureflow.crew.tools as tools_mod

    for tool in (tools_mod.lookup_cves, tools_mod.assess_service):
        fields = set(tool.args_schema.model_fields)
        assert "version" in fields, f"{tool.name} cannot pass a version: {fields}"


def test_lookup_cves_tool_forwards_the_version(monkeypatch):
    import secureflow.crew.tools as tools_mod

    seen = {}
    monkeypatch.setattr(
        tools_mod.security_tools, "lookup_cve",
        lambda product, version="": seen.update(product=product, version=version) or {"status": "ok"},
    )

    tools_mod.lookup_cves.run(product="Apache httpd", version="2.4.7")
    assert seen == {"product": "Apache httpd", "version": "2.4.7"}


def test_assess_service_tool_forwards_the_version(monkeypatch):
    import secureflow.crew.tools as tools_mod

    seen = {}
    monkeypatch.setattr(
        tools_mod.security_tools, "assess_vulnerability",
        lambda port, service, version="": seen.update(
            port=port, service=service, version=version) or {"status": "ok"},
    )

    tools_mod.assess_service.run(port="80/tcp", service="Apache httpd", version="2.4.7")
    assert seen == {"port": "80/tcp", "service": "Apache httpd", "version": "2.4.7"}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Apache httpd 2.4.7", ("Apache httpd", "2.4.7")),
        ("nginx 1.18.0", ("nginx", "1.18.0")),
        ("OpenSSH 8.0p1", ("OpenSSH", "8.0p1")),
        ("Apache HTTP Server", ("Apache HTTP Server", "")),  # 'Server' is not a version
        ("nginx", ("nginx", "")),
        ("", ("", "")),
    ],
)
def test_split_product_version(raw, expected):
    """A model can always phrase it as one string even with the signature
    fixed, so a crammed version is recovered rather than thrown away."""
    from secureflow.crew.tools import _split_product_version

    assert _split_product_version(raw) == expected


def test_lookup_cve_recovers_a_crammed_version_instead_of_refusing(monkeypatch):
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        tools_mod.SecurityTools, "_resolve_cpe", lambda self, p: ("apache", "http_server"))

    result = tools_mod.SecurityTools().lookup_cve("Apache httpd 2.4.7")

    assert result["status"] == "success"
    assert result["version"] == "2.4.7"
    assert result["product"] == "Apache httpd"


# ---------------------------------------------------------------------------
# Nuclei active-verification pass
#
# Roadmap item "Now #2". Live-verified end-to-end against scanme.nmap.org
# after building nuclei from source and cloning its templates: -id CVE-XXXX
# genuinely confirms behaviour (Apache/2.4.7 detected via a real active
# probe), and a nonexistent template id exits nonzero with "no templates
# provided for scan" on stderr — the signal used to distinguish "no template
# exists for this CVE" from "ran and found nothing".
# ---------------------------------------------------------------------------

def test_verify_with_nuclei_rejects_malformed_cve_id():
    """cve_id feeds into argv as -id <value> — validate the shape rather than
    trust it, even though list-form subprocess.run already prevents injection."""
    from secureflow.crew.tools import SecurityTools

    result = SecurityTools().verify_with_nuclei("example.com", "not-a-cve")
    assert result["status"] == "error"


def test_verify_with_nuclei_rejects_invalid_target():
    from secureflow.crew.tools import SecurityTools

    result = SecurityTools().verify_with_nuclei("--script=/tmp/evil.nse", "CVE-2021-41773")
    assert result["status"] == "error"


def test_verify_with_nuclei_reports_not_installed(monkeypatch):
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: None)

    result = tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-2021-41773")
    assert result["status"] == "not_installed"


def test_verify_with_nuclei_distinguishes_no_template_from_no_match(monkeypatch):
    """Live-verified: nuclei exits nonzero with 'no templates provided for
    scan' on stderr when -id matches no template file at all — distinct from
    running cleanly and simply not matching."""
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")

    class _NoTemplate:
        returncode = 1
        stdout = ""
        stderr = "[FTL] Could not run nuclei: no templates provided for scan"

    monkeypatch.setattr(tools_mod.subprocess, "run", lambda *a, **k: _NoTemplate())

    result = tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-9999-99999")
    assert result["status"] == "no_template"


def test_verify_with_nuclei_reports_confirmed_on_real_match(monkeypatch):
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")

    finding_line = json.dumps({
        "template-id": "CVE-2021-41773",
        "matched-at": "http://example.com/icons/.%2e/%2e%2e/etc/passwd",
    })

    class _Match:
        returncode = 0
        stdout = finding_line + "\n"
        stderr = ""

    monkeypatch.setattr(tools_mod.subprocess, "run", lambda *a, **k: _Match())

    result = tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-2021-41773")
    assert result["status"] == "confirmed"
    assert result["template_id"] == "CVE-2021-41773"


def test_verify_with_nuclei_ran_no_match_never_reads_as_safe(monkeypatch):
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")

    class _NoMatch:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(tools_mod.subprocess, "run", lambda *a, **k: _NoMatch())

    result = tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-2021-41773")
    assert result["status"] == "ran_no_match"
    assert "does not prove" in result["message"]


def test_verify_with_nuclei_excludes_invasive_template_categories(monkeypatch):
    """Even 'safe' detection templates can send moderately invasive probes
    (verified live: an info-severity WAF-detection template sends a
    script-tag payload) — fuzz/dos/intrusive tags must be excluded."""
    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")
    captured = {}

    class _Resp:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Resp()

    monkeypatch.setattr(tools_mod.subprocess, "run", _fake_run)

    tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-2021-41773")

    assert "-etags" in captured["cmd"]
    etags_value = captured["cmd"][captured["cmd"].index("-etags") + 1]
    assert "intrusive" in etags_value and "fuzz" in etags_value and "dos" in etags_value


def test_verify_with_nuclei_times_out_gracefully(monkeypatch):
    import subprocess as subprocess_mod

    import secureflow.crew.tools as tools_mod

    monkeypatch.setattr(tools_mod.shutil, "which", lambda name: "/usr/local/bin/nuclei")

    def _timeout(cmd, **kwargs):
        raise subprocess_mod.TimeoutExpired(cmd, kwargs.get("timeout", 45))

    monkeypatch.setattr(tools_mod.subprocess, "run", _timeout)

    result = tools_mod.SecurityTools().verify_with_nuclei("example.com", "CVE-2021-41773")
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# A placeholder version must not unlock the lookup.
#
# Live-verified: with the version argument added to the tool, the recon agent
# called lookup_cves(product="Apache httpd", version="unknown") for a service
# nmap had explicitly reported as unrecognised. "unknown" is truthy, so it
# sailed past the empty-version guard, fell through to the whole-history
# keyword search, and returned CVE-1999-0236 / CVE-1999-0071 — 1999-era
# Apache CVEs — as findings for that target.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "placeholder", ["unknown", "Unknown", "n/a", "N/A", "none", "unspecified", "latest", "-", "?", ""]
)
def test_lookup_cve_rejects_placeholder_versions(placeholder, monkeypatch):
    import secureflow.crew.tools as tools_mod

    def _boom(*a, **k):
        raise AssertionError(f"must not query the network for version={placeholder!r}")

    monkeypatch.setattr(tools_mod.requests, "get", _boom)
    monkeypatch.setattr(tools_mod.requests, "post", _boom)

    result = tools_mod.SecurityTools().lookup_cve("Apache httpd", placeholder)

    assert result["status"] == "insufficient_data", placeholder
    assert result["cve_count"] == 0


@pytest.mark.parametrize("version", ["2.4.7", "8.0p1", "1.18.0", "10", "5.7.44-log"])
def test_lookup_cve_accepts_real_versions(version, monkeypatch):
    """The digit rule must not swallow genuine release identifiers."""
    import secureflow.crew.tools as tools_mod

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"vulnerabilities": [], "totalResults": 0}

    monkeypatch.setattr(tools_mod.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(tools_mod, "_osv_lookup", lambda *a, **k: [])
    monkeypatch.setattr(tools_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(
        tools_mod.SecurityTools, "_resolve_cpe", lambda self, p: ("vendor", "product"))

    result = tools_mod.SecurityTools().lookup_cve("some-product", version)
    assert result["status"] == "success", version


def test_insufficient_data_message_tells_the_model_not_to_guess():
    """The message is the model's only feedback channel — if it doesn't say
    'don't retry with a guess', the model retries with a guess."""
    from secureflow.crew.tools import SecurityTools

    message = SecurityTools().lookup_cve("Apache httpd", "unknown")["message"]
    lowered = message.lower()

    assert "placeholder" in lowered
    assert "do not retry" in lowered or "do not guess" in lowered
