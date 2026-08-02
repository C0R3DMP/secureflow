import shutil
import socket
import subprocess
import json
import threading
import time
import requests
from typing import Dict, List, Any
import re
from crewai.tools import tool

from secureflow.analysis import analyse_python, review_metrics, syntax_check
from secureflow.security import InvalidTarget, validate_target

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


# Offline fallback only — used when the live NVD CPE dictionary lookup below
# is unreachable. Verified against NVD's own dictionary directly: several
# previous guesses here were simply wrong (mysql -> "oracle" when NVD uses
# "mysql"; nginx -> "nginx" when NVD uses "igor_sysoev"; vsftpd -> "vsftpd"
# when NVD uses "vsftpd_project"; redis had no entry and a naive first-hit
# keyword search resolves to an unrelated "att" product). Corrected from
# direct verification, not guessed.
_CPE_VENDORS = {
    "openssh": "openbsd", "ssh": "openbsd",
    "apache": "apache", "httpd": "apache", "tomcat": "apache",
    "nginx": "igor_sysoev", "mysql": "mysql", "mariadb": "mariadb",
    "postgresql": "postgresql", "redis": "pivotal_software", "mongodb": "mongodb",
    "vsftpd": "vsftpd_project", "proftpd": "proftpd", "samba": "samba",
    "openssl": "openssl", "bind": "isc", "dovecot": "dovecot",
    "postfix": "postfix", "exim": "exim", "php": "php",
}


# Service-banner names that don't appear verbatim in NVD's CPE titles, so a
# keyword search on them returns nothing at all. Verified live: nmap reports
# Apache's banner as "Apache httpd", but NVD titles it "Apache HTTP Server" —
# the token "httpd" appears nowhere, so keywordSearch=apache httpd -> 0
# results while the aliased query resolves correctly to apache:http_server.
_CPE_QUERY_ALIASES = {
    "apache httpd": "apache http server",
    "httpd": "apache http server",
    "apache2": "apache http server",
    "apache": "apache http server",
}

# A trailing version token crammed onto the product name — "Apache httpd
# 2.4.7". Must start with a digit (optionally 'v') so descriptive trailing
# words like the "Server" in "Apache HTTP Server" are never mistaken for one.
_TRAILING_VERSION_RE = re.compile(r"^v?\d+(?:\.\d+)*[a-z0-9._-]*$", re.IGNORECASE)


def _split_product_version(product: str) -> Any:
    """Split a trailing version off a product string: ("Apache httpd 2.4.7")
    -> ("Apache httpd", "2.4.7"). Returns (product, "") when there is none.

    Live-verified need: the crew's own recon agent, given a tool with no
    version parameter, put the version it had correctly fingerprinted into
    the product name instead. The tool signature is fixed too, but a model
    can always phrase it this way, so the parsing is kept as a safety net.
    """
    text = str(product or "").strip()
    if " " not in text:
        return text, ""
    head, _, tail = text.rpartition(" ")
    if _TRAILING_VERSION_RE.match(tail):
        return head.strip(), tail
    return text, ""


def _usable_version(version: str) -> str:
    """Return the version if it identifies a real release, else "".

    A model asked for a version it does not have will supply a placeholder
    rather than omit the argument — live-verified, the recon agent called
    lookup_cves(product="Apache httpd", version="unknown") when nmap had
    explicitly reported the service as unrecognised. "unknown" is a truthy
    string, so it sailed past the empty-version guard and reopened exactly
    the whole-history keyword search that guard exists to prevent, returning
    1999-era Apache CVEs for a service whose version nobody knew.

    Requiring at least one digit is the check that generalises: every real
    release identifier has one, and no placeholder a model reaches for
    ("unknown", "n/a", "unspecified", "latest", "-") does.
    """
    text = str(version or "").strip()
    return text if any(char.isdigit() for char in text) else ""


def _normalise_cpe_component(value: str) -> str:
    return re.sub(r"[^a-z0-9_.-]", "_", str(value).strip().lower())


def _cpe_for(vendor: str, product: str, version: str) -> str:
    """Build a CPE 2.3 match string for an NVD virtualMatchString query."""
    return (
        f"cpe:2.3:a:{_normalise_cpe_component(vendor)}:"
        f"{_normalise_cpe_component(product)}:{_normalise_cpe_component(version)}"
    )


