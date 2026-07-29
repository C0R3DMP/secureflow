"""Real static analysis for the code-review tools.

Everything here is *measured*, not asserted. The previous implementations
returned fixed values — `bugs_found: 0`, `quality_score: 85`, `tests_passed: 3`
— regardless of input. Those values were fed back to an LLM as tool output,
which treated them as ground truth and wrote them into review reports.

Where an analysis genuinely cannot be performed (a language we have no parser
for), these functions say so explicitly instead of inventing a number.
"""

import ast
import re
from typing import Any, Dict, List

__all__ = ["analyse_python", "review_metrics", "syntax_check", "SUPPORTED_LANGUAGES"]

SUPPORTED_LANGUAGES = {"python", "py", "python3"}

# Names that look like credentials when assigned a string literal.
_SECRET_NAME_RE = re.compile(
    r"(pass(word|wd)?|secret|token|api_?key|access_?key|private_?key|credential)",
    re.IGNORECASE,
)

# A short literal is more likely a placeholder/sentinel than a real credential.
_MIN_SECRET_LEN = 6

_SQL_RE = re.compile(r"\b(select|insert|update|delete|drop|union)\b", re.IGNORECASE)


def _is_python(language: str) -> bool:
    return str(language or "").strip().lower() in SUPPORTED_LANGUAGES


def _finding(severity: str, kind: str, line: int, message: str) -> Dict[str, Any]:
    return {"severity": severity, "type": kind, "line": line, "message": message}


