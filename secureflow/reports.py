"""Report export utilities — HTML, PDF, JSON."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from secureflow.security import report_stem

_REPORT_DIR = Path.home() / ".secureflow"

# Backwards-compatible alias. The canonical implementation lives in
# secureflow.security so the orchestrator and the export endpoint cannot drift
# apart again — they previously produced different filenames for the same target.
_report_stem = report_stem


class ReportExporter:
    """Convert a completed scan result into HTML / PDF / JSON."""

    def __init__(self, output_dir: str = None):
        self.output_dir = Path(output_dir) if output_dir else _REPORT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, fmt: str, result: Dict[str, Any], target: str) -> str:
        """Dispatch to the correct format. Returns the output file path."""
        fmt = fmt.lower()
        if fmt == "html":
            return self.to_html(result, target)
        if fmt == "pdf":
            return self.to_pdf(result, target)
        if fmt == "json":
            return self.to_json(result, target)
        if fmt == "sarif":
            return self.to_sarif(result, target)
        raise ValueError(f"Unsupported format: {fmt!r}. Choose html, pdf, json, or sarif.")

    def to_html(self, result: Dict[str, Any], target: str) -> str:
        """Save (or reuse) the HTML report. Returns file path."""
        html_content = result.get("report_html", "")
        if not html_content:
            html_content = self._minimal_html(target, result.get("result", "No content"))

        path = self.output_dir / f"report_{_report_stem(target)}.html"
        path.write_text(html_content, encoding="utf-8")
        return str(path)

    def to_pdf(self, result: Dict[str, Any], target: str) -> str:
        """Generate a PDF from the HTML report. Returns file path."""
        try:
            from weasyprint import HTML
        except ImportError:
            raise RuntimeError(
                "PDF export requires weasyprint. Install with: "
                "pip install 'secureflow[export]'"
            )

        html_content = result.get("report_html", "")
        if not html_content:
            html_content = self._minimal_html(target, result.get("result", "No content"))

        path = self.output_dir / f"report_{_report_stem(target)}.pdf"
        HTML(string=html_content).write_pdf(str(path))
        return str(path)

    def to_json(self, result: Dict[str, Any], target: str) -> str:
        """Generate a structured JSON report. Returns file path."""
        payload = {
            "meta": {
                "tool": "SecureFlow AI",
                "version": "0.1.0",
                "target": target,
                "timestamp": datetime.now().isoformat(),
            },
            "status": "success" if result.get("success") else "error",
            "summary": (result.get("result", "") or "")[:2000],
            # Structured, per-CVE findings (severity, confidence, reference,
            # source) — from SecurityTools.get_findings() via the orchestrator
            # for a live scan, or the persisted session record for a
            # historical export. Empty if the caller has none available.
            "findings": result.get("findings", []),
            "diff": result.get("diff"),
            "session_log": result.get("session_log", ""),
            "report_path": result.get("report_path", ""),
        }

        path = self.output_dir / f"report_{_report_stem(target)}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    # SARIF severity levels are none/note/warning/error — map our four
    # severities onto them so ticketing systems that understand SARIF (most
    # do) can sort by the same priority a SecureFlow report would show.
    _SARIF_LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note"}

    def to_sarif(self, result: Dict[str, Any], target: str) -> str:
        """Generate a SARIF 2.1.0 log from structured findings. Returns file path.

        SARIF (Static Analysis Results Interchange Format) is what most CI
        and ticketing systems already know how to ingest — this is the
        integration path the prose/HTML report never had.
        """
        findings = result.get("findings") or []

        rules: List[Dict[str, Any]] = []
        seen_rule_ids = set()
        results: List[Dict[str, Any]] = []

        for finding in findings:
            rule_id = finding.get("reference") or finding.get("source") or "unknown"
            if rule_id not in seen_rule_ids:
                seen_rule_ids.add(rule_id)
                rules.append({
                    "id": rule_id,
                    "shortDescription": {"text": finding.get("description") or rule_id},
                })
            results.append({
                "ruleId": rule_id,
                "level": self._SARIF_LEVEL.get(finding.get("severity"), "warning"),
                "message": {
                    "text": finding.get("description")
                    or f"{finding.get('source', target)} — {rule_id}",
                },
                # Not part of core SARIF, but the spec reserves `properties`
                # for exactly this — carrying our confidence axis through
                # rather than losing it in the conversion.
                "properties": {
                    "severity": finding.get("severity"),
                    "confidence": finding.get("confidence"),
                },
                "locations": [{
                    "physicalLocation": {"artifactLocation": {"uri": target}},
                }],
            })

        payload = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [{
                "tool": {
                    "driver": {
                        "name": "SecureFlow",
                        "informationUri": "https://github.com/C0R3DMP/secureflow",
                        "version": "0.1.0",
                        "rules": rules,
                    },
                },
                "results": results,
            }],
        }

        path = self.output_dir / f"report_{_report_stem(target)}.sarif"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _minimal_html(target: str, content: str) -> str:
        import html as _html
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        safe = _html.escape(content)
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SecureFlow Report — {_html.escape(target)}</title>
  <style>
    body {{ font-family: sans-serif; background:#0f1419; color:#e0e6ed; padding:2rem; }}
    h1 {{ color:#667eea; }} pre {{ background:#1a1f2e; padding:1rem; border-radius:4px; white-space:pre-wrap; }}
  </style>
</head>
<body>
  <h1>Security Assessment Report</h1>
  <p><strong>Target:</strong> {_html.escape(target)} &nbsp;|&nbsp; <strong>Date:</strong> {ts}</p>
  <pre>{safe}</pre>
</body>
</html>"""
