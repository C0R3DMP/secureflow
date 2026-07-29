"""Central security primitives: target validation, safe path joins, request auth.

This module is deliberately dependency-light so it can be imported from the
tools layer (which runs inside agent threads) as well as the HTTP layer.
"""

import hmac
import ipaddress
import logging
import re
import secrets
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__all__ = [
    "InvalidTarget",
    "validate_target",
    "safe_join",
    "report_stem",
    "token_matches",
    "generate_token",
    "extract_token",
    "BearerAuthMiddleware",
]


# ---------------------------------------------------------------------------
# Scan target validation
# ---------------------------------------------------------------------------

class InvalidTarget(ValueError):
    """Raised when a scan target fails validation."""


# Characters that must never reach a subprocess argv, a DNS lookup, or a
# filename. Note ':' and '/' are absent: they are legal in IPv6 / CIDR and are
# handled by the structural checks below.
_FORBIDDEN_CHARS = set(" \t\r\n\x00;|&$`<>()'\"\\!*?[]{}#%,@=+^~")

# RFC 1123 hostname (optionally fully qualified, optional trailing dot).
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\.?$)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
    r"\.?$"
)

MAX_TARGET_LEN = 253


def validate_target(raw: str) -> str:
    """Normalise and validate a scan target.

    Accepts a bare hostname, an IPv4/IPv6 address, a CIDR network, or a URL
    (from which the host is extracted). Returns the canonical host string that
    is safe to hand to ``nmap`` argv, ``socket.gethostbyname``, and filenames.

    Raises:
        InvalidTarget: if the value could be misread as a command-line flag,
            contains shell/argv metacharacters, or is not a routable target.
    """
    if not isinstance(raw, str):
        raise InvalidTarget(f"target must be a string, got {type(raw).__name__}")

    target = raw.strip()
    if not target:
        raise InvalidTarget("target must not be empty")

    # Pull the host out of a URL so "https://example.com:8443/path" works.
    if "://" in target:
        parsed = urlparse(target)
        host = parsed.hostname  # lowercased, port and credentials stripped
        if not host:
            raise InvalidTarget(f"cannot extract a host from URL {raw!r}")
        target = host

    if len(target) > MAX_TARGET_LEN:
        raise InvalidTarget(f"target exceeds {MAX_TARGET_LEN} characters")

    # A leading '-' would be parsed by nmap as an option, not a target
    # (e.g. "-oN/etc/cron.d/x" or "--script=/tmp/evil.nse"). Reject outright.
    if target.startswith("-"):
        raise InvalidTarget(
            f"target {raw!r} may not start with '-' (would be read as a command-line flag)"
        )

    bad = sorted(_FORBIDDEN_CHARS.intersection(target))
    if bad:
        raise InvalidTarget(f"target {raw!r} contains forbidden character(s): {''.join(bad)!r}")

    # Structural check: IP address, IP network, or hostname.
    candidate = target.rstrip(".") or target
    try:
        ipaddress.ip_address(candidate)
        return target
    except ValueError:
        pass
    if "/" in candidate:
        try:
            ipaddress.ip_network(candidate, strict=False)
            return target
        except ValueError as exc:
            raise InvalidTarget(f"target {raw!r} is not a valid IP network: {exc}") from exc

    if not _HOSTNAME_RE.match(target):
        raise InvalidTarget(f"target {raw!r} is not a valid hostname, IP address, or CIDR network")

    return target


# ---------------------------------------------------------------------------
# Filesystem safety
# ---------------------------------------------------------------------------

def safe_join(base: Path, relative: str) -> Optional[Path]:
    """Join ``relative`` onto ``base``, returning None if it escapes ``base``.

    Guards against ``../`` traversal, absolute paths, and symlink escapes.
    The caller is expected to pass an already URL-decoded ``relative`` — this
    function never decodes, to avoid a double-decoding bypass.
    """
    try:
        base_resolved = Path(base).resolve()
        candidate = (base_resolved / str(relative).lstrip("/\\")).resolve()
    except (OSError, ValueError):
        return None

    if candidate != base_resolved and base_resolved not in candidate.parents:
        return None
    return candidate


def report_stem(target: str) -> str:
    """Canonical, filesystem-safe stem for a target's report files.

    Single source of truth: the orchestrator writes reports under this name and
    the export endpoint looks them up by it. Keep them in lockstep.
    """
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", str(target))
    stem = stem.lstrip(".") or "target"
    return stem[:100]


# ---------------------------------------------------------------------------
# Request authentication
# ---------------------------------------------------------------------------

def generate_token(nbytes: int = 32) -> str:
    """Generate a cryptographically random hex token."""
    return secrets.token_hex(nbytes)


def token_matches(presented: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time token comparison."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(str(presented), str(expected))


def extract_token(headers: dict, query_string: str) -> Optional[str]:
    """Pull a bearer token out of headers or the query string.

    The query-string fallback exists because the browser ``EventSource`` API
    used by the dashboard cannot set request headers.
    """
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()

    direct = headers.get("x-secureflow-token")
    if direct:
        return direct.strip()

    if query_string:
        from urllib.parse import parse_qs
        values = parse_qs(query_string).get("token")
        if values:
            return values[0]

    return None


class BearerAuthMiddleware:
    """Pure-ASGI middleware enforcing a shared bearer secret.

    Every HTTP path is protected except those under ``public_prefixes`` (the
    static dashboard, which is inert without API access). Requests without a
    valid token get 401 before any handler — including the MCP transport
    endpoints that expose the scanning tools.
    """

    def __init__(
        self,
        app,
        secret: str,
        public_prefixes: Iterable[str] = ("/ui", "/health"),
    ):
        self.app = app
        self.secret = secret
        self.public_prefixes = tuple(public_prefixes)

    def _is_public(self, path: str) -> bool:
        for prefix in self.public_prefixes:
            trimmed = prefix.rstrip("/")
            if path == trimmed or path.startswith(trimmed + "/"):
                return True
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.secret:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if self._is_public(path):
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        query_string = scope.get("query_string", b"").decode("latin-1")
        presented = extract_token(headers, query_string)

        if not token_matches(presented, self.secret):
            logger.warning(
                "Rejected unauthenticated %s %s from %s",
                scope.get("method", "?"), path,
                (scope.get("client") or ("?",))[0],
            )
            await self._unauthorized(send)
            return

        await self.app(scope, receive, send)

    @staticmethod
    async def _unauthorized(send) -> None:
        body = b'{"error":"unauthorized","detail":"valid MCP_SECRET bearer token required"}'
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b'Bearer realm="secureflow"'),
            ],
        })
        await send({"type": "http.response.body", "body": body})
