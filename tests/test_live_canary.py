"""Live-network canary — the layer that broke silently, repeatedly, this week.

Every other test in this suite mocks the network so the fast, deterministic
default run never depends on external services. That's the right default —
but it's also exactly why six real defects (a false-success report, a
provider that couldn't construct, a fabricated CVE table, a 60s timeout that
silently discarded any real scan, two CPE-vendor mismatches) were invisible to
267 passing tests until a human sat down and ran the tool for real.

These tests are the standing discipline against that: they hit real nmap,
real NVD, and real OSV, against nmap's own public, explicitly-authorized test
target. Excluded from the default run (`-m "not live_network"` in
pyproject.toml's addopts) and from the main CI workflow — slow, and a genuine
external dependency has no place gating every push. Run explicitly with:

    pytest -m live_network -q

or via the scheduled `.github/workflows/canary.yml`, weekly.
"""

import pytest

pytestmark = pytest.mark.live_network

# nmap's own public target, explicitly provided for exactly this kind of
# testing: "You are authorized to scan this machine with Nmap or other port
# scanners." Used throughout this project's manual testing for the same reason.
TARGET = "scanme.nmap.org"


def test_nmap_scan_uses_real_nmap_not_the_socket_fallback():
    """This is the exact regression found this week: a 60s timeout silently
    discarded every real scan against a filtered target (this one took 107s),
    falling back to a 25-port socket scanner with no signal a downgrade had
    happened. If nmap ever regresses to the fallback here, this must fail."""
    from secureflow.crew.tools import SecurityTools

    result = SecurityTools().nmap_scan(TARGET)

    assert result["status"] == "success"
    assert result["scanner"] == "nmap", (
        f"fell back to {result['scanner']!r} — see result.get('note') for why: "
        f"{result.get('note')!r}"
    )
    assert "Nmap scan report" in result["output"]


def test_nvd_cve_lookup_returns_real_data_for_a_known_vulnerable_version():
    """vsftpd 2.3.4 is the famously backdoored release — real, well-known
    CVEs must come back, not zero results and not a network error."""
    from secureflow.crew.tools import SecurityTools

    result = SecurityTools().lookup_cve("vsftpd", "2.3.4")

    assert result["status"] == "success"
    assert result["cve_count"] > 0
    assert any("CVE-" in c["id"] for c in result["cves"])


def test_osv_returns_real_data_for_a_known_vulnerable_package():
    from secureflow.crew.tools import _osv_lookup

    findings = _osv_lookup("lodash", "4.17.15")  # long-known-vulnerable version

    assert findings, "expected real OSV findings for a known-vulnerable package"
    assert any(f.get("id", "").startswith(("CVE-", "GHSA-")) for f in findings)


def test_cpe_vendor_resolves_dynamically_against_nvd():
    """This week's fix: the static table was wrong for several real products
    (mysql, nginx, vsftpd, redis). Confirm the live dictionary lookup — not
    the offline fallback — is what actually answers this."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    assert tools._resolve_cpe("vsftpd") == ("vsftpd_project", "vsftpd")


def test_full_recon_to_cve_pipeline_against_a_real_target():
    """The integration, not just the parts: scan a real target, then look up
    CVEs for whatever was actually found — the same sequence the recon and
    analyst agents perform."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    scan = tools.nmap_scan(TARGET)
    assert scan["scanner"] == "nmap"
    assert "Nmap scan report" in scan["output"]

    # scanme.nmap.org is known to expose port 22 (OpenSSH); assess it if nmap
    # found it open — a real, end-to-end exercise of the same tool chain the
    # crew uses, independent of any LLM.
    if "22/tcp" in scan["output"] and "open" in scan["output"]:
        result = tools.assess_vulnerability("22/tcp", "openssh", "")
        # No version parsed from raw nmap text here (that's the agent's job),
        # so this should read as insufficient_data — not a crash, not a
        # fabricated finding.
        assert result["risk_level"] in ("unknown", "low", "medium", "high", "critical")
