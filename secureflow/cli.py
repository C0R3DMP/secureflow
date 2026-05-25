#!/usr/bin/env python3
"""SecureFlow CLI - Command line interface for SecureFlow."""

import sys
import os
import logging
from pathlib import Path
import click
from secureflow import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("secureflow.cli")


@click.group()
@click.version_option(version=__version__, prog_name="secureflow")
def cli():
    """
    SecureFlow: AI-powered security assessment and application development crew.

    Use 'secureflow COMMAND --help' for more information on each command.
    """
    pass


@cli.command()
def status():
    """Check system status and verify all dependencies."""
    click.secho("\n" + "=" * 80, fg="cyan")
    click.secho("SecureFlow System Status Check", fg="cyan", bold=True)
    click.secho("=" * 80 + "\n", fg="cyan")

    checks = {
        "Python Version": _check_python(),
        "Virtual Environment": _check_venv(),
        "CrewAI": _check_import("crewai"),
        "FastMCP": _check_import("fastmcp"),
        "LiteLLM": _check_import("litellm"),
        "Pydantic": _check_import("pydantic"),
        "OpenCode CLI": _check_opencode(),
        "nmap": _check_nmap(),
    }

    all_passed = True
    for check_name, (status, message) in checks.items():
        symbol = "✅" if status else "❌"
        color = "green" if status else "red"
        click.secho(f"{symbol} {check_name:<30} {message}", fg=color)
        if not status:
            all_passed = False

    # Configuration checks
    click.secho("\nConfiguration:", fg="cyan", bold=True)
    env_vars = _check_env_vars()
    for var_name, (is_set, value) in env_vars.items():
        symbol = "✅" if is_set else "⚠️ "
        status_str = "Set" if is_set else "Not set"
        click.secho(f"{symbol} {var_name:<25} {status_str}", fg="green" if is_set else "yellow")

    click.secho("\n" + "=" * 80, fg="cyan")
    if all_passed:
        click.secho("✅ All checks passed! SecureFlow is ready to use.", fg="green", bold=True)
        return 0
    else:
        click.secho("❌ Some checks failed. Please review above and fix issues.", fg="red", bold=True)
        return 1


@cli.command()
@click.argument("task")
@click.option("--language", default="python", help="Programming language (python, javascript, go, rust, etc.)")
@click.option("--output", default="/tmp/dev_output", help="Output directory for generated files")
def build(task, language, output):
    """Build an application using the development crew."""
    click.secho(f"\n🚀 Starting development crew for {language}...\n", fg="blue", bold=True)

    try:
        from secureflow.crew.dev_orchestrator import DevOrchestrator

        from secureflow.crew.history import SessionHistory

        orchestrator = DevOrchestrator()
        result = orchestrator.run_dev_crew(task, language, output)

        SessionHistory().record(
            session_type="dev",
            target=task[:120],
            status="success" if result.get("status") == "success" else "failed",
            summary=result.get("error", "")[:200],
        )

        if result.get("status") == "success":
            click.secho("\n✅ Development crew completed successfully!", fg="green", bold=True)
            click.secho(f"   Output directory: {output}", fg="green")
            click.secho(f"   Session log: {orchestrator.log_path}", fg="green")
            return 0
        else:
            click.secho(f"\n❌ Development crew failed: {result.get('error', 'Unknown error')}", fg="red", bold=True)
            return 1
    except Exception as e:
        click.secho(f"\n❌ Error: {str(e)}", fg="red", bold=True)
        logger.error(f"Build command failed: {str(e)}", exc_info=True)
        return 1


