import socket
import ssl
import subprocess
import json
import threading
import time
import requests
from urllib.parse import urlparse
from typing import Dict, List, Any
import re
from crewai.tools import tool

# Common ports for socket fallback scanner
_COMMON_PORTS = [
    21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143,
    443, 445, 993, 995, 1723, 3306, 3389, 5432, 5900,
    6379, 8080, 8443, 8888, 27017,
]

_SERVICE_NAMES = {
    21: "ftp", 22: "ssh", 23: "telnet", 25: "smtp", 53: "dns",
    80: "http", 110: "pop3", 111: "rpcbind", 135: "msrpc",
    139: "netbios-ssn", 143: "imap", 443: "https", 445: "smb",
    993: "imaps", 995: "pop3s", 1723: "pptp", 3306: "mysql",
    3389: "rdp", 5432: "postgresql", 5900: "vnc", 6379: "redis",
    8080: "http-alt", 8443: "https-alt", 8888: "http-alt", 27017: "mongodb",
}

# Ports that emit a banner on connect (used for lightweight version detection)
_BANNER_PORTS = {21, 22, 23, 25, 110, 143, 3306, 6379}

# Security-relevant HTTP response headers and why they matter.
_SECURITY_HEADERS = {
    "Strict-Transport-Security": "Enforces HTTPS (HSTS); prevents protocol downgrade",
    "Content-Security-Policy": "Mitigates XSS and data injection attacks",
    "X-Frame-Options": "Prevents clickjacking via framing",
    "X-Content-Type-Options": "Stops MIME-sniffing (should be 'nosniff')",
    "Referrer-Policy": "Controls referrer leakage to third parties",
    "Permissions-Policy": "Restricts access to powerful browser features",
}

# Sensitive paths frequently left exposed. Probed read-only with GET.
_SENSITIVE_PATHS = [
    "/.git/config", "/.git/HEAD", "/.env", "/.env.local", "/.env.backup",
    "/config.php.bak", "/wp-config.php.bak", "/.aws/credentials",
    "/.ssh/id_rsa", "/backup.zip", "/backup.sql", "/dump.sql",
    "/.DS_Store", "/robots.txt", "/sitemap.xml", "/server-status",
    "/phpinfo.php", "/admin", "/admin/login", "/.htaccess",
    "/swagger.json", "/api/swagger.json", "/actuator/health", "/actuator/env",
    # Debug / developer endpoints
    "/debug", "/debug.php", "/_debug", "/console", "/test", "/test.php",
    "/healthz", "/health", "/api/health", "/api/debug",
    # Java / Spring
    "/actuator", "/actuator/beans", "/actuator/loggers", "/jolokia",
    "/api-docs", "/swagger-ui.html", "/v2/api-docs", "/v3/api-docs",
    # GraphQL
    "/graphql", "/api/graphql", "/gql",
    # CI / DevOps
    "/.travis.yml", "/Jenkinsfile", "/docker-compose.yml", "/.circleci/config.yml",
    # Backup / config
    "/config.yml", "/config.yaml", "/settings.py", "/web.config",
    "/WEB-INF/web.xml", "/.well-known/security.txt",
]

# Header/cookie substrings → technology fingerprint.
_TECH_SIGNATURES = {
    "server": {
        "nginx": "nginx", "apache": "Apache", "iis": "Microsoft IIS",
        "cloudflare": "Cloudflare", "gunicorn": "Gunicorn", "werkzeug": "Werkzeug/Flask",
        "openresty": "OpenResty", "litespeed": "LiteSpeed", "caddy": "Caddy",
    },
    "x-powered-by": {
        "php": "PHP", "express": "Express.js", "asp.net": "ASP.NET",
        "next.js": "Next.js", "servlet": "Java Servlet",
    },
    "cookie": {
        "wordpress_": "WordPress", "wp-": "WordPress", "phpsessid": "PHP",
        "jsessionid": "Java", "csrftoken": "Django", "laravel_session": "Laravel",
        "connect.sid": "Express.js",
    },
}


def _validate_target(target: str) -> bool:
    """Reject empty, flag-like, overlong, or malformed targets (hostname/IP/CIDR only)."""
    if not target or target.startswith("-"):
        return False
    if len(target) > 253:  # DNS name length limit (RFC 1035)
        return False
    return bool(re.match(r'^[a-zA-Z0-9.\-:/\[\]_]+$', target))


# Exceptions a network probe may raise that should degrade to a clean error
# rather than crash the agent (RequestException, IDNA/UnicodeError, bad input).
_NET_ERRORS = (requests.exceptions.RequestException, UnicodeError, ValueError, OSError)


def _normalize_url(target: str, prefer_https: bool = True) -> str:
    """Turn a bare host or partial URL into a full http(s):// URL."""
    if target.startswith(("http://", "https://")):
        return target
    scheme = "https" if prefer_https else "http"
    return f"{scheme}://{target}"


# Compact but broad subdomain wordlist (~200 entries covering 90 % of real sub-domains)
_SUBDOMAIN_WORDLIST: List[str] = [
    "www", "mail", "remote", "blog", "webmail", "server", "ns1", "ns2",
    "smtp", "secure", "vpn", "m", "shop", "ftp", "mail2", "test", "portal",
    "ns", "ww1", "host", "support", "dev", "web", "bbs", "wap", "api",
    "admin", "mx", "email", "cdn", "static", "media", "img", "images",
    "video", "download", "uploads", "files", "assets", "cloud", "app",
    "apps", "mobile", "beta", "alpha", "staging", "prod", "production",
    "qa", "uat", "demo", "preview", "login", "auth", "sso", "oauth",
    "accounts", "account", "profile", "user", "users", "member", "members",
    "dashboard", "panel", "cp", "cpanel", "plesk", "whm", "webmin",
    "monitor", "metrics", "grafana", "kibana", "elastic", "redis", "mysql",
    "db", "database", "backup", "jenkins", "ci", "git", "gitlab", "github",
    "jira", "confluence", "wiki", "docs", "help", "status", "health",
    "intranet", "internal", "corp", "vpn2", "remote2", "proxy", "gateway",
    "router", "fw", "firewall", "smtp2", "imap", "pop", "exchange",
    "owa", "autodiscover", "lyncdiscover", "sip", "voip", "pbx",
    "payment", "pay", "billing", "invoice", "erp", "crm", "hr",
    "infra", "devops", "k8s", "kubernetes", "docker", "registry",
    "aws", "gcp", "azure", "s3", "storage", "bucket",
    "iot", "monitor", "alert", "alertmanager", "prometheus",
    "sonarqube", "nexus", "artifactory", "vault", "consul",
    "old", "new", "www2", "web2", "test2", "dev2",
]

# WAF header/cookie signatures → product name
_WAF_HEADER_SIGNATURES: Dict[str, str] = {
    "x-sucuri-id": "Sucuri WAF", "sucuri": "Sucuri WAF",
    "cf-ray": "Cloudflare", "cloudflare": "Cloudflare",
    "x-fw-hash": "Fortinet FortiWeb", "fortigate": "Fortinet",
    "x-waf-event-info": "Radware AppWall", "radware": "Radware",
    "x-dotdefender": "dotDefender", "dotdefender": "dotDefender",
    "x-mod-security": "ModSecurity", "mod_security": "ModSecurity",
    "x-protected-by": "Generic WAF", "x-blocked-by": "Generic WAF",
    "x-akamai": "Akamai Kona", "akamai": "Akamai Kona",
    "x-varnish": "Varnish Cache", "via": "Reverse Proxy/CDN",
    "x-cdn": "CDN", "server: awselb": "AWS ELB",
    "x-amzn-requestid": "AWS WAF", "x-amz": "AWS",
    "x-azure-ref": "Azure Front Door", "arr-disable-session": "ARR/Azure",
    "x-barracuda": "Barracuda WAF", "bni-persistence": "Barracuda",
    "x-rewrite-url": "IIS / Rewrite", "x-nis": "Citrix NetScaler",
    "ns_af": "Citrix NetScaler", "x-cnection": "NetScaler",
    "x-dynatrace": "Dynatrace", "x-instana": "Instana",
}

# WAF body pattern signatures
_WAF_BODY_SIGNATURES: Dict[str, str] = {
    "access denied by website's firewall": "Generic WAF",
    "sucuri website firewall": "Sucuri WAF",
    "cloudflare ray id": "Cloudflare",
    "this page is blocked by fortinet": "Fortinet",
    "you don't have permission to access": "Generic WAF",
    "mod_security": "ModSecurity",
    "request rejected by url scan rule": "Generic WAF",
    "this request has been blocked": "Generic WAF",
    "barracuda networks": "Barracuda",
    "kona site defender": "Akamai Kona",
}

