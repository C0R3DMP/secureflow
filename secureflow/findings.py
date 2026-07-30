"""Pure helpers for comparing structured finding lists across scans.

Kept separate from crew/tools.py and crew/history.py so both can import it
without a circular dependency — the orchestrator needs it to diff a fresh
scan against SessionHistory's last record for the same target.
"""

from typing import Any, Dict, List

__all__ = ["diff_findings"]


def _finding_key(finding: Dict[str, Any]) -> str:
    """Same dedup key SecurityTools.severity_counts()/get_findings() use, so a
    finding that's genuinely unchanged across two scans can't be miscounted
    as both resolved and new just because it lacks a CVE reference."""
    reference = finding.get("reference") or ""
    if reference:
        return reference
    return f"{finding.get('source', '')}:{finding.get('severity', '')}"


def diff_findings(
    previous: List[Dict[str, Any]], current: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """Compare a target's previous scan's findings against its current ones.

    Returns {"new": [...], "resolved": [...]} — findings present now but not
    before, and findings present before but absent now. A finding unchanged
    between scans appears in neither list.
    """
    previous_by_key = {_finding_key(f): f for f in previous}
    current_by_key = {_finding_key(f): f for f in current}

    new = [f for key, f in current_by_key.items() if key not in previous_by_key]
    resolved = [f for key, f in previous_by_key.items() if key not in current_by_key]
    return {"new": new, "resolved": resolved}