def _osv_lookup(product: str, version: str, timeout: int = 10) -> List[Dict[str, Any]]:
    """Query OSV.dev for a package version.

    NVD's CPE matching depends on getting vendor:product exactly right, and a
    miss returns silently empty. OSV matches on package coordinates instead and
    has better coverage and freshness for open-source components, so the two are
    used together rather than either alone.
    """
    if not version:
        return []

    try:
        response = requests.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": product}, "version": version},
            timeout=timeout,
        )
        if response.status_code != 200:
            return []
        vulns = response.json().get("vulns", []) or []
    except (requests.exceptions.RequestException, ValueError):
        return []

    findings = []
    for vuln in vulns:
        # Keep only records that carry a real CVE id, and use it so results
        # dedupe against the NVD set.
        #
        # A query with no ecosystem — which is all we can send, since a service
        # banner doesn't name one — matches distro *advisories* far more often
        # than CVEs. Live-verified: nginx 1.18.0 returns 417 OSV records, of
        # which only 22 carry a CVE alias; the other 395 are RHSA/DSA/USN/
        # ALPINE/SUSE packaging advisories, each for one distro's own build.
        # vsftpd 2.3.4 returns 42 records and *none* are CVEs. Recording those
        # as findings inflated a scan's CVE count by an order of magnitude with
        # entries that say nothing about the target's actual software.
        candidates = [vuln.get("id", "")] + list(vuln.get("aliases") or [])
        identifier = next((c for c in candidates if c.startswith("CVE-")), "")
        if not identifier:
            continue
        severity = _osv_severity(vuln)
        findings.append({
            "id": identifier,
            "description": (vuln.get("summary") or vuln.get("details") or "")[:400],
            "score": severity[1],
            "severity": severity[0],
            "cvss_version": "osv",
            "source": "osv",
        })
    return findings


def _osv_severity(vuln: Dict[str, Any]) -> Any:
    """Derive (label, score) from an OSV record's severity block."""
    for entry in vuln.get("severity", []) or []:
        score = entry.get("score", "")
        # OSV commonly carries a CVSS vector string rather than a number.
        if isinstance(score, str) and score.startswith("CVSS:"):
            continue
        try:
            value = float(score)
        except (TypeError, ValueError):
            continue
        return (_label_for_score(value), value)

    severity = (vuln.get("database_specific") or {}).get("severity")
    label = _normalise_severity(severity)
    return (label or "unknown", 0)