class _BugVisitor(ast.NodeVisitor):
    """Walks a Python AST collecting concrete, evidence-backed findings."""

    def __init__(self) -> None:
        self.findings: List[Dict[str, Any]] = []

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            parts = [func.attr]
            value = func.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            return ".".join(reversed(parts))
        return ""

    @staticmethod
    def _is_dynamic_string(node: ast.AST) -> bool:
        """True when a string is assembled at runtime (f-string, %, +, .format)."""
        if isinstance(node, ast.JoinedStr):
            return any(isinstance(v, ast.FormattedValue) for v in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
            return True
        if isinstance(node, ast.Call):
            func = node.func
            return isinstance(func, ast.Attribute) and func.attr == "format"
        return False

    @staticmethod
    def _static_text(node: ast.AST) -> str:
        """Best-effort literal text of a possibly-dynamic string node."""
        chunks: List[str] = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                chunks.append(sub.value)
        return " ".join(chunks)

    # -- visitors --------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node)

        if name in ("eval", "exec"):
            self.findings.append(_finding(
                "critical", "code_injection", node.lineno,
                f"{name}() executes arbitrary code; avoid it on any untrusted value",
            ))

        if name in ("os.system", "os.popen"):
            dynamic = any(self._is_dynamic_string(a) for a in node.args)
            self.findings.append(_finding(
                "critical" if dynamic else "high", "command_injection", node.lineno,
                f"{name}() runs a shell command"
                + (" built from a runtime value" if dynamic else ""),
            ))

        if name.startswith("subprocess."):
            for kw in node.keywords:
                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    self.findings.append(_finding(
                        "high", "command_injection", node.lineno,
                        "subprocess called with shell=True; pass an argument list instead",
                    ))

        if name in ("pickle.loads", "pickle.load", "dill.loads"):
            self.findings.append(_finding(
                "high", "unsafe_deserialization", node.lineno,
                f"{name}() executes code embedded in the payload",
            ))

        if name == "yaml.load" and not any(kw.arg == "Loader" for kw in node.keywords):
            self.findings.append(_finding(
                "high", "unsafe_deserialization", node.lineno,
                "yaml.load() without Loader= can construct arbitrary objects; use safe_load()",
            ))

        # SQL assembled by string interpolation, then handed to a DB cursor.
        if name.endswith("execute") or name.endswith("executemany"):
            for arg in node.args:
                if self._is_dynamic_string(arg) and _SQL_RE.search(self._static_text(arg)):
                    self.findings.append(_finding(
                        "critical", "sql_injection", node.lineno,
                        "SQL statement built by string interpolation; use bound parameters",
                    ))

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # SQL string built by interpolation (flagged even before it is executed).
        if self._is_dynamic_string(node.value) and _SQL_RE.search(self._static_text(node.value)):
            self.findings.append(_finding(
                "high", "sql_injection", node.lineno,
                "SQL statement assembled by string interpolation; use bound parameters",
            ))

        # Hardcoded credentials.
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            if len(node.value.value) >= _MIN_SECRET_LEN:
                for target in node.targets:
                    names = [target.id] if isinstance(target, ast.Name) else []
                    if isinstance(target, ast.Attribute):
                        names = [target.attr]
                    for candidate in names:
                        if _SECRET_NAME_RE.search(candidate):
                            self.findings.append(_finding(
                                "high", "hardcoded_secret", node.lineno,
                                f"{candidate!r} is assigned a literal string; load it from the environment",
                            ))

        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.findings.append(_finding(
                "medium", "broad_except", node.lineno,
                "bare 'except:' also swallows KeyboardInterrupt and SystemExit",
            ))
        body = node.body
        if len(body) == 1 and isinstance(body[0], ast.Pass):
            self.findings.append(_finding(
                "medium", "silent_failure", node.lineno,
                "exception is caught and discarded, hiding real failures",
            ))
        self.generic_visit(node)

    def _check_mutable_defaults(self, node) -> None:
        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.findings.append(_finding(
                    "medium", "mutable_default_arg", node.lineno,
                    f"{node.name}() has a mutable default argument, shared across calls",
                ))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_mutable_defaults(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_mutable_defaults(node)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(comparator, ast.Constant):
                if comparator.value is None:
                    self.findings.append(_finding(
                        "low", "identity_comparison", node.lineno,
                        "compare to None with 'is' / 'is not', not '==' / '!='",
                    ))
        self.generic_visit(node)


def syntax_check(code: str, language: str) -> Dict[str, Any]:
    """Parse the source. Returns whether it is syntactically valid."""
    if not _is_python(language):
        return {
            "checked": False,
            "valid": None,
            "reason": f"no parser available for {language!r}; only Python is analysed",
        }
    try:
        ast.parse(code)
        return {"checked": True, "valid": True}
    except SyntaxError as exc:
        return {
            "checked": True,
            "valid": False,
            "error": {"message": exc.msg, "line": exc.lineno, "offset": exc.offset},
        }


def analyse_python(code: str, language: str = "python") -> Dict[str, Any]:
    """Find concrete defects in Python source via AST inspection."""
    if not _is_python(language):
        return {
            "status": "unsupported",
            "language": language,
            "analysed": False,
            "findings": [],
            "message": (
                f"Static analysis is not implemented for {language!r}. "
                "Review the code directly rather than relying on this tool."
            ),
        }

    syntax = syntax_check(code, language)
    if syntax.get("valid") is False:
        err = syntax["error"]
        return {
            "status": "syntax_error",
            "language": language,
            "analysed": False,
            "findings": [_finding("critical", "syntax_error", err["line"] or 0, err["message"])],
            "message": f"Source does not parse: {err['message']} (line {err['line']})",
        }

    visitor = _BugVisitor()
    visitor.visit(ast.parse(code))
    findings = sorted(visitor.findings, key=lambda f: (f["line"], f["type"]))

    severity_counts: Dict[str, int] = {}
    for f in findings:
        severity_counts[f["severity"]] = severity_counts.get(f["severity"], 0) + 1

    return {
        "status": "success",
        "language": language,
        "analysed": True,
        "findings_count": len(findings),
        "severity_counts": severity_counts,
        "findings": findings,
    }


def review_metrics(code: str, language: str) -> Dict[str, Any]:
    """Compute real size/complexity metrics for the supplied source."""
    lines = code.splitlines()
    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    comments = sum(1 for line in lines if line.strip().startswith("#"))
    todos = sum(1 for line in lines if re.search(r"\b(TODO|FIXME|XXX|HACK)\b", line))
    longest_line = max((len(line) for line in lines), default=0)

    metrics: Dict[str, Any] = {
        "total_lines": total,
        "code_lines": total - blank - comments,
        "blank_lines": blank,
        "comment_lines": comments,
        "todo_markers": todos,
        "longest_line_chars": longest_line,
    }

    if _is_python(language):
        syntax = syntax_check(code, language)
        if syntax.get("valid"):
            tree = ast.parse(code)
            functions = [
                n for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

            def _span(node) -> int:
                end = getattr(node, "end_lineno", None) or node.lineno
                return end - node.lineno + 1

            longest_fn = max(functions, key=_span, default=None)
            documented = sum(1 for f in functions if ast.get_docstring(f))

            metrics.update({
                "functions": len(functions),
                "classes": len(classes),
                "documented_functions": documented,
                "longest_function": (
                    {"name": longest_fn.name, "lines": _span(longest_fn), "line": longest_fn.lineno}
                    if longest_fn else None
                ),
                "max_nesting_depth": _max_depth(tree),
            })
        else:
            metrics["parse_error"] = syntax.get("error")

    return metrics


def _max_depth(tree: ast.AST) -> int:
    """Deepest nesting of control-flow blocks."""
    nesting = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)

    def walk(node: ast.AST, depth: int) -> int:
        best = depth
        for child in ast.iter_child_nodes(node):
            child_depth = depth + 1 if isinstance(child, nesting) else depth
            best = max(best, walk(child, child_depth))
        return best

    return walk(tree, 0)