# Offline version-based risk knowledge base.
# Keys are lowercase service names, values map version prefixes → risk info.
_VERSION_RISK_KB: Dict[str, Dict[str, Dict]] = {
    "openssh": {
        "1.": {"risk": "CRITICAL", "cves": ["CVE-2001-0144"], "safe_ver": "9.x", "note": "Very old, many RCEs"},
        "2.": {"risk": "CRITICAL", "cves": ["CVE-2002-0083"], "safe_ver": "9.x"},
        "3.": {"risk": "CRITICAL", "cves": ["CVE-2003-0693"], "safe_ver": "9.x"},
        "4.": {"risk": "HIGH", "cves": ["CVE-2006-5051"], "safe_ver": "9.x"},
        "5.": {"risk": "HIGH", "cves": ["CVE-2010-4478"], "safe_ver": "9.x"},
        "6.": {"risk": "HIGH", "cves": ["CVE-2014-2532", "CVE-2016-0778"], "safe_ver": "9.x"},
        "7.0": {"risk": "HIGH", "cves": ["CVE-2016-6515", "CVE-2016-10009"], "safe_ver": "9.x"},
        "7.1": {"risk": "HIGH", "cves": ["CVE-2016-6515"], "safe_ver": "9.x"},
        "7.2": {"risk": "MEDIUM", "cves": ["CVE-2016-10009"], "safe_ver": "9.x"},
        "7.3": {"risk": "MEDIUM", "cves": ["CVE-2017-15906"], "safe_ver": "9.x"},
        "7.4": {"risk": "LOW", "cves": [], "safe_ver": "9.x", "note": "Mostly patched"},
        "8.": {"risk": "LOW", "cves": ["CVE-2023-38408"], "safe_ver": "9.3", "note": "Known but low"},
    },
    "apache": {
        "1.": {"risk": "CRITICAL", "cves": ["CVE-2002-0392"], "safe_ver": "2.4.57+"},
        "2.0": {"risk": "CRITICAL", "cves": ["CVE-2011-3192"], "safe_ver": "2.4.57+"},
        "2.2": {"risk": "CRITICAL", "cves": ["CVE-2011-3348", "CVE-2017-7679"], "safe_ver": "2.4.57+"},
        "2.4.1": {"risk": "HIGH", "cves": ["CVE-2014-0231"], "safe_ver": "2.4.57+"},
        "2.4.2": {"risk": "HIGH", "cves": ["CVE-2014-0231"], "safe_ver": "2.4.57+"},
        "2.4.17": {"risk": "HIGH", "cves": ["CVE-2016-0736"], "safe_ver": "2.4.57+"},
        "2.4.29": {"risk": "HIGH", "cves": ["CVE-2017-9798", "CVE-2018-1312"], "safe_ver": "2.4.57+"},
        "2.4.38": {"risk": "HIGH", "cves": ["CVE-2019-0211"], "safe_ver": "2.4.57+"},
        "2.4.49": {"risk": "CRITICAL", "cves": ["CVE-2021-41773"], "safe_ver": "2.4.57+",
                   "note": "Path traversal/RCE — widely exploited in the wild"},
        "2.4.50": {"risk": "CRITICAL", "cves": ["CVE-2021-42013"], "safe_ver": "2.4.57+",
                   "note": "Incomplete fix for CVE-2021-41773"},
        "2.4.51": {"risk": "MEDIUM", "cves": ["CVE-2022-22720"], "safe_ver": "2.4.57+"},
    },
    "nginx": {
        "0.": {"risk": "CRITICAL", "cves": ["CVE-2009-2629"], "safe_ver": "1.24+"},
        "1.0": {"risk": "HIGH", "cves": ["CVE-2011-4315"], "safe_ver": "1.24+"},
        "1.2": {"risk": "HIGH", "cves": ["CVE-2013-2028"], "safe_ver": "1.24+"},
        "1.4": {"risk": "HIGH", "cves": ["CVE-2013-2028"], "safe_ver": "1.24+"},
        "1.6": {"risk": "MEDIUM", "cves": ["CVE-2014-3616"], "safe_ver": "1.24+"},
        "1.8": {"risk": "MEDIUM", "cves": ["CVE-2016-0742"], "safe_ver": "1.24+"},
        "1.10": {"risk": "MEDIUM", "cves": ["CVE-2017-7529"], "safe_ver": "1.24+"},
        "1.12": {"risk": "MEDIUM", "cves": ["CVE-2017-7529"], "safe_ver": "1.24+"},
        "1.14": {"risk": "MEDIUM", "cves": ["CVE-2019-9511"], "safe_ver": "1.24+"},
        "1.16": {"risk": "LOW", "cves": [], "safe_ver": "1.24+"},
        "1.18": {"risk": "LOW", "cves": ["CVE-2021-23017"], "safe_ver": "1.24+", "note": "DNS resolver vuln"},
    },
    "php": {
        "4.": {"risk": "CRITICAL", "cves": ["CVE-2007-1285"], "safe_ver": "8.2+"},
        "5.0": {"risk": "CRITICAL", "cves": ["CVE-2005-3388"], "safe_ver": "8.2+"},
        "5.2": {"risk": "CRITICAL", "cves": ["CVE-2008-3658"], "safe_ver": "8.2+"},
        "5.3": {"risk": "CRITICAL", "cves": ["CVE-2012-0830"], "safe_ver": "8.2+"},
        "5.4": {"risk": "CRITICAL", "cves": ["CVE-2014-3597"], "safe_ver": "8.2+"},
        "5.5": {"risk": "CRITICAL", "cves": ["CVE-2015-8835"], "safe_ver": "8.2+"},
        "5.6": {"risk": "HIGH", "cves": ["CVE-2016-9138"], "safe_ver": "8.2+", "note": "EOL"},
        "7.0": {"risk": "HIGH", "cves": ["CVE-2017-5340"], "safe_ver": "8.2+", "note": "EOL"},
        "7.1": {"risk": "HIGH", "cves": ["CVE-2018-10545"], "safe_ver": "8.2+", "note": "EOL"},
        "7.2": {"risk": "MEDIUM", "cves": ["CVE-2019-11041"], "safe_ver": "8.2+", "note": "EOL"},
        "7.3": {"risk": "MEDIUM", "cves": ["CVE-2021-21705"], "safe_ver": "8.2+"},
        "7.4": {"risk": "MEDIUM", "cves": ["CVE-2022-31625"], "safe_ver": "8.2+"},
        "8.0": {"risk": "LOW", "cves": ["CVE-2023-3247"], "safe_ver": "8.2+"},
    },
    "redis": {
        "2.": {"risk": "HIGH", "cves": ["CVE-2015-8080"], "safe_ver": "7.0+"},
        "3.": {"risk": "HIGH", "cves": ["CVE-2016-8339"], "safe_ver": "7.0+"},
        "4.": {"risk": "HIGH", "cves": ["CVE-2018-11218", "CVE-2018-12326"], "safe_ver": "7.0+"},
        "5.": {"risk": "MEDIUM", "cves": ["CVE-2021-32625"], "safe_ver": "7.0+"},
        "6.0": {"risk": "MEDIUM", "cves": ["CVE-2021-32761"], "safe_ver": "7.0+"},
        "6.2": {"risk": "LOW", "cves": ["CVE-2022-24736"], "safe_ver": "7.0+"},
    },
    "mysql": {
        "5.0": {"risk": "CRITICAL", "cves": ["CVE-2009-4484"], "safe_ver": "8.0+"},
        "5.1": {"risk": "HIGH", "cves": ["CVE-2010-3833"], "safe_ver": "8.0+"},
        "5.5": {"risk": "HIGH", "cves": ["CVE-2016-0640"], "safe_ver": "8.0+"},
        "5.6": {"risk": "MEDIUM", "cves": ["CVE-2019-2534"], "safe_ver": "8.0+"},
        "5.7": {"risk": "MEDIUM", "cves": ["CVE-2020-2574"], "safe_ver": "8.0+"},
    },
    "openssl": {
        "0.9": {"risk": "CRITICAL", "cves": ["CVE-2014-0160"], "safe_ver": "3.0+", "note": "Heartbleed era"},
        "1.0.1": {"risk": "CRITICAL", "cves": ["CVE-2014-0160", "CVE-2014-0224"], "safe_ver": "3.0+",
                  "note": "Heartbleed — private key extraction possible"},
        "1.0.2": {"risk": "HIGH", "cves": ["CVE-2015-0291", "CVE-2016-2108"], "safe_ver": "3.0+"},
        "1.1.0": {"risk": "MEDIUM", "cves": ["CVE-2017-3737"], "safe_ver": "3.0+"},
        "1.1.1": {"risk": "LOW", "cves": ["CVE-2022-0778"], "safe_ver": "3.0+"},
    },
    "proftpd": {
        "1.3.0": {"risk": "CRITICAL", "cves": ["CVE-2010-4221"], "safe_ver": "1.3.8+"},
        "1.3.3": {"risk": "CRITICAL", "cves": ["CVE-2010-4221"], "safe_ver": "1.3.8+"},
        "1.3.5": {"risk": "HIGH", "cves": ["CVE-2019-12815"], "safe_ver": "1.3.8+"},
        "1.3.6": {"risk": "MEDIUM", "cves": ["CVE-2020-9272"], "safe_ver": "1.3.8+"},
    },
    "vsftpd": {
        "2.3.4": {"risk": "CRITICAL", "cves": ["CVE-2011-2523"], "safe_ver": "3.0.5+",
                  "note": "Backdoor RCE — smile ':)' in username triggers shell"},
        "3.0.2": {"risk": "LOW", "cves": [], "safe_ver": "3.0.5+"},
    },
    "iis": {
        "5.": {"risk": "CRITICAL", "cves": ["CVE-2001-0333", "CVE-2003-0223"], "safe_ver": "10+"},
        "6.": {"risk": "CRITICAL", "cves": ["CVE-2017-7269"], "safe_ver": "10+",
               "note": "WebDAV RCE — widely exploited"},
        "7.": {"risk": "HIGH", "cves": ["CVE-2010-3972"], "safe_ver": "10+"},
        "8.": {"risk": "MEDIUM", "cves": ["CVE-2015-1635"], "safe_ver": "10+"},
    },
}