def _label_for_score(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


_SEVERITY_LEVELS = ("critical", "high", "medium", "low")


def _normalise_severity(value: Any) -> Any:
    """Map an NVD baseSeverity or internal risk level onto our four levels."""
    text = str(value or "").strip().lower()
    return text if text in _SEVERITY_LEVELS else None


def _parse_cve(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Extract id, description and the best available CVSS score."""
    cve = entry.get("cve", {}) or {}
    descriptions = cve.get("descriptions") or []
    english = next(
        (d.get("value", "") for d in descriptions if d.get("lang") == "en"),
        descriptions[0].get("value", "") if descriptions else "",
    )

    # Prefer CVSS v3.1, then v3.0, then v2 — the old code read only v3.1 and
    # indexed [0] on a possibly-empty list, scoring everything else as 0.
    metrics = cve.get("metrics", {}) or {}
    score, severity, version_used = 0, "UNKNOWN", None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key) or []
        if not entries:
            continue
        data = entries[0].get("cvssData", {}) or {}
        score = data.get("baseScore", 0) or 0
        severity = (
            data.get("baseSeverity")
            or entries[0].get("baseSeverity")
            or "UNKNOWN"
        )
        version_used = key
        break

    return {
        "id": cve.get("id", ""),
        "description": english,
        "score": score,
        "severity": severity,
        "cvss_version": version_used,
    }


class SecurityTools:
    """Security scanning and lookup tools for the crew."""

    # Minimum seconds between outbound NVD API calls (public tier is 5 req/30s).
    NVD_MIN_INTERVAL = 3.0

    def __init__(self):
        self.cve_cache = {}
        self.last_api_call = 0.0
        self._cpe_vendor_cache: Dict[str, str] = {}
        # Structured findings recorded during a scan. These come from real CVSS
        # data returned by NVD — the dashboard summarises these rather than
        # counting severity words in the agents' prose.
        self._findings: List[Dict[str, Any]] = []
        self._findings_lock = threading.Lock()

    def _throttle_nvd(self) -> None:
        """Shared rate limit across every NVD endpoint this class calls —
        the public tier is 5 req/30s regardless of which NVD path is hit."""
        elapsed = time.time() - self.last_api_call
        remaining = self.NVD_MIN_INTERVAL - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self.last_api_call = time.time()

    def _resolve_cpe(self, product: str) -> Any:
        """Resolve a product name to its NVD (vendor, product) CPE components.

        Both halves have to be resolved, not just the vendor: NVD's CPE
        *product* field frequently differs from the name a scanner reports.
        Live-verified against a real crew run — nmap fingerprinted
        "Apache httpd 2.4.7" (the genuine banner on scanme.nmap.org), whose
        real CPE is `apache:http_server`, matching 108 real CVEs. Keeping the
        caller's own string as the product built `apache_httpd:apache_httpd`,
        which matches nothing, so a correct, versioned lookup still found zero.

        The query also has to use the *raw* product string, not the
        underscore-normalised one: keywordSearch is a natural-language text
        search, so "apache_httpd" returns 0 results where "apache http server"
        returns 574. Normalising before querying silently broke every
        multi-word product name; it only ever worked for single-word ones
        (nginx, redis, php) where normalisation is a no-op.

        Resolution is layered, because neither strategy alone is right
        (both verified against NVD directly):
          1. Prefer results whose CPE product field exactly equals the query —
             a plain majority vote picks whichever product happens to have the
             most version rows ("php" resolves to `php:blog_cms` that way).
          2. Otherwise fall back to the majority (vendor, product) pair, which
             is what resolves descriptive names like "Apache HTTP Server".
        """
        key = str(product or "").strip().lower()
        if key in self._cpe_vendor_cache:
            return self._cpe_vendor_cache[key]

        resolved = self._query_nvd_cpe_dictionary(_CPE_QUERY_ALIASES.get(key, key))
        if resolved is None:
            normalised = _normalise_cpe_component(product)
            resolved = (_CPE_VENDORS.get(normalised, normalised), normalised)

        self._cpe_vendor_cache[key] = resolved
        return resolved

    def _query_nvd_cpe_dictionary(self, query: str) -> Any:
        """Return a resolved (vendor, product) pair, or None if the dictionary
        is unreachable or returns nothing usable."""
        self._throttle_nvd()
        try:
            response = requests.get(
                "https://services.nvd.nist.gov/rest/json/cpes/2.0",
                params={"keywordSearch": query, "resultsPerPage": 50},
                timeout=15,
            )
            if response.status_code != 200:
                return None
            data = response.json()
        except (requests.exceptions.RequestException, ValueError):
            return None

        pairs: List[Any] = []
        for item in data.get("products", []):
            cpe_name = (item.get("cpe") or {}).get("cpeName", "")
            parts = cpe_name.split(":")
            # cpe:2.3:a:<vendor>:<product>:... — indexes 3 and 4.
            if len(parts) > 4:
                pairs.append((parts[3], parts[4]))

        if not pairs:
            return None

        target = _normalise_cpe_component(query)
        exact = [pair for pair in pairs if pair[1] == target]
        candidates = exact or pairs

        votes: Dict[Any, int] = {}
        for pair in candidates:
            votes[pair] = votes.get(pair, 0) + 1
        return max(votes.items(), key=lambda kv: kv[1])[0]

    def record_finding(
        self,
        severity: str,
        source: str,
        reference: str = "",
        confidence: str = "likely",
        description: str = "",
    ) -> None:
        """Record one severity-rated finding for the current scan.

        `confidence` is a distinct axis from severity: severity is how bad the
        finding would be if real, confidence is how sure we are it actually
        applies to this target. A passive CPE version match is "likely", a
        looser keyword match is "possible", and `mark_confirmed()` upgrades a
        specific CVE to "confirmed" once an active Nuclei probe observes it —
        the same verified/unverified distinction the project's own research
        roadmap called for extending past a single "unknown" risk level.
        """
        level = _normalise_severity(severity)
        if level is None:
            return
        with self._findings_lock:
            self._findings.append({
                "severity": level,
                "source": source,
                "reference": reference,
                "confidence": confidence,
                "description": description,
            })

    def mark_confirmed(self, cve_id: str) -> None:
        """Upgrade a previously recorded finding to "confirmed" once an active
        probe (verify_with_nuclei) has actually observed it on the target."""
        with self._findings_lock:
            for finding in self._findings:
                if finding["reference"] == cve_id:
                    finding["confidence"] = "confirmed"

    def severity_counts(self) -> Dict[str, int]:
        """Deduplicated counts by severity, keyed on the finding reference."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        seen = set()
        with self._findings_lock:
            for finding in self._findings:
                key = finding["reference"] or f"{finding['source']}:{finding['severity']}"
                if key in seen:
                    continue
                seen.add(key)
                counts[finding["severity"]] += 1
        return counts

    def get_findings(self) -> List[Dict[str, Any]]:
        """Deduplicated structured findings for the current scan, newest first
        duplicate discarded — the same dedup key as severity_counts()."""
        seen = set()
        out: List[Dict[str, Any]] = []
        with self._findings_lock:
            for finding in self._findings:
                key = finding["reference"] or f"{finding['source']}:{finding['severity']}"
                if key in seen:
                    continue
                seen.add(key)
                out.append(dict(finding))
        return out

    def clear_findings(self) -> None:
        with self._findings_lock:
            self._findings.clear()

    # nmap must wait out a connection timeout on every filtered (non-responding)
    # port before it can conclude "filtered" rather than "open"/"closed". Live-
    # verified against scanme.nmap.org — a real, benign, well-known target —
    # `-sV --top-ports=50` took 107s because 48 of those 50 ports were filtered.
    # The previous 60s timeout silently discarded every real nmap run against
    # any target with a real firewall in front of it, falling back to the
    # socket scanner with no signal that a downgrade had even happened.
    NMAP_TIMEOUT_SECONDS = 180

    def nmap_scan(self, target: str, verbose: bool = False) -> Dict[str, Any]:
        """
        Scan target for open ports and services.
        Primary: nmap -Pn -sV --top-ports=50
        Fallback: socket-based scanner if nmap is unavailable, times out, or
        otherwise fails. The fallback result always names the reason so a
        report can distinguish "no nmap installed" from "nmap timed out" from
        a genuine scan — the two failure paths were previously indistinguishable.

        The target is validated first: an unvalidated value beginning with '-'
        is parsed by nmap as an option, not a host, which turns this into an
        argument-injection sink (e.g. '--script=/tmp/evil.nse').
        """
        try:
            target = validate_target(target)
        except InvalidTarget as exc:
            return {"status": "error", "scanner": "none", "target": target, "message": str(exc)}

        fallback_reason = "nmap unavailable"
        try:
            cmd = ["nmap", "-Pn", "-sV", "--top-ports=50"]
            if verbose:
                cmd.append("-v")
            # '--' terminates option parsing so the target can never be read
            # as a flag, even if validation is ever loosened.
            cmd.extend(["--", target])

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.NMAP_TIMEOUT_SECONDS
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
            fallback_reason = f"nmap returned an error: {result.stderr or 'non-zero exit'}"
            raise RuntimeError(fallback_reason)

        except FileNotFoundError:
            fallback_reason = "nmap is not installed"
        except subprocess.TimeoutExpired:
            fallback_reason = (
                f"nmap did not finish within {self.NMAP_TIMEOUT_SECONDS}s "
                "(a real scan of a filtered target can legitimately take this long)"
            )
        except RuntimeError:
            pass  # fallback_reason already set above
        except Exception as exc:
            fallback_reason = f"nmap failed unexpectedly: {exc}"

        # Socket-based fallback — always honest about *why* it was used.
        return self._socket_scan(target, fallback_reason=fallback_reason)

    def _socket_scan(self, target: str, timeout: float = 1.0, fallback_reason: str = "nmap unavailable") -> Dict[str, Any]:
        """Lightweight socket-based port scanner — no external dependencies."""
        open_ports = []
        try:
            target = validate_target(target)
        except InvalidTarget as exc:
            return {"status": "error", "scanner": "socket", "message": str(exc)}

        try:
            host = socket.gethostbyname(target)
        except socket.gaierror as e:
            return {"status": "error", "scanner": "socket", "message": f"DNS resolution failed: {e}"}

        for port in _COMMON_PORTS:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    service = _SERVICE_NAMES.get(port, "unknown")
                    open_ports.append({"port": f"{port}/tcp", "state": "open", "service": service})
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass

        output_lines = [
            f"Socket scan report for {target} ({host})",
            f"Scanned {len(_COMMON_PORTS)} common ports",
            "",
        ]
        for p in open_ports:
            output_lines.append(f"{p['port']:<12} open   {p['service']}")
        output_lines.append(f"\n{len(open_ports)} open port(s) found.")

        return {
            "status": "success",
            "scanner": "socket",
            "target": target,
            "output": "\n".join(output_lines),
            "open_ports": open_ports,
            "note": f"{fallback_reason} — used socket scanner (no version detection)",
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
        Rate limited to one request per NVD_MIN_INTERVAL seconds.
        """
        # NVD's keywordSearch has no version awareness at all — without a
        # version, "success" only ever means "the product name appeared
        # somewhere in NVD's text for *some* CVE, from *some* year". This was
        # first caught for bare protocol labels ("http", "ssh" — what the
        # socket-scan fallback returns with no nmap installed): the reporter
        # once cited 1999-2001-era CVEs for a defunct antivirus proxy as
        # CRITICAL findings for a target almost certainly not running it.
        # Live re-verified this week with a real crew run (OpenRouter +
        # scanme.nmap.org): the recon agent, unprompted, guessed the product
        # name "Apache HTTP Server" for a service nmap itself could only
        # fingerprint as "ssl/http" — not a generic label our old check would
        # catch — and cve_lookup("Apache HTTP Server", "") returned 10 of 471
        # totally real, totally unrelated CVEs spanning Apache's entire
        # history. An LLM inventing a plausible-sounding product name defeats
        # any check keyed on specific known-generic strings; the only thing
        # that actually generalises is refusing *any* unversioned lookup,
        # invented product name or not.
        #
        # A placeholder like "unknown" is not a version — see _usable_version.
        version = _usable_version(version)

        # Before refusing, recover a version the caller crammed onto the
        # product name ("Apache httpd 2.4.7") — live-verified real model
        # behaviour, and refusing that would throw away a version we actually
        # have.
        if not version:
            product, version = _split_product_version(product)

        if not version:
            return {
                "status": "insufficient_data",
                "product": product,
                "version": version,
                "cve_count": 0,
                "cves": [],
                "message": (
                    f"No usable version was provided for '{product}' — a keyword-only "
                    "search with no version matches CVEs across that product's entire "
                    "history, unrelated to what's actually running on this target. A "
                    "placeholder such as 'unknown' or 'n/a' does not count as a version "
                    "and will not unlock this lookup. Do NOT retry with a guessed "
                    "version: if the scan did not reveal one, report the version as "
                    "unknown and move on."
                ),
            }

        cache_key = f"{product}:{version}"
        if cache_key in self.cve_cache:
            return self.cve_cache[cache_key]

        # NVD's keywordSearch requires *every* token to appear in the CVE text.
        # "openssh 8.0" therefore matched nothing, so any versioned lookup
        # silently returned zero CVEs and every service was rated "low".
        # Query by CPE first (a version is always present past the guard
        # above), falling back to a keyword search on the product alone if
        # the CPE match misses. Both CPE components are resolved dynamically
        # against NVD's own CPE dictionary (throttled + cached) rather than
        # guessed — the product half matters as much as the vendor half, e.g.
        # "Apache httpd" -> apache:http_server.
        cpe_vendor, cpe_product = self._resolve_cpe(product)
        attempts = [
            ("cpe", {"virtualMatchString": _cpe_for(cpe_vendor, cpe_product, version)}),
            ("keyword", {"keywordSearch": product}),
        ]

        last_error = None
        for strategy, extra in attempts:
            params = {"resultsPerPage": 10, **extra}
            # Throttle immediately before each real call — this loop can make
            # two (cpe then keyword), and _resolve_cpe above may have
            # made a third; NVD's public rate limit applies across all of them.
            self._throttle_nvd()
            try:
                response = requests.get(
                    "https://services.nvd.nist.gov/rest/json/cves/2.0",
                    params=params,
                    timeout=15,
                )
            except requests.exceptions.RequestException as e:
                last_error = f"CVE lookup failed: {e}"
                continue

            if response.status_code != 200:
                last_error = f"NVD API returned {response.status_code}"
                continue

            data = response.json()
            vulns = data.get("vulnerabilities", [])
            if not vulns and strategy != attempts[-1][0]:
                continue  # try the next strategy before giving up

            cves = [_parse_cve(v) for v in vulns]
            for cve in cves:
                cve.setdefault("source", "nvd")

            # Complement NVD with OSV. A CPE miss returns silently empty, so a
            # single source makes "no findings" indistinguishable from "no match".
            merged = {cve["id"]: cve for cve in cves if cve.get("id")}
            osv_added = 0
            for finding in _osv_lookup(product, version):
                key = finding.get("id")
                if key and key not in merged:
                    merged[key] = finding
                    osv_added += 1

            combined = list(merged.values())

            # Each finding carries a real severity — record it so the dashboard
            # can summarise measured results. Confidence tracks the match
            # strategy: an exact CPE version match is "likely", the looser
            # keyword fallback (no exact CPE hit, or no version to match on)
            # is only "possible" — collapsing the two into one confidence
            # would overstate how sure a keyword-only hit actually is.
            match_confidence = "likely" if strategy == "cpe" else "possible"
            for finding in combined:
                self.record_finding(
                    severity=finding.get("severity", ""),
                    source=f"{product} {version}".strip(),
                    reference=finding.get("id", ""),
                    confidence=match_confidence,
                    description=finding.get("description", "")[:300],
                )

            result = {
                "status": "success",
                "product": product,
                "version": version,
                "match_strategy": strategy,
                "sources": ["nvd"] + (["osv"] if osv_added else []),
                "cve_count": len(combined),
                "total_available": data.get("totalResults", len(vulns)),
                "cves": combined,
            }
            self.cve_cache[cache_key] = result
            return result

        return {
            "status": "error",
            "message": last_error or "CVE lookup failed",
            "product": product,
            "version": version,
        }

    def assess_vulnerability(self, port: str, service: str, version: str = "") -> Dict[str, Any]:
        """
        Assess vulnerability of a service by combining nmap data with CVE lookup.
        """
        cve_data = self.lookup_cve(service, version)
        status = cve_data.get("status")

        # "low" means a specific product/version was actually checked and had
        # no matching CVEs — that's a real, informative result. It must not
        # also be the default for "we didn't have enough information to check"
        # (insufficient_data) or "the lookup itself failed" (error): those are
        # genuinely unknown, not confirmed-safe, and conflating them previously
        # let a missing nmap scan quietly read as a clean bill of health.
        if status == "success":
            risk_level = "low"
            cve_count = cve_data.get("cve_count", 0)
            if cve_count > 0:
                avg_score = sum([c.get("score", 0) for c in cve_data.get("cves", [])]) / max(1, len(cve_data.get("cves", [])))
                if avg_score >= 9:
                    risk_level = "critical"
                elif avg_score >= 7:
                    risk_level = "high"
                elif avg_score >= 4:
                    risk_level = "medium"
                # A real CPE version match is a solid basis for a CVE finding;
                # the keyword fallback is a much looser text search and
                # shouldn't be reported with the same confidence.
                confidence = "likely" if cve_data.get("match_strategy") == "cpe" else "possible"
            else:
                # A real, specific check ran and found nothing — that's a
                # confident "clean", not the same as never having checked.
                confidence = "high"
        else:
            risk_level = "unknown"
            confidence = "insufficient_data" if status == "insufficient_data" else "unknown"

        return {
            "port": port,
            "service": service,
            "version": version,
            "risk_level": risk_level,
            "confidence": confidence,
            "cve_data": cve_data
        }

    def generate_recommendations(self, vulnerabilities: List[Dict]) -> List[str]:
        """Generate remediation recommendations based on found vulnerabilities."""
        recommendations = []
        critical_count = len([v for v in vulnerabilities if v.get("risk_level") == "critical"])
        high_count = len([v for v in vulnerabilities if v.get("risk_level") == "high"])
        unknown_count = len([v for v in vulnerabilities if v.get("risk_level") == "unknown"])

        if critical_count > 0:
            recommendations.append(f"CRITICAL: {critical_count} critical vulnerabilities found. Immediate patching required.")

        if high_count > 0:
            recommendations.append(f"HIGH: {high_count} high-risk vulnerabilities. Schedule patching within 30 days.")

        if unknown_count > 0:
            recommendations.append(
                f"UNKNOWN: {unknown_count} service(s) could not be matched to a specific "
                "product/version (no nmap available) — install nmap and re-scan for a "
                "confident vulnerability assessment rather than treating these as clean."
            )

        recommendations.append("Enable network segmentation to limit lateral movement.")
        recommendations.append("Implement IDS/IPS for suspicious port scanning activity.")
        recommendations.append("Keep all services updated to latest patches.")

        return recommendations

    def verify_with_nuclei(self, target: str, cve_id: str, timeout: int = 45) -> Dict[str, Any]:
        """
        Actively verify one specific CVE against a target using a matching
        Nuclei template, if one exists.

        This is a real, active probe against the target — not a passive
        lookup. It sends live requests and inspects the actual response,
        which is what separates "this version string matches a known-CVE
        entry" from "this specific behaviour was observed". Only call this
        against a target you are explicitly authorised to test, and only
        after lookup_cve()/assess_vulnerability() has already identified a
        specific CVE worth confirming — this doesn't replace that step.

        Verified live: even an "info"-severity, "safe" detection template
        (WAF detection) sends a script-tag probe as part of its fingerprint,
        so this excludes fuzzing/DoS/intrusive-tagged templates and runs
        at a deliberately low rate limit — but it is still an active probe,
        not a passive one, and should be used judiciously rather than on
        every finding.

        Returns status:
          - "confirmed"     — the template matched: real, observed evidence,
                               not just a version-string correlation.
          - "not_installed" — nuclei isn't available; the passive CVE match
                               stands unconfirmed, not disproven.
          - "no_template"   — no Nuclei template exists for this CVE. Common —
                               most CVEs never get one. Not a signal either way.
          - "ran_no_match"  — the probe executed and found nothing. This is
                               NOT proof the target is safe: auth, a
                               non-default config, or WAF interference can all
                               hide a real vulnerability from a single probe.
          - "error"         — the check itself failed to run.
        """
        try:
            validated = validate_target(target)
        except InvalidTarget as exc:
            return {"status": "error", "message": str(exc)}

        if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve_id or "", re.IGNORECASE):
            return {
                "status": "error",
                "message": f"{cve_id!r} doesn't look like a CVE id (expected e.g. CVE-2021-41773)",
            }

        if not shutil.which("nuclei"):
            return {
                "status": "not_installed",
                "message": "nuclei is not installed; this finding remains unconfirmed by active probing.",
            }

        cmd = [
            "nuclei",
            "-target", validated,
            "-id", cve_id,
            "-jsonl",
            "-silent",
            "-rate-limit", "10",
            # Even "safe" detection templates can send moderately invasive
            # probes (verified live) — exclude categories that go further
            # than confirming a specific CVE's signature.
            "-etags", "fuzz,dos,intrusive",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": f"nuclei did not finish within {timeout}s"}
        except FileNotFoundError:
            return {"status": "not_installed", "message": "nuclei is not installed"}
        except Exception as exc:
            return {"status": "error", "message": f"nuclei failed to run: {exc}"}

        if result.returncode != 0:
            stderr = (result.stderr or "").lower()
            if "no templates" in stderr:
                return {
                    "status": "no_template",
                    "cve_id": cve_id,
                    "message": f"No Nuclei template exists for {cve_id} — most CVEs never get one.",
                }
            return {"status": "error", "message": (result.stderr or "nuclei exited with an error").strip()}

        findings = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                findings.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if findings:
            # Upgrade the passive finding this CVE came from (if any) to
            # "confirmed" — real observed behaviour outranks a version match.
            self.mark_confirmed(cve_id)
            return {
                "status": "confirmed",
                "cve_id": cve_id,
                "template_id": findings[0].get("template-id"),
                "matched_at": findings[0].get("matched-at"),
                "message": f"Active probe confirmed {cve_id} — observed behaviour, not just a version match.",
            }

        return {
            "status": "ran_no_match",
            "cve_id": cve_id,
            "message": (
                f"The active probe for {cve_id} ran and found no match. This does not "
                "prove the target is safe — the probe may not cover this target's exact "
                "configuration, or the service may require authentication to reach."
            ),
        }

security_tools = SecurityTools()

@tool("Run Nmap Scan")
def run_nmap_scan(target: str) -> str:
    """Execute nmap scan to discover open ports and services on target."""
    result = security_tools.nmap_scan(target)
    return json.dumps(result, indent=2)

@tool("CVE Lookup")
def lookup_cves(product: str, version: str = "") -> str:
    """Look up known CVEs (Common Vulnerabilities and Exposures) for a product.

    ALWAYS pass the exact version string the scan reported, as a separate
    `version` argument — e.g. product="Apache httpd", version="2.4.7".
    Without a version this returns status "insufficient_data" and no CVEs,
    because a version-less search matches that product's entire CVE history
    rather than what is actually running on this target.

    If the scan did not reveal a version, do NOT call this tool at all, and
    do NOT pass a placeholder like "unknown", "n/a" or a guessed number —
    placeholders are rejected the same as no version. Simply report that the
    version could not be determined.
    """
    result = security_tools.lookup_cve(product, version)
    return json.dumps(result, indent=2)

@tool("Assess Service Vulnerability")
def assess_service(port: str, service: str, version: str = "") -> str:
    """Assess vulnerability risk level of a service running on a specific port.

    ALWAYS pass the exact version string the scan reported, as a separate
    `version` argument — e.g. service="Apache httpd", version="2.4.7".
    Without one the assessment can only come back "unknown", since no
    version-specific CVE correlation is possible.
    """
    result = security_tools.assess_vulnerability(port, service, version)
    return json.dumps(result, indent=2)

@tool("Actively Verify CVE")
def verify_cve_actively(target: str, cve_id: str) -> str:
    """
    Send a real, active probe to confirm one specific CVE against the target,
    using a matching Nuclei template if one exists. This goes further than a
    version-string match: it observes real behaviour on the live target.

    Use this judiciously, not on every finding — it makes an additional live
    request against the target, only for CVEs you have already identified via
    CVE lookup that are worth confirming (e.g. the highest-severity ones you
    intend to lead the report with). It is not a substitute for that lookup.

    A "ran_no_match" result does NOT mean the target is safe from this CVE —
    it means this specific probe didn't trigger. Never report the absence of
    a match as a clean bill of health.
    """
    result = security_tools.verify_with_nuclei(target, cve_id)
    return json.dumps(result, indent=2)


@tool("Get Measured Findings")
def get_measured_findings() -> str:
    """The authoritative, machine-recorded list of every CVE this scan actually
    matched, with its severity and confidence.

    These are recorded directly from NVD/OSV responses during CVE lookups —
    they are not written or summarised by any agent. This is the ONLY valid
    source of CVEs for a report.

    Any CVE not in this list did not come from this scan. Do not add CVEs from
    your own knowledge of what a service "typically" suffers from, however
    plausible: a version that was never fingerprinted cannot be known to be
    vulnerable. If this list is empty, the correct report says no CVEs could
    be confirmed for this target and explains why — it does not fall back to
    generic, well-known vulnerabilities.
    """
    findings = security_tools.get_findings()
    return json.dumps(
        {
            "count": len(findings),
            "findings": findings,
            "note": (
                "Authoritative machine-recorded findings. A CVE absent from this "
                "list was not matched by this scan and must not appear in the report."
            ),
        },
        indent=2,
    )


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
    def create_file_impl(filepath: str, content: str, language: str) -> Dict[str, Any]:
        """Create a file with the given content."""
        import os
        try:
            # Create parent directories if needed
            os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

            # Write content to file
            with open(filepath, 'w') as f:
                f.write(content)

            return {
                "status": "success",
                "filepath": filepath,
                "size": len(content),
                "message": f"File created successfully at {filepath}"
            }
        except Exception as e:
            return {
                "status": "error",
                "filepath": filepath,
                "message": str(e)
            }

    @staticmethod
    def check_syntax_impl(code: str, language: str) -> Dict[str, Any]:
        """Parse the source and report whether it is syntactically valid.

        This deliberately does NOT claim that any test suite ran. The previous
        `test_code` returned 'tests_run: 3, tests_passed: 3, coverage: 85%'
        without executing anything, and the agent reported those numbers as fact.
        """
        result = syntax_check(code, language)
        if not result.get("checked"):
            return {
                "status": "unsupported",
                "language": language,
                "tests_executed": 0,
                "message": result.get("reason", "no parser available for this language"),
            }
        if result.get("valid"):
            return {
                "status": "success",
                "language": language,
                "syntax_valid": True,
                "tests_executed": 0,
                "message": "Source parses cleanly. No test suite was executed by this tool.",
            }
        err = result["error"]
        return {
            "status": "error",
            "language": language,
            "syntax_valid": False,
            "tests_executed": 0,
            "error": err,
            "message": f"Syntax error on line {err['line']}: {err['message']}",
        }

    @staticmethod
    def review_code_impl(code: str, language: str) -> Dict[str, Any]:
        """Review code quality using measured metrics and AST findings."""
        metrics = review_metrics(code, language)
        analysis = analyse_python(code, language)
        findings = analysis.get("findings", [])

        if not analysis.get("analysed") and analysis.get("status") == "unsupported":
            return {
                "status": "unsupported",
                "language": language,
                "metrics": metrics,
                "message": analysis["message"],
            }

        # Score derived from what was actually measured, not a constant.
        weights = {"critical": 25, "high": 15, "medium": 7, "low": 2}
        penalty = sum(weights.get(f["severity"], 2) for f in findings)

        longest = (metrics.get("longest_function") or {}).get("lines", 0)
        if longest > 100:
            penalty += 10
        elif longest > 50:
            penalty += 5
        if metrics.get("max_nesting_depth", 0) > 4:
            penalty += 5
        if metrics.get("todo_markers", 0):
            penalty += min(5, metrics["todo_markers"])

        functions = metrics.get("functions", 0)
        if functions:
            undocumented = functions - metrics.get("documented_functions", 0)
            penalty += min(10, undocumented * 2)

        return {
            "status": analysis.get("status", "success"),
            "language": language,
            "metrics": metrics,
            "issues_found": len(findings),
            "issues": findings,
            "quality_score": max(0, 100 - penalty),
            "score_basis": "100 minus weighted penalties for measured findings, size and nesting",
        }

    @staticmethod
    def suggest_improvements_impl(code: str, language: str) -> Dict[str, Any]:
        """Suggest improvements grounded in what the analysis actually found."""
        metrics = review_metrics(code, language)
        analysis = analyse_python(code, language)

        if analysis.get("status") == "unsupported":
            return {
                "status": "unsupported",
                "language": language,
                "suggestions": [],
                "message": analysis["message"],
            }

        suggestions: List[Dict[str, str]] = []
        seen = set()
        remedies = {
            "code_injection": ("security", "Replace eval()/exec() with an explicit parser or a dispatch table"),
            "command_injection": ("security", "Call subprocess with an argument list and shell=False"),
            "sql_injection": ("security", "Use bound query parameters instead of string interpolation"),
            "hardcoded_secret": ("security", "Move credentials to environment variables or a secret store"),
            "unsafe_deserialization": ("security", "Use a safe loader (yaml.safe_load / json) for untrusted input"),
            "broad_except": ("robustness", "Catch specific exception types rather than a bare except"),
            "silent_failure": ("robustness", "Log or re-raise caught exceptions instead of discarding them"),
            "mutable_default_arg": ("correctness", "Use None as the default and build the container inside the function"),
            "identity_comparison": ("readability", "Use 'is None' / 'is not None' for None comparisons"),
            "syntax_error": ("correctness", "Fix the parse error before any further review"),
        }
        for finding in analysis.get("findings", []):
            kind = finding["type"]
            if kind in seen:
                continue
            seen.add(kind)
            category, text = remedies.get(kind, ("quality", f"Address the reported {kind}"))
            suggestions.append({
                "category": category,
                "suggestion": text,
                "first_seen_line": finding["line"],
                "occurrences": sum(1 for f in analysis["findings"] if f["type"] == kind),
            })

        longest = metrics.get("longest_function")
        if longest and longest["lines"] > 50:
            suggestions.append({
                "category": "readability",
                "suggestion": f"Split {longest['name']}() — it spans {longest['lines']} lines",
                "first_seen_line": longest["line"],
                "occurrences": 1,
            })

        functions = metrics.get("functions", 0)
        undocumented = functions - metrics.get("documented_functions", 0)
        if undocumented > 0:
            suggestions.append({
                "category": "documentation",
                "suggestion": f"Add docstrings to {undocumented} of {functions} functions",
                "first_seen_line": 0,
                "occurrences": undocumented,
            })

        return {
            "status": "success",
            "language": language,
            "suggestions": suggestions,
            "message": "No issues detected by static analysis" if not suggestions else "",
        }

    @staticmethod
    def find_bugs_impl(code: str, language: str) -> Dict[str, Any]:
        """Find real defects by inspecting the parsed syntax tree."""
        analysis = analyse_python(code, language)
        findings = analysis.get("findings", [])
        severity = analysis.get("severity_counts", {})

        return {
            "status": analysis["status"],
            "language": language,
            "analysed": analysis.get("analysed", False),
            "bugs_found": len(findings),
            "severity_counts": severity,
            "issues": findings,
            "message": analysis.get("message", ""),
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

# NOTE: there is deliberately no "Write Code" tool. It used to return a fixed
# `def main(): pass` stub for every specification, which polluted the developer
# agent's context with a non-answer. Writing code is what the model itself does;
# `Create File` below persists the result.

@tool("Create File")
def create_file(filepath: str, content: str, language: str) -> str:
    """Create a file with the given content."""
    result = dev_tools.create_file_impl(filepath, content, language)
    return json.dumps(result, indent=2)

@tool("Check Syntax")
def check_syntax(code: str, language: str) -> str:
    """Parse code and report syntax errors. Does NOT execute any test suite."""
    result = dev_tools.check_syntax_impl(code, language)
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

            # A missing key used to return status "success" with findings=None,
            # so an agent whose upstream handoff failed carried on as though it
            # had data. Report the miss, and say what *is* available.
            if findings is None:
                available = sorted(ctx.get_all(agent_name).keys())
                return {
                    "status": "not_found",
                    "agent": agent_name,
                    "key": key,
                    "findings": None,
                    "available_keys": available,
                    "message": (
                        f"No findings stored under agent={agent_name!r} key={key!r}. "
                        + (f"Available keys for this agent: {available}. "
                           if available else
                           f"This agent has written nothing yet. ")
                        + "Do not invent results — say the upstream data is missing."
                    ),
                }

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