@cli.command()
@click.argument("target")
def scan(target):
    """Run security assessment on target."""
    click.secho(f"\n🔒 Starting security assessment of {target}...\n", fg="blue", bold=True)

    try:
        from secureflow.crew.orchestrator import CrewOrchestrator
        from secureflow.crew.history import SessionHistory

        orchestrator = CrewOrchestrator()
        result = orchestrator.run_security_crew(target)

        SessionHistory().record(
            session_type="security",
            target=target,
            status="success" if result.get("success") else "failed",
            summary=result.get("error", "")[:200],
        )

        if result.get("success"):
            click.secho("\n✅ Security assessment completed!", fg="green", bold=True)
            click.secho(f"   Session log: {orchestrator.log_path}", fg="green")
            return 0
        else:
            click.secho(f"\n❌ Assessment failed: {result.get('error', 'Unknown error')}", fg="red", bold=True)
            return 1
    except Exception as e:
        click.secho(f"\n❌ Error: {str(e)}", fg="red", bold=True)
        logger.error(f"Scan command failed: {str(e)}", exc_info=True)
        return 1


@cli.command()
@click.option("--limit", default=20, show_default=True, help="Number of sessions to show")
@click.option("--type", "session_type", default=None, help="Filter by type: security, dev")
def history(limit, session_type):
    """Show history of past scan and build sessions."""
    from secureflow.crew.history import SessionHistory

    sessions = SessionHistory().get_sessions(limit=limit, session_type=session_type)

    if not sessions:
        click.secho("\nNo sessions found.", fg="yellow")
        return

    click.secho("\n" + "=" * 80, fg="cyan")
    click.secho("SecureFlow Session History", fg="cyan", bold=True)
    click.secho("=" * 80, fg="cyan")
    click.secho(
        f"\n{'ID':<5} {'Type':<10} {'Target / Task':<38} {'Status':<10} Completed",
        fg="cyan",
        bold=True,
    )
    click.secho("-" * 80, fg="cyan")

    for s in sessions:
        color = "green" if s["status"] == "success" else "red"
        target_col = s["target"][:36] + ".." if len(s["target"]) > 38 else s["target"]
        completed = (s["completed_at"] or "")[:19]
        click.secho(
            f"{s['id']:<5} {s['type']:<10} {target_col:<38} {s['status']:<10} {completed}",
            fg=color,
        )

    click.secho("")


@cli.command()
def server():
    """Start the SecureFlow MCP server."""
    click.secho("\n🚀 Starting SecureFlow MCP Server...\n", fg="blue", bold=True)

    try:
        from secureflow.server import main as server_main
        server_main()
    except Exception as e:
        click.secho(f"\n❌ Server error: {str(e)}", fg="red", bold=True)
        logger.error(f"Server failed: {str(e)}", exc_info=True)
        return 1


def _check_python():
    """Check Python version."""
    import sys
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        return True, f"Python {version}"
    return False, f"Python {version} (requires 3.10+)"


def _check_venv():
    """Check if running in virtual environment."""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    if in_venv:
        return True, "Active"
    return False, "Not in virtual environment"


def _check_import(module_name):
    """Check if a module can be imported."""
    try:
        __import__(module_name)
        return True, "Installed"
    except ImportError:
        return False, "Not installed"


def _check_opencode():
    """Check if OpenCode CLI is available."""
    import subprocess
    try:
        result = subprocess.run(["opencode", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return True, "Available"
        return False, "Not found"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "Not found"


def _check_nmap():
    """Check if nmap is installed."""
    import subprocess
    try:
        result = subprocess.run(["nmap", "--version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return True, "Available"
        return False, "Not found"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "Not found"


def _check_env_vars():
    """Check important environment variables."""
    vars_to_check = {
        "MCP_SECRET": os.getenv("MCP_SECRET"),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY"),
        "OPENCODE_URL": os.getenv("OPENCODE_URL"),
        "OLLAMA_BASE_URL": os.getenv("OLLAMA_BASE_URL"),
    }

    return {
        name: (bool(value), value[:20] + "..." if value and len(value) > 20 else value)
        for name, value in vars_to_check.items()
    }


def main():
    """Main entry point."""
    try:
        cli()
    except KeyboardInterrupt:
        click.secho("\n\nInterrupted by user.", fg="yellow")
        sys.exit(130)
    except Exception as e:
        click.secho(f"\nUnexpected error: {str(e)}", fg="red", bold=True)
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