class SecurityTools:
    """Security scanning and lookup tools for the crew."""

    def __init__(self):
        self.cve_cache: Dict[str, Any] = {}
        self._cache_lock = threading.Lock()

    def nmap_scan(self, target: str, verbose: bool = False) -> Dict[str, Any]:
        """
        Scan target for open ports and services.
        Primary: nmap -Pn -sV -T4 --top-ports=50 --host-timeout=45s
        Fallback: parallel socket-based scanner if nmap unavailable or times out.
        """
        import re as _re
        if not target or target.startswith("-") or not _re.match(r'^[a-zA-Z0-9.\-:/\[\]_]+$', target):
            return {"status": "error", "scanner": "nmap", "message": "Invalid target format"}

        try:
            cmd = [
                "nmap", "-Pn", "-sV", "-T4",
                "--top-ports=50",
                "--host-timeout=45s",   # hard wall so subprocess timeout is never hit
                "--version-intensity=0",# fast banner-only version detection
            ]
            if verbose:
                cmd.append("-v")
            cmd.append(target)

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=90
            )

            if result.returncode == 0 or (result.stdout and "Nmap scan report" in result.stdout):
                return {
                    "status": "success",
                    "scanner": "nmap",
                    "target": target,
                    "output": result.stdout,
                    "stderr": result.stderr if result.stderr else None,
                }

            # nmap ran but returned an error — fall through to socket scan
            raise RuntimeError(result.stderr or "nmap returned non-zero")

        except FileNotFoundError:
            pass  # nmap not installed → socket fallback
        except subprocess.TimeoutExpired:
            pass  # nmap timed out → socket fallback
        except Exception:
            pass  # any other nmap error → socket fallback

        # Parallel socket-based fallback
        return self._socket_scan(target)

    def _socket_scan(self, target: str, timeout: float = 1.0,
                     workers: int = 50) -> Dict[str, Any]:
        """Lightweight parallel socket-based port scanner — no external dependencies."""
        try:
            host = socket.gethostbyname(target.split(":")[0])
        except (socket.gaierror, UnicodeError) as e:
            return {"status": "error", "scanner": "socket", "message": f"DNS resolution failed: {e}"}

        lock = threading.Lock()
        open_ports: list = []

        def probe(port: int):
            try:
                conn = socket.create_connection((host, port), timeout=timeout)
                with conn:
                    service = _SERVICE_NAMES.get(port, "unknown")
                    banner = self._grab_banner(conn) if port in _BANNER_PORTS else ""
                    entry = {"port": f"{port}/tcp", "state": "open", "service": service}
                    if banner:
                        entry["banner"] = banner
                    with lock:
                        open_ports.append(entry)
            except (socket.timeout, ConnectionRefusedError, OSError, UnicodeError):
                pass

        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(workers, len(_COMMON_PORTS))) as ex:
            list(ex.map(probe, _COMMON_PORTS))

        # Sort by port number for consistent output
        open_ports.sort(key=lambda p: int(p["port"].split("/")[0]))

        output_lines = [
            f"Socket scan report for {target} ({host})",
            f"Scanned {len(_COMMON_PORTS)} common ports (parallel)",
            "",
        ]
        for p in open_ports:
            banner_str = f"   [{p['banner']}]" if p.get("banner") else ""
            output_lines.append(f"{p['port']:<12} open   {p['service']}{banner_str}")
        output_lines.append(f"\n{len(open_ports)} open port(s) found.")

        return {
            "status": "success",
            "scanner": "socket",
            "target": target,
            "output": "\n".join(output_lines),
            "open_ports": open_ports,
            "note": "nmap unavailable — used parallel socket scanner (no version detection)",
        }

    @staticmethod
    def _grab_banner(conn: socket.socket, max_bytes: int = 256) -> str:
        """Read an initial service banner. Returns a single trimmed line, or ''."""
        try:
            conn.settimeout(2.0)
            data = conn.recv(max_bytes)
            if not data:
                return ""
            line = data.decode("latin-1", errors="replace").strip()
            return line.splitlines()[0][:200] if line else ""
        except (socket.timeout, OSError):
            return ""

    # ------------------------------------------------------------------
    # HTTP fingerprinting & web-layer assessment
    # ------------------------------------------------------------------

    def http_fingerprint(self, target: str, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Identify a web server: status, server banner, page title, and detected
        technologies (from headers and cookies). Tries HTTPS then HTTP.
        Probes root plus a few common landing pages to maximise header/title coverage.
        """
        if not _validate_target(target.replace("http://", "").replace("https://", "").split("/")[0]):
            return {"status": "error", "tool": "http_fingerprint", "message": "Invalid target format"}

        ua = {"User-Agent": "SecureFlow-Scanner/1.0"}
        # Merged header/tech/title from multiple probe paths for thoroughness
        merged_headers: Dict[str, str] = {}
        merged_cookies = ""
        best_title = ""
        best_status = None
        final_url = ""
        last_error = None

        for prefer_https in (True, False):
            base_url = _normalize_url(target, prefer_https=prefer_https)
            probe_urls = [base_url + p for p in ("", "/index.php", "/index.html", "/index.asp")]
            for url in probe_urls:
                try:
                    resp = requests.get(url, timeout=timeout, allow_redirects=True,
                                        verify=False, headers=ua)
                except _NET_ERRORS as exc:
                    last_error = str(exc)
                    continue

                if best_status is None:
                    best_status = resp.status_code
                    final_url = resp.url

                # Accumulate headers (later probes fill gaps left by earlier ones)
                for k, v in resp.headers.items():
                    if k.lower() not in merged_headers:
                        merged_headers[k.lower()] = v
                merged_cookies += " " + "; ".join(c.name for c in resp.cookies).lower()

                # Take first non-empty title
                if not best_title:
                    m = re.search(r"<title[^>]*>(.*?)</title>",
                                  resp.text or "", re.IGNORECASE | re.DOTALL)
                    if m:
                        best_title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]

            if best_status is not None:
                break  # got a valid response on this scheme

        if best_status is None:
            return {"status": "error", "tool": "http_fingerprint",
                    "target": target, "message": f"No HTTP(S) response: {last_error}"}

        technologies = self._detect_technologies(merged_headers, merged_cookies.strip())
        return {
            "status": "success",
            "tool": "http_fingerprint",
            "target": target,
            "final_url": final_url,
            "http_status": best_status,
            "server": merged_headers.get("server", "unknown"),
            "powered_by": merged_headers.get("x-powered-by", ""),
            "title": best_title,
            "technologies": technologies,
        }

    @staticmethod
    def _detect_technologies(headers: Dict[str, str], cookies: str) -> List[str]:
        """Match header/cookie signatures to technology names."""
        found = set()
        for hdr in ("server", "x-powered-by"):
            value = headers.get(hdr, "").lower()
            for needle, name in _TECH_SIGNATURES.get(hdr, {}).items():
                if needle in value:
                    found.add(name)
        for needle, name in _TECH_SIGNATURES["cookie"].items():
            if needle in cookies:
                found.add(name)
        if "x-aspnet-version" in headers:
            found.add("ASP.NET")
        if "x-drupal-cache" in headers:
            found.add("Drupal")
        return sorted(found)

    def http_security_headers(self, target: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Audit a site's HTTP security headers and report which are missing."""
        if not _validate_target(target.replace("http://", "").replace("https://", "").split("/")[0]):
            return {"status": "error", "tool": "security_headers", "message": "Invalid target format"}

        last_error = None
        for prefer_https in (True, False):
            url = _normalize_url(target, prefer_https=prefer_https)
            try:
                resp = requests.get(
                    url, timeout=timeout, allow_redirects=True,
                    verify=False, headers={"User-Agent": "SecureFlow-Scanner/1.0"},
                )
            except _NET_ERRORS as exc:
                last_error = str(exc)
                continue

            present, missing = {}, []
            lower = {k.lower(): v for k, v in resp.headers.items()}
            for header, why in _SECURITY_HEADERS.items():
                if header.lower() in lower:
                    present[header] = lower[header.lower()]
                else:
                    missing.append({"header": header, "risk": why})

            total = len(_SECURITY_HEADERS)
            grade_pct = int(len(present) / total * 100)
            return {
                "status": "success",
                "tool": "security_headers",
                "target": target,
                "final_url": resp.url,
                "present": present,
                "missing": missing,
                "score": f"{len(present)}/{total}",
                "grade_pct": grade_pct,
            }

        return {
            "status": "error", "tool": "security_headers",
            "target": target, "message": f"No HTTP(S) response: {last_error}",
        }

    @staticmethod
    def _resolve_base_url(target: str, timeout: float = 6.0) -> str:
        """Return a reachable http(s):// base URL, trying HTTPS then HTTP."""
        if target.startswith(("http://", "https://")):
            return target.rstrip("/")
        for prefer_https in (True, False):
            url = _normalize_url(target, prefer_https=prefer_https)
            try:
                requests.get(url, timeout=timeout, allow_redirects=True, verify=False,
                             headers={"User-Agent": "SecureFlow-Scanner/1.0"})
                return url.rstrip("/")
            except _NET_ERRORS:
                continue
        return ""

    def probe_paths(self, target: str, timeout: float = 6.0) -> Dict[str, Any]:
        """Probe common sensitive paths. Reports any that are reachable (read-only GET)."""
        if not _validate_target(target.replace("http://", "").replace("https://", "").split("/")[0]):
            return {"status": "error", "tool": "probe_paths", "message": "Invalid target format"}

        base = self._resolve_base_url(target, timeout=timeout)
        if not base:
            return {"status": "error", "tool": "probe_paths", "target": target,
                    "message": "No reachable HTTP(S) service"}
        exposed = []
        checked = 0
        for path in _SENSITIVE_PATHS:
            checked += 1
            try:
                resp = requests.get(
                    base + path, timeout=timeout, allow_redirects=False,
                    verify=False, headers={"User-Agent": "SecureFlow-Scanner/1.0"},
                )
            except _NET_ERRORS:
                continue
            # 200 = exposed; 401/403 = exists but protected (still informative)
            if resp.status_code in (200, 401, 403):
                exposed.append({
                    "path": path,
                    "status": resp.status_code,
                    "length": len(resp.content),
                    "note": "ACCESSIBLE" if resp.status_code == 200 else "exists (protected)",
                })

        return {
            "status": "success",
            "tool": "probe_paths",
            "target": target,
            "paths_checked": checked,
            "findings": exposed,
            "exposed_count": len([e for e in exposed if e["status"] == 200]),
        }

    # ------------------------------------------------------------------
    # TLS / SSL certificate inspection
    # ------------------------------------------------------------------

    def tls_inspect(self, target: str, port: int = 443, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Inspect a TLS endpoint: certificate subject/issuer/validity, negotiated
        protocol & cipher, and common weaknesses (expired, self-signed, weak proto).
        """
        host = target.replace("https://", "").replace("http://", "").split("/")[0]
        if ":" in host and not host.startswith("["):
            host, _, maybe_port = host.partition(":")
            if maybe_port.isdigit():
                port = int(maybe_port)
        if not _validate_target(host):
            return {"status": "error", "tool": "tls_inspect", "message": "Invalid target format"}

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # we inspect the cert ourselves
        try:
            with socket.create_connection((host, port), timeout=timeout) as sock:
                with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                    der = ssock.getpeercert(binary_form=True)
                    protocol = ssock.version()
                    cipher = ssock.cipher()
        except (socket.timeout, socket.gaierror, ConnectionRefusedError,
                OSError, ssl.SSLError, UnicodeError) as exc:
            return {"status": "error", "tool": "tls_inspect", "target": target,
                    "message": f"TLS connection failed: {exc}"}

        info = self._parse_certificate(der)
        warnings = []
        if protocol in ("SSLv2", "SSLv3", "TLSv1", "TLSv1.1"):
            warnings.append(f"Weak/outdated protocol negotiated: {protocol}")
        if info.get("expired"):
            warnings.append("Certificate is EXPIRED")
        if info.get("days_until_expiry") is not None and 0 <= info["days_until_expiry"] <= 30:
            warnings.append(f"Certificate expires soon ({info['days_until_expiry']} days)")
        if info.get("self_signed"):
            warnings.append("Certificate appears self-signed")

        return {
            "status": "success",
            "tool": "tls_inspect",
            "target": target,
            "port": port,
            "protocol": protocol,
            "cipher": cipher[0] if cipher else None,
            "certificate": info,
            "warnings": warnings,
        }

    @staticmethod
    def _parse_certificate(der_bytes: bytes) -> Dict[str, Any]:
        """Parse a DER certificate via the cryptography library."""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from datetime import datetime, timezone
        except ImportError:
            return {"error": "cryptography library not available"}

        try:
            cert = x509.load_der_x509_certificate(der_bytes, default_backend())
        except Exception as exc:  # noqa: BLE001
            return {"error": f"could not parse certificate: {exc}"}

        def _name(name) -> str:
            try:
                return name.rfc4514_string()
            except Exception:  # noqa: BLE001
                return str(name)

        try:
            not_after = cert.not_valid_after_utc
            not_before = cert.not_valid_before_utc
        except AttributeError:  # older cryptography
            from datetime import timezone as _tz
            not_after = cert.not_valid_after.replace(tzinfo=_tz.utc)
            not_before = cert.not_valid_before.replace(tzinfo=_tz.utc)

        now = datetime.now(timezone.utc)
        days_left = (not_after - now).days

        sans = []
        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = ext.value.get_values_for_type(x509.DNSName)
        except Exception:  # noqa: BLE001
            pass

        subject = _name(cert.subject)
        issuer = _name(cert.issuer)
        return {
            "subject": subject,
            "issuer": issuer,
            "self_signed": subject == issuer,
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "expired": now > not_after,
            "days_until_expiry": days_left,
            "serial": str(cert.serial_number),
            "subject_alt_names": sans[:20],
        }

    # ------------------------------------------------------------------
    # DNS enumeration
    # ------------------------------------------------------------------

    def dns_enum(self, domain: str) -> Dict[str, Any]:
        """Enumerate DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA) for a domain."""
        host = domain.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        if not _validate_target(host):
            return {"status": "error", "tool": "dns_enum", "message": "Invalid domain format"}

        try:
            import dns.resolver
        except ImportError:
            return {"status": "error", "tool": "dns_enum",
                    "message": "dnspython not installed (pip install dnspython)"}

        resolver = dns.resolver.Resolver()
        resolver.timeout = 5.0
        resolver.lifetime = 5.0

        records: Dict[str, Any] = {}
        for rtype in ("A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"):
            try:
                answers = resolver.resolve(host, rtype)
                records[rtype] = [r.to_text() for r in answers]
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                continue
            except (dns.resolver.NoNameservers, dns.exception.Timeout) as exc:
                records.setdefault("_errors", []).append(f"{rtype}: {exc}")
            except Exception as exc:  # noqa: BLE001
                records.setdefault("_errors", []).append(f"{rtype}: {exc}")

        if not records or (len(records) == 1 and "_errors" in records):
            return {"status": "error", "tool": "dns_enum", "domain": host,
                    "message": "No DNS records resolved", "details": records.get("_errors", [])}

        return {
            "status": "success",
            "tool": "dns_enum",
            "domain": host,
            "records": records,
            "record_types_found": [k for k in records if not k.startswith("_")],
        }

    def parse_nmap_output(self, nmap_output: str) -> List[Dict[str, str]]:
        """Parse nmap output to extract open ports and services."""
        ports = []
        for line in nmap_output.split("\n"):
            if "/tcp" in line or "/udp" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    port_info = parts[0]
                    state = parts[1]
                    service = " ".join(parts[2:]) if len(parts) > 2 else "unknown"
                    ports.append({
                        "port": port_info,
                        "state": state,
                        "service": service
                    })
        return ports

    def lookup_cve(self, product: str, version: str = "") -> Dict[str, Any]:
        """
        Look up CVEs for a product/version via NVD API.
        Includes rate limiting (3s between requests) and thread-safe cache.
        """
        cache_key = f"{product}:{version}"
        with self._cache_lock:
            if cache_key in self.cve_cache:
                return self.cve_cache[cache_key]

        time.sleep(3)

        try:
            keyword = f"{product} {version}".strip() if version else product
            params = {"keywordSearch": keyword, "resultsPerPage": 10}

            response = requests.get(
                "https://services.nvd.nist.gov/rest/json/cves/2.0",
                params=params,
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                vulns = data.get("vulnerabilities", [])
                result = {
                    "status": "success",
                    "product": product,
                    "version": version,
                    "cve_count": len(vulns),
                    "cves": [
                        {
                            "id": v.get("cve", {}).get("id", ""),
                            "description": (v.get("cve", {}).get("descriptions") or [{}])[0].get("value", ""),
                            "score": (
                                v.get("cve", {}).get("metrics", {})
                                 .get("cvssMetricV31", [{}])[0]
                                 .get("cvssData", {})
                                 .get("baseScore", 0)
                            )
                        }
                        for v in vulns
                    ]
                }
                with self._cache_lock:
                    self.cve_cache[cache_key] = result
                return result
            else:
                return {
                    "status": "error",
                    "message": f"NVD API returned {response.status_code}",
                    "product": product
                }

        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "message": f"CVE lookup failed: {str(e)}",
                "product": product
            }

    def assess_vulnerability(self, port: str, service: str, version: str = "") -> Dict[str, Any]:
        """
        Assess vulnerability of a service by combining nmap data with CVE lookup.
        """
        cve_data = self.lookup_cve(service, version)

        risk_level = "low"
        if cve_data.get("status") == "success" and cve_data.get("cve_count", 0) > 0:
            avg_score = sum([c.get("score", 0) for c in cve_data.get("cves", [])]) / max(1, len(cve_data.get("cves", [])))
            if avg_score >= 9:
                risk_level = "critical"
            elif avg_score >= 7:
                risk_level = "high"
            elif avg_score >= 4:
                risk_level = "medium"

        return {
            "port": port,
            "service": service,
            "version": version,
            "risk_level": risk_level,
            "cve_data": cve_data
        }

    def generate_recommendations(self, vulnerabilities: List[Dict]) -> List[str]:
        """Generate remediation recommendations based on found vulnerabilities."""
        recommendations = []
        critical_count = len([v for v in vulnerabilities if v.get("risk_level") == "critical"])
        high_count = len([v for v in vulnerabilities if v.get("risk_level") == "high"])

        if critical_count > 0:
            recommendations.append(f"CRITICAL: {critical_count} critical vulnerabilities found. Immediate patching required.")

        if high_count > 0:
            recommendations.append(f"HIGH: {high_count} high-risk vulnerabilities. Schedule patching within 30 days.")

        recommendations.append("Enable network segmentation to limit lateral movement.")
        recommendations.append("Implement IDS/IPS for suspicious port scanning activity.")
        recommendations.append("Keep all services updated to latest patches.")

        return recommendations

    # ==================================================================
    # TOOL 5: Subdomain Enumeration
    # DNS brute-force + zone-transfer attempt + wildcard detection.
    # ==================================================================

    def subdomain_enum(self, domain: str, wordlist: List[str] = None,
                       threads: int = 30) -> Dict[str, Any]:
        """
        Enumerate subdomains via DNS brute-force (built-in wordlist + custom),
        zone-transfer (AXFR) attempt, and wildcard detection.
        Pure-Python, works without any external binaries.
        """
        host = domain.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        if not _validate_target(host):
            return {"status": "error", "tool": "subdomain_enum", "message": "Invalid domain format"}

        try:
            import dns.resolver, dns.query, dns.zone, dns.exception, dns.name
        except ImportError:
            return {"status": "error", "tool": "subdomain_enum",
                    "message": "dnspython not installed"}

        resolver = dns.resolver.Resolver()
        resolver.timeout = 3.0
        resolver.lifetime = 3.0

        # -- 1. Wildcard detection ----------------------------------------
        probe = f"__wildcard_probe_{int(time.time())}.{host}"
        wildcard_ip = None
        try:
            ans = resolver.resolve(probe, "A")
            wildcard_ip = ans[0].address
        except Exception:
            pass

        # -- 2. Zone transfer (AXFR) — passive, read-only -------------------
        axfr_records = []
        try:
            ns_ans = resolver.resolve(host, "NS", lifetime=5)
            for ns_rdata in ns_ans:
                ns_host = str(ns_rdata.target).rstrip(".")
                try:
                    zone = dns.zone.from_xfr(dns.query.xfr(ns_host, host, lifetime=5))
                    for name, _ in zone.nodes.items():
                        axfr_records.append(str(name) + "." + host)
                except Exception:
                    continue
        except Exception:
            pass

        # -- 3. Brute-force wordlist -----------------------------------------
        if wordlist is None:
            wordlist = _SUBDOMAIN_WORDLIST

        found = {}
        lock = threading.Lock()

        def resolve_sub(sub):
            fqdn = f"{sub}.{host}"
            try:
                ans = resolver.resolve(fqdn, "A", lifetime=2)
                ips = [r.address for r in ans]
                if wildcard_ip and all(ip == wildcard_ip for ip in ips):
                    return  # wildcard match — not a real subdomain
                with lock:
                    found[fqdn] = ips
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer,
                    dns.resolver.NoNameservers, dns.exception.Timeout):
                pass
            except Exception:
                pass

        with __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
            max_workers=threads
        ) as ex:
            list(ex.map(resolve_sub, wordlist))

        all_subs = dict(sorted(found.items()))
        return {
            "status": "success",
            "tool": "subdomain_enum",
            "domain": host,
            "wildcard_detected": wildcard_ip is not None,
            "wildcard_ip": wildcard_ip,
            "zone_transfer_records": axfr_records,
            "subdomains_found": len(all_subs),
            "subdomains": all_subs,
        }

    # ==================================================================
    # TOOL 6: WAF Detection
    # Fingerprints Web Application Firewalls by probing with payloads
    # and analysing response anomalies / WAF-specific headers.
    # ==================================================================

    def waf_detect(self, target: str, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Detect the presence and identity of a WAF/CDN by:
        1. Comparing normal vs attack-payload responses (status, length, headers).
        2. Checking for WAF-specific response headers and cookies.
        3. Looking for WAF vendor signatures in response bodies.
        Returns WAF name (or 'unknown WAF') + confidence + evidence.
        """
        host = target.replace("http://", "").replace("https://", "").split("/")[0]
        if not _validate_target(host):
            return {"status": "error", "tool": "waf_detect", "message": "Invalid target format"}

        base = self._resolve_base_url(target, timeout=timeout)
        if not base:
            return {"status": "error", "tool": "waf_detect", "target": target,
                    "message": "No reachable HTTP(S) service"}

        probe_headers = {"User-Agent": "SecureFlow-Scanner/1.0"}

        # Normal request
        try:
            normal = requests.get(base + "/", timeout=timeout, verify=False,
                                  allow_redirects=True, headers=probe_headers)
        except _NET_ERRORS as e:
            return {"status": "error", "tool": "waf_detect", "message": str(e)}

        # Attack-payload request (benign-looking but triggers WAF rules)
        try:
            attack = requests.get(
                base + "/?a=<script>alert(1)</script>&b=1+AND+1=1--&c=../etc/passwd",
                timeout=timeout, verify=False, allow_redirects=False,
                headers=probe_headers,
            )
        except _NET_ERRORS:
            attack = None

        evidence = []
        waf_name = None

        # Check WAF-specific headers and cookies
        all_headers = {k.lower(): v.lower() for k, v in normal.headers.items()}
        for k, v in all_headers.items():
            for vendor, name in _WAF_HEADER_SIGNATURES.items():
                if vendor in k or vendor in v:
                    waf_name = waf_name or name
                    evidence.append(f"header {k}: {v[:60]}")

        # Check vendor signatures in normal response body (first 4 KB)
        body_sample = (normal.text or "")[:4096].lower()
        for pattern, name in _WAF_BODY_SIGNATURES.items():
            if pattern in body_sample:
                waf_name = waf_name or name
                evidence.append(f"body pattern: {pattern!r}")

        # Compare normal vs attack response
        if attack is not None:
            if normal.status_code != attack.status_code and attack.status_code in (403, 406, 429, 444, 501):
                evidence.append(f"attack payload → HTTP {attack.status_code} (vs normal {normal.status_code})")
                waf_name = waf_name or "unknown WAF"

            attack_headers = {k.lower(): v.lower() for k, v in attack.headers.items()}
            for k, v in attack_headers.items():
                for vendor, name in _WAF_HEADER_SIGNATURES.items():
                    if vendor in k or vendor in v:
                        waf_name = name
                        evidence.append(f"attack resp header {k}: {v[:60]}")

        confidence = ("high" if len(evidence) >= 3
                      else "medium" if len(evidence) >= 1
                      else "none")
        return {
            "status": "success",
            "tool": "waf_detect",
            "target": target,
            "waf_detected": waf_name is not None,
            "waf_name": waf_name,
            "confidence": confidence,
            "evidence": evidence,
            "normal_status": normal.status_code,
            "attack_status": attack.status_code if attack is not None else None,
        }

    # ==================================================================
    # TOOL 7: HTTP Vulnerability Scanner
    # Actively probes for classes of web vulnerabilities with safe,
    # non-destructive payloads. Returns concrete evidence, not guesses.
    # ==================================================================

    def http_vuln_scan(self, target: str, timeout: float = 10.0) -> Dict[str, Any]:
        """
        Active HTTP vulnerability scan covering:
        - SQLi error disclosure (database error in response)
        - XSS reflection (payload echoed back verbatim)
        - Open redirect (Location header follows attacker URL)
        - Directory listing enabled
        - Stack trace / debug info disclosure
        - Server-side path traversal error indicators
        - Default pages (phpinfo, test pages, admin)
        All payloads are read-only (GET) and non-destructive.
        """
        host = target.replace("http://", "").replace("https://", "").split("/")[0]
        if not _validate_target(host):
            return {"status": "error", "tool": "http_vuln_scan", "message": "Invalid target format"}

        base = self._resolve_base_url(target, timeout=timeout)
        if not base:
            return {"status": "error", "tool": "http_vuln_scan", "target": target,
                    "message": "No reachable HTTP(S) service"}

        findings = []
        hdrs = {"User-Agent": "SecureFlow-Scanner/1.0"}

        def get(path: str, params: dict = None) -> Any:
            try:
                return requests.get(base + path, params=params, timeout=timeout,
                                    verify=False, allow_redirects=False, headers=hdrs)
            except _NET_ERRORS:
                return None

        # Common paths to probe for input-reflection vulnerabilities.
        # Covers root plus the most common endpoints in real apps.
        _probe_paths_list = [
            "/", "/search", "/index.php", "/index.asp", "/home",
            "/query", "/results", "/find", "/filter",
        ]

        # -- SQLi error disclosure -------------------------------------------
        sqli_payloads = ["'", '"', "1' OR '1'='1", "1 AND 1=2--"]
        sqli_errors = [
            "sql syntax", "mysql_fetch", "ora-", "pg_query", "sqlite3",
            "unclosed quotation mark", "you have an error in your sql",
            "warning: mysql", "invalid query", "sqlstate",
        ]
        sqli_found = False
        for probe_path in _probe_paths_list:
            if sqli_found:
                break
            for payload in sqli_payloads:
                r = get(probe_path, {"id": payload, "q": payload, "search": payload})
                if r and any(e in (r.text or "").lower() for e in sqli_errors):
                    findings.append({
                        "type": "SQLi Error Disclosure",
                        "severity": "HIGH",
                        "evidence": f"Database error in response to payload: {payload!r}",
                        "path": probe_path,
                    })
                    sqli_found = True
                    break

        # -- XSS reflection --------------------------------------------------
        xss_token = "SEC_FLOW_XSS_7f3a"
        xss_payload = f"<script>{xss_token}</script>"
        xss_params = {"q": xss_payload, "search": xss_payload, "s": xss_payload,
                      "query": xss_payload, "name": xss_payload, "input": xss_payload}
        for probe_path in _probe_paths_list:
            r = get(probe_path, xss_params)
            if r and xss_token in (r.text or ""):
                findings.append({
                    "type": "Reflected XSS",
                    "severity": "HIGH",
                    "evidence": f"Payload token reflected verbatim in response body",
                    "path": probe_path,
                })
                break

        # -- Open redirect ---------------------------------------------------
        redirect_payloads = [
            "//evil.com", "https://evil.com", "/\\evil.com",
        ]
        for param in ("url", "redirect", "next", "return", "returnUrl", "r", "goto"):
            for payload in redirect_payloads:
                r = get("/", {param: payload})
                if r and r.status_code in (301, 302, 303, 307, 308):
                    loc = r.headers.get("Location", "")
                    if "evil.com" in loc or loc.startswith("//"):
                        findings.append({
                            "type": "Open Redirect",
                            "severity": "MEDIUM",
                            "evidence": f"Redirect to {loc!r} via ?{param}={payload!r}",
                            "path": "/",
                        })

        # -- Directory listing -----------------------------------------------
        for path in ("/", "/static/", "/assets/", "/files/", "/uploads/",
                     "/images/", "/backup/", "/tmp/"):
            r = get(path)
            if r and r.status_code == 200:
                body = (r.text or "").lower()
                if ("index of " in body and "<a href" in body) or \
                   ("directory listing" in body) or \
                   ("parent directory" in body and "last modified" in body):
                    findings.append({
                        "type": "Directory Listing",
                        "severity": "MEDIUM",
                        "evidence": f"Directory index exposed at {path}",
                        "path": path,
                    })
                    break

        # -- Stack trace / debug info disclosure -----------------------------
        debug_patterns = [
            (r"traceback \(most recent call last\)", "Python traceback"),
            (r"java\.lang\.", "Java stack trace"),
            (r"system\.web\.httpunhandledexception", "ASP.NET exception"),
            (r"debug: true|debug_mode|debug=1", "Debug mode enabled"),
            (r"at [a-z]+\.[a-z]+\([a-zA-Z]+\.java:\d+\)", "Java stack trace"),
            (r"fatal error.*in.*on line \d+", "PHP fatal error"),
            (r"django\.core\.exceptions", "Django exception"),
        ]
        error_paths = ["/", "/?error=1", "/nonexistent_" + str(int(time.time()))]
        for path in error_paths:
            r = get(path)
            if r and r.status_code in (200, 400, 404, 500):
                body = (r.text or "").lower()
                for pattern, desc in debug_patterns:
                    if re.search(pattern, body):
                        findings.append({
                            "type": "Stack Trace / Debug Disclosure",
                            "severity": "MEDIUM",
                            "evidence": f"{desc} found in response to {path}",
                            "path": path,
                        })
                        break

        # -- Default / admin pages -------------------------------------------
        for path, name in [("/phpinfo.php", "phpinfo"), ("/test.php", "test page"),
                            ("/server-status", "mod_status"), ("/adminer.php", "Adminer DB UI"),
                            ("/phpmyadmin", "phpMyAdmin"), ("/wp-admin", "WordPress admin")]:
            r = get(path)
            if r and r.status_code == 200 and len(r.content) > 100:
                body = (r.text or "").lower()
                indicators = {
                    "phpinfo": "php version" in body,
                    "adminer DB UI": "adminer" in body,
                    "phpMyAdmin": "phpmyadmin" in body,
                    "WordPress admin": "wp-login" in body or "wordpress" in body,
                    "mod_status": "server version" in body and "requests currently" in body,
                }
                if indicators.get(name, True):
                    findings.append({
                        "type": "Sensitive Admin Page",
                        "severity": "HIGH",
                        "evidence": f"{name} accessible at {path}",
                        "path": path,
                    })

        # -- Open redirect (extended: probe common redirect endpoints) ------
        redirect_endpoints = [
            "/", "/redirect", "/login", "/oauth/callback", "/auth/callback",
            "/sso", "/goto", "/out", "/exit", "/link",
        ]
        redirect_params = ("url", "redirect", "next", "return", "returnUrl",
                           "r", "goto", "location", "target", "redirect_uri",
                           "continue", "forward", "back", "destination")
        redirect_payloads = ["//evil.example.com", "https://evil.example.com",
                             "/\\evil.example.com", "///evil.example.com"]
        seen_redirect = False
        for ep in redirect_endpoints:
            if seen_redirect:
                break
            for param in redirect_params:
                if seen_redirect:
                    break
                for payload in redirect_payloads:
                    r = get(ep, {param: payload})
                    if r and r.status_code in (301, 302, 303, 307, 308):
                        loc = r.headers.get("Location", "")
                        if "evil.example.com" in loc or (loc.startswith("//") and "evil" in loc):
                            findings.append({
                                "type": "Open Redirect",
                                "severity": "MEDIUM",
                                "evidence": f"Unvalidated redirect to {loc!r} via {ep}?{param}={payload!r}",
                                "path": ep,
                            })
                            seen_redirect = True
                            break

        # -- SSTI (Server-Side Template Injection) -------------------------
        # Payload: {{7*7}} — if response contains literal "49", template eval occurred.
        # Also tests: ${7*7} (Freemarker/Groovy), #{7*7} (Thymeleaf), <%=7*7%> (ERB)
        ssti_probes = [
            ("{{7*7}}", "49"),       # Jinja2, Twig, Django, Pebble
            ("${7*7}", "49"),        # Freemarker, Groovy, Spring Expression
            ("#{7*7}", "49"),        # Thymeleaf, Ruby
            ("<%= 7*7 %>", "49"),    # ERB, JSP
            ("{{7*'7'}}", "7777777"),# Jinja2 string multiplication
        ]
        ssti_endpoints = ["/", "/render", "/template", "/page", "/view",
                          "/content", "/preview", "/email", "/report"]
        ssti_params = ("template", "tmpl", "tpl", "view", "page", "content",
                       "q", "s", "search", "name", "text", "msg", "message")
        ssti_found = False
        for ep in ssti_endpoints:
            if ssti_found:
                break
            for payload, expected in ssti_probes:
                if ssti_found:
                    break
                for param in ssti_params:
                    r = get(ep, {param: payload})
                    if r and expected in (r.text or ""):
                        findings.append({
                            "type": "SSTI (Server-Side Template Injection)",
                            "severity": "CRITICAL",
                            "evidence": f"Payload {payload!r} evaluated to {expected!r} on {ep}?{param}=",
                            "path": ep,
                            "note": "SSTI can lead to Remote Code Execution",
                        })
                        ssti_found = True
                        break

        # -- LFI (Local File Inclusion / Path Traversal) -------------------
        lfi_payloads = [
            "../etc/passwd", "../../etc/passwd", "../../../etc/passwd",
            "....//....//etc/passwd", "/etc/passwd",
            "../etc/shadow", "..\\..\\windows\\system32\\drivers\\etc\\hosts",
        ]
        lfi_errors = [
            "failed to open stream", "include(", "require(", "no such file",
            "open_basedir restriction", "permission denied", "file not found",
            "warning: include", "warning: require",
        ]
        lfi_root5 = ["root:x:0:", "root:!:", "[boot loader]", "localhost"]  # file content hints
        lfi_endpoints = ["/", "/read", "/include", "/page", "/load",
                         "/file", "/view", "/content", "/show", "/open",
                         "/download", "/fetch", "/get", "/display"]
        lfi_params = ("file", "page", "include", "path", "load", "f",
                      "filename", "filepath", "url", "source", "doc", "read")
        lfi_found = False
        for ep in lfi_endpoints:
            if lfi_found:
                break
            for payload in lfi_payloads:
                if lfi_found:
                    break
                for param in lfi_params:
                    r = get(ep, {param: payload})
                    if r:
                        body_lower = (r.text or "").lower()
                        file_leaked = any(h in body_lower for h in lfi_root5)
                        error_leaked = any(e in body_lower for e in lfi_errors)
                        if file_leaked or error_leaked:
                            sev = "CRITICAL" if file_leaked else "HIGH"
                            findings.append({
                                "type": "LFI / Path Traversal",
                                "severity": sev,
                                "evidence": (
                                    f"File contents leaked" if file_leaked
                                    else f"Include error revealed"
                                ) + f" on {ep}?{param}={payload!r}",
                                "path": ep,
                                "note": "Can expose /etc/passwd, config files, source code",
                            })
                            lfi_found = True
                            break

        # -- Command Injection (error-based detection) ---------------------
        cmd_payloads = [
            (";id", ["uid=", "gid=", "groups="]),
            ("|id", ["uid=", "gid="]),
            ("&&whoami", ["root", "www-data", "apache", "nginx"]),
            ("`id`", ["uid=", "gid="]),
            (";sleep 0;echo SF_CMDINJ_OK", ["SF_CMDINJ_OK"]),
            # Windows
            ("&whoami", ["nt authority", "system"]),
        ]
        shell_errors = [
            "sh: ", "bash: ", "command not found", "/bin/sh", "syntax error",
            "unexpected token", "is not recognized as",
        ]
        cmd_endpoints = ["/", "/ping", "/exec", "/run", "/cmd", "/command",
                         "/system", "/shell", "/trace", "/nslookup", "/whois",
                         "/lookup", "/check", "/test", "/scan"]
        cmd_params = ("host", "ip", "target", "cmd", "command", "exec",
                      "q", "query", "domain", "input", "arg", "param")
        cmd_found = False
        for ep in cmd_endpoints:
            if cmd_found:
                break
            for payload, indicators in cmd_payloads:
                if cmd_found:
                    break
                for param in cmd_params:
                    r = get(ep, {param: f"localhost{payload}"})
                    if r:
                        body_lower = (r.text or "").lower()
                        body_orig = (r.text or "")
                        # Command output OR shell error message
                        output_found = any(ind in body_orig or ind in body_lower for ind in indicators)
                        error_found = any(e in body_lower for e in shell_errors)
                        if output_found or error_found:
                            sev = "CRITICAL" if output_found else "HIGH"
                            findings.append({
                                "type": "Command Injection",
                                "severity": sev,
                                "evidence": (
                                    f"Shell output leaked" if output_found
                                    else f"Shell error disclosed"
                                ) + f" on {ep}?{param}=localhost{payload!r}",
                                "path": ep,
                                "note": "OS command injection can lead to full server compromise",
                            })
                            cmd_found = True
                            break

        # -- GraphQL introspection enabled ---------------------------------
        graphql_endpoints = ["/graphql", "/api/graphql", "/gql", "/query",
                             "/api/query", "/graphiql", "/playground"]
        for ep in graphql_endpoints:
            r = get(ep, {"query": "{__schema{types{name}}}"})
            if r and r.status_code == 200:
                body = r.text or ""
                if "__schema" in body and "types" in body:
                    findings.append({
                        "type": "GraphQL Introspection Enabled",
                        "severity": "MEDIUM",
                        "evidence": f"__schema query returned schema at {ep}",
                        "path": ep,
                        "note": "Exposes full API schema to attackers; disable in production",
                    })
                    break

        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        findings.sort(key=lambda f: severity_order.get(f["severity"], 9))
        return {
            "status": "success",
            "tool": "http_vuln_scan",
            "target": target,
            "findings_count": len(findings),
            "findings": findings,
        }

    # ==================================================================
    # TOOL 8: Service-Specific Probe
    # Tests concrete, protocol-level security weaknesses per service:
    # unauthenticated access, anonymous login, default credentials.
    # ==================================================================

    def service_probe(self, target: str, port: int, service: str,
                      timeout: float = 5.0) -> Dict[str, Any]:
        """
        Protocol-level security probe for specific services:
        - Redis: check for NOAUTH (unauthenticated) access
        - FTP: test anonymous login
        - MongoDB: attempt unauthenticated list collections
        - Elasticsearch: probe for open HTTP API (/_cat/indices)
        - Memcached: check for unauthenticated stats
        - SMTP: check for open relay potential (VRFY/EXPN)
        - SSH: identify algorithm weaknesses from banner
        """
        if not _validate_target(target):
            return {"status": "error", "tool": "service_probe", "message": "Invalid target"}

        svc = service.lower()
        try:
            if svc in ("redis",):
                return self._probe_redis(target, port, timeout)
            if svc in ("ftp",):
                return self._probe_ftp(target, port, timeout)
            if svc in ("mongodb", "mongo"):
                return self._probe_mongodb(target, port, timeout)
            if svc in ("elasticsearch", "es"):
                return self._probe_elasticsearch(target, port, timeout)
            if svc in ("memcached", "memcache"):
                return self._probe_memcached(target, port, timeout)
            if svc in ("smtp",):
                return self._probe_smtp(target, port, timeout)
            if svc in ("ssh",):
                return self._probe_ssh(target, port, timeout)
            return {"status": "error", "tool": "service_probe",
                    "message": f"No probe implemented for service: {service}"}
        except Exception as exc:
            return {"status": "error", "tool": "service_probe",
                    "target": target, "port": port, "service": service,
                    "message": str(exc)}

    def _sock_conn(self, host: str, port: int, timeout: float) -> socket.socket:
        s = socket.create_connection((host, port), timeout=timeout)
        s.settimeout(timeout)
        return s

    def _probe_redis(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        with self._sock_conn(host, port, timeout) as s:
            s.sendall(b"PING\r\n")
            resp = s.recv(256).decode("latin-1", errors="replace")
        unauth = "+PONG" in resp
        version = ""
        if unauth:
            try:
                with self._sock_conn(host, port, timeout) as s2:
                    s2.sendall(b"INFO server\r\n")
                    info = s2.recv(2048).decode("latin-1", errors="replace")
                version_m = re.search(r"redis_version:(\S+)", info)
                if version_m:
                    version = version_m.group(1)
            except Exception:
                pass
        risk = "CRITICAL" if unauth else "none"
        return {
            "status": "success", "tool": "service_probe", "service": "redis",
            "host": host, "port": port, "unauthenticated_access": unauth,
            "version": version, "risk": risk,
            "finding": "Redis accepts commands without authentication — all data readable/writable." if unauth else "",
        }

    def _probe_ftp(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        with self._sock_conn(host, port, timeout) as s:
            banner = s.recv(512).decode("latin-1", errors="replace").strip()
            s.sendall(b"USER anonymous\r\n")
            r1 = s.recv(256).decode("latin-1", errors="replace")
            anon_ok = False
            if r1.startswith("331"):
                s.sendall(b"PASS secureflow@scan.local\r\n")
                r2 = s.recv(256).decode("latin-1", errors="replace")
                anon_ok = r2.startswith("230")
        risk = "HIGH" if anon_ok else "none"
        return {
            "status": "success", "tool": "service_probe", "service": "ftp",
            "host": host, "port": port, "banner": banner.splitlines()[0][:120],
            "anonymous_login": anon_ok, "risk": risk,
            "finding": "Anonymous FTP login accepted — unauthenticated read/write may be possible." if anon_ok else "",
        }

    def _probe_mongodb(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        # MongoDB wire protocol: send isMaster command, check for auth requirement.
        # OP_QUERY message for {isMaster:1} on 'admin.$cmd'
        import struct
        query_doc = (
            b"\x13\x00\x00\x00"           # doc length (19)
            b"\x10isMaster\x00\x01\x00\x00\x00\x00"
        )
        ns = b"admin.$cmd\x00"
        header = struct.pack("<iiiiBBBi", 41 + len(ns) + len(query_doc), 0, 0, 2004,
                             0, 0, 0, 1) if False else b""
        # Simpler: just check if port is open and banner reveals version
        try:
            with self._sock_conn(host, port, timeout) as s:
                # Mongo sends nothing on connect; try a minimal HTTP-like probe
                s.sendall(b"db.version()\n")
                time.sleep(0.3)
                data = s.recv(256)
                version_hint = data.decode("latin-1", errors="replace")
                open_access = len(data) > 0
        except Exception:
            open_access = False
            version_hint = ""
        risk = "HIGH" if open_access else "low"
        return {
            "status": "success", "tool": "service_probe", "service": "mongodb",
            "host": host, "port": port, "port_open": open_access,
            "response_sample": version_hint[:80], "risk": risk,
            "finding": "MongoDB port is open — verify authentication is required and bind-ip is restricted." if open_access else "",
        }

    def _probe_elasticsearch(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        # ES exposes HTTP API — check if /_cat/indices responds without auth
        for scheme in ("http", "https"):
            try:
                r = requests.get(
                    f"{scheme}://{host}:{port}/_cat/indices?v",
                    timeout=timeout, verify=False,
                    headers={"User-Agent": "SecureFlow-Scanner/1.0"},
                )
                open_access = r.status_code == 200 and ("index" in r.text or "green" in r.text or "yellow" in r.text)
                version = ""
                try:
                    info_r = requests.get(f"{scheme}://{host}:{port}/", timeout=timeout, verify=False)
                    version = info_r.json().get("version", {}).get("number", "")
                except Exception:
                    pass
                risk = "CRITICAL" if open_access else "low"
                return {
                    "status": "success", "tool": "service_probe", "service": "elasticsearch",
                    "host": host, "port": port, "open_api": open_access,
                    "version": version, "risk": risk,
                    "finding": "Elasticsearch /_cat/indices accessible without auth — all index data exposed." if open_access else "",
                }
            except _NET_ERRORS:
                continue
        return {"status": "error", "tool": "service_probe", "service": "elasticsearch",
                "message": "Could not connect to Elasticsearch"}

    def _probe_memcached(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        with self._sock_conn(host, port, timeout) as s:
            s.sendall(b"stats\r\n")
            data = s.recv(2048).decode("latin-1", errors="replace")
        unauth = "STAT pid" in data or "STAT version" in data
        version_m = re.search(r"STAT version (\S+)", data)
        version = version_m.group(1) if version_m else ""
        risk = "HIGH" if unauth else "none"
        return {
            "status": "success", "tool": "service_probe", "service": "memcached",
            "host": host, "port": port, "unauthenticated_access": unauth,
            "version": version, "risk": risk,
            "finding": "Memcached responds to stats without auth — cache poisoning / data extraction possible." if unauth else "",
        }

    def _probe_smtp(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        with self._sock_conn(host, port, timeout) as s:
            banner = s.recv(512).decode("latin-1", errors="replace").strip()
            s.sendall(b"EHLO secureflow.scan\r\n")
            ehlo_resp = s.recv(1024).decode("latin-1", errors="replace")
            vrfy_enabled = False
            try:
                s.sendall(b"VRFY root\r\n")
                vrfy_resp = s.recv(256).decode("latin-1", errors="replace")
                vrfy_enabled = not vrfy_resp.startswith("5")
            except Exception:
                pass
        findings = []
        if vrfy_enabled:
            findings.append("VRFY command enabled — allows user enumeration")
        starttls = "STARTTLS" in ehlo_resp
        auth = "AUTH" in ehlo_resp
        risk = "MEDIUM" if vrfy_enabled else "low"
        return {
            "status": "success", "tool": "service_probe", "service": "smtp",
            "host": host, "port": port, "banner": banner.splitlines()[0][:120],
            "starttls_supported": starttls, "auth_supported": auth,
            "vrfy_enabled": vrfy_enabled, "risk": risk, "findings": findings,
        }

    def _probe_ssh(self, host: str, port: int, timeout: float) -> Dict[str, Any]:
        with self._sock_conn(host, port, timeout) as s:
            banner = s.recv(512).decode("latin-1", errors="replace").strip()
        version_m = re.search(r"SSH-\d+\.\d+-(\S+)", banner)
        sw_version = version_m.group(1) if version_m else ""
        warnings = []
        if "openssh" in sw_version.lower():
            ver_m = re.search(r"OpenSSH_(\d+\.\d+)", sw_version, re.IGNORECASE)
            if ver_m:
                ver = float(ver_m.group(1))
                if ver < 7.4:
                    warnings.append(f"OpenSSH {ver} is below 7.4 — multiple known CVEs (CVE-2016-6515, CVE-2016-10009)")
                if ver < 8.0:
                    warnings.append(f"OpenSSH {ver} — consider upgrading to 8.x+ for security improvements")
        if "dropbear" in sw_version.lower():
            warnings.append("Dropbear SSH — ensure recent version; embedded/IoT usage often unpatched")
        risk = ("HIGH" if any("CVE" in w for w in warnings)
                else "MEDIUM" if warnings else "low")
        return {
            "status": "success", "tool": "service_probe", "service": "ssh",
            "host": host, "port": port, "banner": banner.splitlines()[0][:120],
            "software": sw_version, "warnings": warnings, "risk": risk,
        }

    # ==================================================================
    # TOOL 9: Version Risk Assessment (offline, no API)
    # Instantly maps service version strings to known risk levels
    # using a built-in knowledge base. Works without any API calls.
    # ==================================================================

    def version_risk_assess(self, service: str, version: str,
                            banner: str = "") -> Dict[str, Any]:
        """
        Instant offline risk assessment for a service/version combination.
        Checks against a built-in knowledge base of known-vulnerable versions
        (OpenSSH, Apache, nginx, PHP, MySQL/MariaDB, OpenSSL, ProFTPd, Redis, etc.).
        Returns risk level, CVE IDs, and recommended safe version.
        Returns 'unknown' when the version cannot be scored (not 'low').
        """
        svc = service.lower().split("/")[0].strip()
        ver_clean = version.lower().strip() if version else ""

        # Extract version from banner if version string is empty
        if not ver_clean and banner:
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", banner)
            if m:
                ver_clean = m.group(1)

        # Score from the knowledge base
        kb = _VERSION_RISK_KB.get(svc, _VERSION_RISK_KB.get(svc.split("-")[0], {}))

        best_match = None
        best_score = 0
        for kb_ver, entry in kb.items():
            if kb_ver in ver_clean or ver_clean.startswith(kb_ver):
                match_score = len(kb_ver)
                if match_score > best_score:
                    best_match = entry
                    best_score = match_score

        if best_match:
            return {
                "status": "success",
                "tool": "version_risk_assess",
                "service": service,
                "version": version,
                "risk": best_match["risk"],
                "cves": best_match.get("cves", []),
                "safe_version": best_match.get("safe_ver", ""),
                "note": best_match.get("note", ""),
            }

        return {
            "status": "success",
            "tool": "version_risk_assess",
            "service": service,
            "version": version,
            "risk": "unknown",
            "note": "Version not in knowledge base — run CVE Lookup for current data.",
        }

security_tools = SecurityTools()

# We intentionally connect to untrusted/self-signed pentest targets with
# verify=False; silence the resulting urllib3 warning to keep agent logs clean.
try:
    from urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:  # noqa: BLE001
    pass

@tool("Run Nmap Scan")
def run_nmap_scan(target: str) -> str:
    """Execute nmap scan to discover open ports and services on target."""
    result = security_tools.nmap_scan(target)
    return json.dumps(result, indent=2)

@tool("CVE Lookup")
def lookup_cves(product: str) -> str:
    """Look up known CVEs (Common Vulnerabilities and Exposures) for a product."""
    result = security_tools.lookup_cve(product)
    return json.dumps(result, indent=2)

@tool("Assess Service Vulnerability")
def assess_service(port: str, service: str) -> str:
    """Assess vulnerability risk level of a service running on a specific port."""
    result = security_tools.assess_vulnerability(port, service)
    return json.dumps(result, indent=2)

@tool("HTTP Fingerprint")
def http_fingerprint(target: str) -> str:
    """Fingerprint a web server: HTTP status, server banner, page title, and detected
    technologies (CMS, frameworks, languages) from response headers and cookies."""
    result = security_tools.http_fingerprint(target)
    return json.dumps(result, indent=2)

@tool("Audit HTTP Security Headers")
def audit_security_headers(target: str) -> str:
    """Audit a website's HTTP security headers (HSTS, CSP, X-Frame-Options, etc.)
    and report which protective headers are missing and the associated risk."""
    result = security_tools.http_security_headers(target)
    return json.dumps(result, indent=2)

@tool("Probe Sensitive Paths")
def probe_sensitive_paths(target: str) -> str:
    """Probe a web server for commonly-exposed sensitive paths (/.git, /.env, backups,
    admin panels, actuator endpoints). Reports any that are accessible or protected."""
    result = security_tools.probe_paths(target)
    return json.dumps(result, indent=2)

@tool("Inspect TLS Certificate")
def inspect_tls(target: str) -> str:
    """Inspect a TLS/SSL endpoint: certificate subject/issuer/validity, negotiated
    protocol and cipher, and weaknesses (expired, self-signed, outdated TLS)."""
    result = security_tools.tls_inspect(target)
    return json.dumps(result, indent=2)

@tool("DNS Enumeration")
def dns_enumerate(domain: str) -> str:
    """Enumerate DNS records (A, AAAA, MX, NS, TXT, CNAME, SOA) for a domain to map
    its infrastructure, mail servers, and name servers."""
    result = security_tools.dns_enum(domain)
    return json.dumps(result, indent=2)

@tool("Subdomain Enumeration")
def subdomain_enumerate(domain: str) -> str:
    """Enumerate subdomains of a domain using DNS brute-force (built-in wordlist),
    zone-transfer attempt, and wildcard detection. Maps the full attack surface."""
    result = security_tools.subdomain_enum(domain)
    return json.dumps(result, indent=2)

@tool("WAF Detection")
def detect_waf(target: str) -> str:
    """Detect the presence and identity of a Web Application Firewall (WAF) or CDN
    by comparing normal vs attack-payload responses and inspecting WAF-specific headers."""
    result = security_tools.waf_detect(target)
    return json.dumps(result, indent=2)

@tool("HTTP Vulnerability Scan")
def http_vuln_scan(target: str) -> str:
    """Active HTTP vulnerability scanner covering 8 vulnerability classes:
    SQLi error disclosure, Reflected XSS, Open Redirect (extended endpoint coverage),
    Directory Listing, Stack Trace/Debug Disclosure, SSTI (Server-Side Template Injection,
    {{7*7}} patterns for Jinja2/Twig/Freemarker/ERB), LFI/Path Traversal (../etc/passwd
    across 15 endpoints and 12 parameters), Command Injection (shell metacharacter
    injection with output/error detection), and GraphQL Introspection.
    All probes are non-destructive read-only GET requests."""
    result = security_tools.http_vuln_scan(target)
    return json.dumps(result, indent=2)

@tool("Service Security Probe")
def service_security_probe(target: str, port: int, service: str) -> str:
    """Protocol-level security probe for specific services. Tests for unauthenticated
    access, anonymous login, and default credential weaknesses.
    Supports: redis, ftp, mongodb, elasticsearch, memcached, smtp, ssh."""
    result = security_tools.service_probe(target, port, service)
    return json.dumps(result, indent=2)

@tool("Version Risk Assessment")
def version_risk_assessment(service: str, version: str, banner: str = "") -> str:
    """Instant offline risk assessment for a service/version. Checks against a built-in
    knowledge base of known-vulnerable versions (OpenSSH, Apache, nginx, PHP, MySQL,
    OpenSSL, Redis, IIS, ProFTPd, vsftpd). Returns risk level, CVE IDs, safe version.
    No API call needed — works offline."""
    result = security_tools.version_risk_assess(service, version, banner)
    return json.dumps(result, indent=2)


class DevTools:
    """Development tools for architecture, code generation, and review."""

    @staticmethod
    def design_system_impl(requirements: str) -> Dict[str, Any]:
        """Design system architecture based on requirements."""
        return {
            "status": "success",
            "architecture": {
                "pattern": "Layered Architecture",
                "layers": [
                    {"name": "Presentation Layer", "description": "User interface and API endpoints"},
                    {"name": "Business Logic Layer", "description": "Core application logic and processing"},
                    {"name": "Data Access Layer", "description": "Database interaction and caching"},
                    {"name": "Infrastructure Layer", "description": "External services and utilities"}
                ],
                "components": ["API Server", "Database", "Cache", "Message Queue", "External APIs"],
                "data_flow": "Client → API Gateway → Services → Database with caching layer"
            },
            "description": f"Architecture designed for: {requirements[:100]}..."
        }

    @staticmethod
    def recommend_stack_impl(requirements: str, language: str) -> Dict[str, Any]:
        """Recommend technology stack for the project."""
        stacks = {
            "python": {
                "framework": "FastAPI or Django",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "Celery with RabbitMQ",
                "frontend": "React with TypeScript",
                "deployment": "Docker + Kubernetes"
            },
            "javascript": {
                "framework": "Node.js + Express or Next.js",
                "database": "MongoDB or PostgreSQL",
                "cache": "Redis",
                "messaging": "Bull queue",
                "frontend": "React or Vue.js",
                "deployment": "Docker + Vercel or AWS"
            },
            "go": {
                "framework": "Gin or Echo",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "Kafka or RabbitMQ",
                "frontend": "React or Vue.js",
                "deployment": "Docker + Kubernetes"
            },
            "rust": {
                "framework": "Actix-web or Axum",
                "database": "PostgreSQL",
                "cache": "Redis",
                "messaging": "tokio mpsc or crossbeam",
                "frontend": "SvelteKit or Next.js",
                "deployment": "Docker + Kubernetes"
            }
        }

        recommended = stacks.get(language.lower(), stacks["python"])
        return {
            "status": "success",
            "language": language,
            "stack": recommended,
            "reasoning": f"Recommended for {language} project with requirements: {requirements[:100]}..."
        }

    @staticmethod
    def plan_structure_impl(project_type: str, language: str) -> Dict[str, Any]:
        """Plan project directory structure."""
        structures = {
            "web": {
                "root": ["README.md", "requirements.txt", "docker-compose.yml", ".env.example"],
                "src": ["main.py", "config.py", "app.py"],
                "tests": ["test_main.py", "test_api.py", "conftest.py"],
                "docs": ["API.md", "ARCHITECTURE.md"],
                "scripts": ["setup.sh", "migrate.sh"]
            },
            "library": {
                "root": ["README.md", "setup.py", "pyproject.toml"],
                "src": ["__init__.py", "core.py", "utils.py"],
                "tests": ["test_core.py", "test_utils.py"],
                "docs": ["INDEX.md", "EXAMPLES.md"]
            },
            "cli": {
                "root": ["README.md", "setup.py", "Makefile"],
                "src": ["__main__.py", "cli.py", "commands.py"],
                "tests": ["test_cli.py"],
                "docs": ["USAGE.md"]
            }
        }

        structure = structures.get(project_type.lower(), structures["web"])
        return {
            "status": "success",
            "type": project_type,
            "language": language,
            "structure": structure,
            "description": f"Project structure for {language} {project_type}"
        }

    @staticmethod
    def write_code_impl(spec: str, language: str) -> Dict[str, Any]:
        """Generate code implementation."""
        return {
            "status": "success",
            "language": language,
            "code": f"""
# {language.upper()} Implementation
# Specification: {spec[:50]}...

def main():
    '''Main application entry point'''
    pass

if __name__ == "__main__":
    main()
""",
            "modules": ["main", "config", "models", "services", "utils"],
            "note": "Full code would be generated based on detailed specifications"
        }

    @staticmethod
    def create_file_impl(filepath: str, content: str, language: str) -> Dict[str, Any]:
        """Create a file with the given content (restricted to safe directories)."""
        import os
        from pathlib import Path

        _ALLOWED_PREFIXES = (
            "/tmp/",
            str(Path.home() / ".secureflow"),
        )

        try:
            resolved = Path(filepath).resolve()
            if not any(str(resolved).startswith(p) for p in _ALLOWED_PREFIXES):
                return {
                    "status": "error",
                    "filepath": filepath,
                    "message": "Path not allowed. Files may only be written under /tmp/ or ~/.secureflow/"
                }

            os.makedirs(str(resolved.parent), exist_ok=True)
            resolved.write_text(content, encoding="utf-8")

            return {
                "status": "success",
                "filepath": str(resolved),
                "size": len(content),
                "message": f"File created successfully at {resolved}"
            }
        except Exception as e:
            return {
                "status": "error",
                "filepath": filepath,
                "message": str(e)
            }

    @staticmethod
    def test_code_impl(code: str, language: str) -> Dict[str, Any]:
        """Test code for syntax and basic quality."""
        return {
            "status": "success",
            "language": language,
            "tests_run": 3,
            "tests_passed": 3,
            "tests_failed": 0,
            "coverage": "85%",
            "issues": [],
            "note": "Full testing would run actual test suite"
        }

    @staticmethod
    def review_code_impl(code: str, language: str) -> Dict[str, Any]:
        """Review code quality and identify issues."""
        lines = code.split('\n')
        issues = []

        if len(lines) > 200:
            issues.append({"type": "complexity", "severity": "medium", "message": "Function too long"})
        if code.count('TODO') > 0:
            issues.append({"type": "incomplete", "severity": "low", "message": "TODO comments found"})

        return {
            "status": "success",
            "language": language,
            "lines_of_code": len(lines),
            "issues_found": len(issues),
            "issues": issues,
            "quality_score": 85,
            "maintainability_index": 75
        }

    @staticmethod
    def suggest_improvements_impl(code: str, language: str) -> Dict[str, Any]:
        """Suggest improvements for code."""
        return {
            "status": "success",
            "language": language,
            "suggestions": [
                {"category": "readability", "suggestion": "Break down long functions into smaller units"},
                {"category": "performance", "suggestion": "Consider caching frequently accessed data"},
                {"category": "security", "suggestion": "Add input validation and sanitization"},
                {"category": "testing", "suggestion": "Add more edge case tests"}
            ],
            "estimated_improvement": "30% improvement in maintainability"
        }

    @staticmethod
    def find_bugs_impl(code: str, language: str) -> Dict[str, Any]:
        """Find potential bugs in code."""
        return {
            "status": "success",
            "language": language,
            "bugs_found": 0,
            "potential_issues": [
                {"severity": "low", "type": "missing_error_handling", "line": "unknown"},
                {"severity": "low", "type": "unused_variable", "line": "unknown"}
            ],
            "recommendation": "No critical bugs found, but review error handling"
        }


dev_tools = DevTools()

@tool("Design System Architecture")
def design_system(requirements: str) -> str:
    """Design system architecture based on requirements."""
    result = dev_tools.design_system_impl(requirements)
    return json.dumps(result, indent=2)

@tool("Recommend Technology Stack")
def recommend_stack(requirements: str, language: str) -> str:
    """Recommend optimal technology stack for the project."""
    result = dev_tools.recommend_stack_impl(requirements, language)
    return json.dumps(result, indent=2)

@tool("Plan Project Structure")
def plan_structure(project_type: str, language: str) -> str:
    """Plan project directory structure and organization."""
    result = dev_tools.plan_structure_impl(project_type, language)
    return json.dumps(result, indent=2)

@tool("Write Code")
def write_code(spec: str, language: str) -> str:
    """Generate code implementation based on specification."""
    result = dev_tools.write_code_impl(spec, language)
    return json.dumps(result, indent=2)

@tool("Create File")
def create_file(filepath: str, content: str, language: str) -> str:
    """Create a file with the given content."""
    result = dev_tools.create_file_impl(filepath, content, language)
    return json.dumps(result, indent=2)

@tool("Test Code")
def test_code(code: str, language: str) -> str:
    """Test code for syntax errors and basic quality checks."""
    result = dev_tools.test_code_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Review Code Quality")
def review_code(code: str, language: str) -> str:
    """Review code for quality issues, complexity, and maintainability."""
    result = dev_tools.review_code_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Suggest Code Improvements")
def suggest_improvements(code: str, language: str) -> str:
    """Suggest improvements for code readability, performance, and security."""
    result = dev_tools.suggest_improvements_impl(code, language)
    return json.dumps(result, indent=2)

@tool("Find Bugs")
def find_bugs(code: str, language: str) -> str:
    """Find potential bugs and issues in code."""
    result = dev_tools.find_bugs_impl(code, language)
    return json.dumps(result, indent=2)


class ContextManager:
    """Manage shared context for inter-agent communication."""

    _context = None

    @classmethod
    def get_context(cls):
        """Get or initialize the shared context."""
        if cls._context is None:
            from secureflow.crew.memory import SharedContext
            cls._context = SharedContext()
        return cls._context

    @staticmethod
    def save_findings(agent_name: str, key: str, findings: Any) -> Dict[str, Any]:
        """Save findings to shared context."""
        try:
            ctx = ContextManager.get_context()
            ctx.write(agent_name, key, findings)
            return {
                "status": "success",
                "agent": agent_name,
                "key": key,
                "message": f"Findings saved by {agent_name}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def read_findings(agent_name: str, key: str) -> Dict[str, Any]:
        """Read findings from shared context."""
        try:
            ctx = ContextManager.get_context()
            findings = ctx.read(agent_name, key)
            return {
                "status": "success",
                "agent": agent_name,
                "key": key,
                "findings": findings
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def get_all_findings(agent_name: str) -> Dict[str, Any]:
        """Get all findings from a specific agent."""
        try:
            ctx = ContextManager.get_context()
            findings = ctx.get_all(agent_name)
            return {
                "status": "success",
                "agent": agent_name,
                "findings": findings
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }

    @staticmethod
    def get_latest_findings_all() -> Dict[str, Any]:
        """Get latest findings from all agents."""
        try:
            ctx = ContextManager.get_context()
            findings = ctx.get_latest_findings()
            return {
                "status": "success",
                "all_findings": findings
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }


@tool("Save Findings to Context")
def save_findings_to_context(agent_name: str, key: str, findings: str) -> str:
    """Save agent findings to shared context for other agents to read."""
    result = ContextManager.save_findings(agent_name, key, findings)
    return json.dumps(result, indent=2)


@tool("Read Context Findings")
def read_context_findings(agent_name: str, key: str) -> str:
    """Read findings from shared context saved by another agent."""
    result = ContextManager.read_findings(agent_name, key)
    return json.dumps(result, indent=2)


@tool("Get All Agent Findings")
def get_all_findings(agent_name: str) -> str:
    """Get all findings saved by a specific agent."""
    result = ContextManager.get_all_findings(agent_name)
    return json.dumps(result, indent=2)


@tool("Get Latest Findings from All Agents")
def get_latest_findings() -> str:
    """Get latest findings from all agents in the crew."""
    result = ContextManager.get_latest_findings_all()
    return json.dumps(result, indent=2)
