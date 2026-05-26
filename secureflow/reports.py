"""Report export utilities — HTML, PDF, JSON."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

_REPORT_DIR = Path.home() / ".secureflow"


def _report_stem(target: str) -> str:
    return target.replace("/", "_").replace(":", "_").replace(" ", "_")


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
        raise ValueError(f"Unsupported format: {fmt!r}. Choose html, pdf, or json.")

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
            "session_log": result.get("session_log", ""),
            "report_path": result.get("report_path", ""),
        }

        path = self.output_dir / f"report_{_report_stem(target)}.json"
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
