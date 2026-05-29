"""Test crew tools."""

import os
import ssl
import socket
import tempfile
import threading
import http.server
import socketserver
import subprocess
import time

import pytest
import json


def test_security_tools_instantiation():
    """Test that SecurityTools can be instantiated."""
    from secureflow.crew.tools import SecurityTools

    tools = SecurityTools()
    assert tools is not None


def test_dev_tools_instantiation():
    """Test that DevTools can be instantiated."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    assert tools is not None


def test_design_system_tool():
    """Test design_system tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.design_system_impl("Build a web application")
    assert isinstance(result, dict)
    assert "architecture" in result
    assert result["status"] == "success"


def test_recommend_stack_tool():
    """Test recommend_stack tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.recommend_stack_impl("Build a web application", "python")
    assert isinstance(result, dict)
    assert "stack" in result
    assert result["status"] == "success"


def test_plan_structure_tool():
    """Test plan_structure tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.plan_structure_impl("web", "python")
    assert isinstance(result, dict)
    assert "structure" in result
    assert result["status"] == "success"


def test_write_code_tool():
    """Test write_code tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    result = tools.write_code_impl("Calculate fibonacci", "python")
    assert isinstance(result, dict)
    assert "code" in result
    assert result["status"] == "success"


def test_review_code_tool():
    """Test review_code tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "def hello(): print('world')"
    result = tools.review_code_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert "quality_score" in result


def test_find_bugs_tool():
    """Test find_bugs tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "def test(): pass"
    result = tools.find_bugs_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"


def test_suggest_improvements_tool():
    """Test suggest_improvements tool implementation."""
    from secureflow.crew.tools import DevTools

    tools = DevTools()
    code = "x=1+2"
    result = tools.suggest_improvements_impl(code, "python")
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert "suggestions" in result


# ----------------------------------------------------------------------
# Target validation (security: no injection / abuse)
# ----------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "", "-oG/tmp/x", "; rm -rf /", "$(whoami)", "a b c", "a;b",
    "x" * 300,  # exceeds DNS length limit
])
def test_validate_target_rejects_bad_input(bad):
    """Malformed / flag-like / overlong targets must be rejected."""
    from secureflow.crew.tools import _validate_target
    assert _validate_target(bad) is False


@pytest.mark.parametrize("good", ["example.com", "127.0.0.1", "10.0.0.0/24", "host_name", "a.b.c.d"])
def test_validate_target_accepts_valid(good):
    from secureflow.crew.tools import _validate_target
    assert _validate_target(good) is True


@pytest.mark.parametrize("bad", ["", "-x", "$(id)", "a;b", "x" * 5000, "../../etc/passwd"])
def test_web_tools_never_raise_on_hostile_input(bad):
    """Web/DNS/TLS tools must degrade to a clean error dict, never raise."""
    from secureflow.crew.tools import security_tools as ST
    for fn in (ST.http_fingerprint, ST.dns_enum, ST.tls_inspect,
               ST.probe_paths, ST.http_security_headers):
        result = fn(bad)
        assert result["status"] == "error"


# ----------------------------------------------------------------------
# Pure-function logic
# ----------------------------------------------------------------------

def test_detect_technologies():
    """Header/cookie signatures map to technology names."""
    from secureflow.crew.tools import SecurityTools
    techs = SecurityTools._detect_technologies(
        {"server": "nginx/1.18.0", "x-powered-by": "PHP/7.4"},
        "wordpress_logged_in=1; phpsessid=abc",
    )
    assert "nginx" in techs
    assert "PHP" in techs
    assert "WordPress" in techs


def test_grab_banner_reads_line():
    """_grab_banner returns the first line of a service banner."""
    from secureflow.crew.tools import SecurityTools
    a, b = socket.socketpair()
    try:
        b.sendall(b"SSH-2.0-OpenSSH_8.9\r\nextra\r\n")
        banner = SecurityTools._grab_banner(a)
        assert banner == "SSH-2.0-OpenSSH_8.9"
    finally:
        a.close()
        b.close()


# ----------------------------------------------------------------------
# Live local HTTP target (deliberately vulnerable)
# ----------------------------------------------------------------------

@pytest.fixture
def vuln_http_server():
    """A local HTTP server with an exposed /.env, no security headers, fake banner."""
    webroot = tempfile.mkdtemp(prefix="sf_test_")
    with open(os.path.join(webroot, ".env"), "w") as f:
        f.write("SECRET=test\n")
    with open(os.path.join(webroot, "index.html"), "w") as f:
        f.write("<html><head><title>Test Portal</title></head><body>ok</body></html>")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=webroot, **k)

        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Server", "nginx/1.18.0")
            self.send_header("X-Powered-By", "PHP/7.4.3")
            super().end_headers()

    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    time.sleep(0.2)
    try:
        yield f"127.0.0.1:{port}"
    finally:
        httpd.shutdown()


def test_http_fingerprint_live(vuln_http_server):
    from secureflow.crew.tools import security_tools as ST
    r = ST.http_fingerprint(vuln_http_server)
    assert r["status"] == "success"
    assert r["http_status"] == 200
    assert r["title"] == "Test Portal"
    assert "nginx" in r["technologies"]
    assert "PHP" in r["technologies"]


def test_security_headers_live(vuln_http_server):
    from secureflow.crew.tools import security_tools as ST
    r = ST.http_security_headers(vuln_http_server)
    assert r["status"] == "success"
    # Server sends none of the protective headers
    assert len(r["missing"]) == 6
    assert r["grade_pct"] == 0


def test_probe_paths_live(vuln_http_server):
    from secureflow.crew.tools import security_tools as ST
    r = ST.probe_paths(vuln_http_server)
    assert r["status"] == "success"
    found = {f["path"] for f in r["findings"]}
    assert "/.env" in found
    assert r["exposed_count"] >= 1


# ----------------------------------------------------------------------
# Live local TLS server (self-signed)
# ----------------------------------------------------------------------

@pytest.fixture
def self_signed_tls_server():
    """A local TLS server presenting a short-lived self-signed cert."""
    certdir = tempfile.mkdtemp(prefix="sf_tls_")
    certfile = os.path.join(certdir, "cert.pem")
    keyfile = os.path.join(certdir, "key.pem")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", keyfile,
         "-out", certfile, "-days", "10", "-nodes", "-subj", "/CN=test.local"],
        capture_output=True, check=True,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(5)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile, keyfile)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                c, _ = sock.accept()
            except OSError:
                break
            try:
                ctx.wrap_socket(c, server_side=True).close()
            except Exception:
                try:
                    c.close()
                except Exception:
                    pass

    threading.Thread(target=serve, daemon=True).start()
    time.sleep(0.2)
    try:
        yield port
    finally:
        stop.set()
        sock.close()


def test_tls_inspect_live(self_signed_tls_server):
    from secureflow.crew.tools import security_tools as ST
    r = ST.tls_inspect("127.0.0.1", port=self_signed_tls_server)
    assert r["status"] == "success"
    assert r["protocol"].startswith("TLS")
    cert = r["certificate"]
    assert "test.local" in cert["subject"]
    assert cert["self_signed"] is True
    assert "self-signed" in " ".join(r["warnings"]).lower()


def test_dns_enum_validation():
    """DNS enum rejects malformed domains without network access."""
    from secureflow.crew.tools import security_tools as ST
    assert ST.dns_enum("-bad")["status"] == "error"
    assert ST.dns_enum("a b c")["status"] == "error"
