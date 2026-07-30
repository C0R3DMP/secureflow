"""Best-effort, locally-tracked LLM request budget.

Roadmap item "Now #4". The free tiers this project targets have no "check
remaining calls" endpoint — quota state lives server-side and isn't queryable
in advance. Verified live this week: a Gemini free-tier key's *daily* quota
(20 requests/day, separate from the well-documented 5/min rate limit) was
exhausted by a single full crew run, and the only signal was a raw 429 after
the next scan had already failed.

This tracks what SecureFlow itself has attempted today (UTC) and records the
actual limit a provider reports the moment a 429 is hit, so the dashboard can
show *something* before a scan starts instead of only an error after one
fails. It is explicitly an estimate: other processes, other sessions, or the
same key used elsewhere are invisible to this process's memory, and it resets
on restart. Never present it as authoritative.
"""

import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Iterable

__all__ = ["record_attempt", "record_quota_exhausted", "snapshot", "snapshot_all"]

_lock = threading.Lock()
_state: Dict[str, Dict[str, Any]] = {}

# Quote-agnostic: the same error surfaces as raw double-quoted JSON (an HTTP
# response body) in some call paths, and as Python's single-quoted dict-repr
# (str(exception), which stringifies a parsed dict) in others — verified live
# in both forms this week.
_QUOTA_VALUE_RE = re.compile(r"""["']quotaValue["']\s*:\s*["'](\d+)["']""")
_QUOTA_METRIC_RE = re.compile(r"""["']quotaMetric["']\s*:\s*["']([^"']+)["']""")
_QUOTA_ID_RE = re.compile(r"""["']quotaId["']\s*:\s*["']([^"']+)["']""")


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _bucket(provider: str) -> Dict[str, Any]:
    """Return today's (UTC) counter for a provider, resetting it if the date rolled over."""
    today = _today_key()
    entry = _state.get(provider)
    if entry is None or entry.get("date") != today:
        entry = {
            "date": today,
            "attempts": 0,
            "exhausted_at": None,
            "known_limit": None,
            "quota_metric": None,
        }
        _state[provider] = entry
    return entry


def record_attempt(provider: str) -> None:
    """Call once per outbound request attempt to a provider, before it fires."""
    with _lock:
        _bucket(provider)["attempts"] += 1


def record_quota_exhausted(provider: str, error_text: str = "") -> None:
    """Call when a provider returns a quota/rate-limit error.

    Parses whatever limit/metric details the error actually contains (Gemini's
    429 body includes exact figures — verified live: 'quotaValue': '20',
    metric 'generate_content_free_tier_requests') without assuming a fixed
    format other providers must match.
    """
    with _lock:
        entry = _bucket(provider)
        entry["exhausted_at"] = datetime.now(timezone.utc).isoformat()

        value_match = _QUOTA_VALUE_RE.search(error_text)
        if value_match:
            entry["known_limit"] = int(value_match.group(1))

        metric_match = _QUOTA_METRIC_RE.search(error_text) or _QUOTA_ID_RE.search(error_text)
        if metric_match:
            entry["quota_metric"] = metric_match.group(1)


def snapshot(provider: str) -> Dict[str, Any]:
    """Today's (UTC) tracked state for one provider. Always an estimate."""
    with _lock:
        entry = dict(_bucket(provider))
    return {
        "attempts_today": entry["attempts"],
        "known_limit": entry["known_limit"],
        "quota_metric": entry["quota_metric"],
        "exhausted_at": entry["exhausted_at"],
        "estimate": True,
    }


def snapshot_all(providers: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    return {p: snapshot(p) for p in providers}
