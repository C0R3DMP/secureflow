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
@click.option(
    "--format", "fmt",
    type=click.Choice(["html", "pdf", "json"], case_sensitive=False),
    default="html",
    show_default=True,
    help="Output report format.",
)
def scan(target, fmt):
    """Run security assessment on target."""
    click.secho(f"\n🔒 Starting security assessment of {target}...\n", fg="blue", bold=True)

    try:
        from secureflow.crew.orchestrator import CrewOrchestrator
        from secureflow.crew.history import SessionHistory
        from secureflow.reports import ReportExporter

        orchestrator = CrewOrchestrator()
        result = orchestrator.run_security_crew(target)

        SessionHistory().record(
            session_type="security",
            target=target,
            status="success" if result.get("success") else "failed",
            summary=result.get("error", "")[:200],
        )

        if result.get("success"):
            exporter = ReportExporter()
            report_path = exporter.export(fmt, result, target)
            click.secho("\n✅ Security assessment completed!", fg="green", bold=True)
            click.secho(f"   Report ({fmt.upper()}): {report_path}", fg="green")
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


@cli.group()
def schedule():
    """Manage scheduled security assessments."""
    pass


@schedule.command("add")
@click.argument("target")
@click.option("--cron", required=True, help='5-field cron expression, e.g. "0 3 * * *"')
def schedule_add(target, cron):
    """Schedule a recurring security scan on TARGET."""
    try:
        from secureflow.scheduler import get_manager
        job_id = get_manager().add(target, cron)
        click.secho(f"\n✅ Scheduled scan added", fg="green", bold=True)
        click.secho(f"   ID:     {job_id}", fg="cyan")
        click.secho(f"   Target: {target}", fg="cyan")
        click.secho(f"   Cron:   {cron}", fg="cyan")
    except ValueError as e:
        click.secho(f"\n❌ Invalid cron expression: {e}", fg="red", bold=True)
        raise SystemExit(1)
    except Exception as e:
        click.secho(f"\n❌ Error: {e}", fg="red", bold=True)
        raise SystemExit(1)


@schedule.command("list")
def schedule_list():
    """List all scheduled scans."""
    from secureflow.scheduler import get_manager
    jobs = get_manager().list_jobs()

    if not jobs:
        click.secho("\nNo scheduled scans.", fg="yellow")
        return

    click.secho("\n" + "=" * 70, fg="cyan")
    click.secho("Scheduled Scans", fg="cyan", bold=True)
    click.secho("=" * 70, fg="cyan")
    click.secho(f"\n{'ID':<36} {'Target':<25} {'Next Run (UTC)'}", fg="cyan", bold=True)
    click.secho("-" * 70, fg="cyan")
    for j in jobs:
        click.secho(f"{j['id']:<36} {j['target']:<25} {j['next_run'] or 'N/A'}", fg="white")
    click.secho("")


@schedule.command("remove")
@click.argument("job_id")
def schedule_remove(job_id):
    """Remove a scheduled scan by JOB_ID."""
    try:
        from secureflow.scheduler import get_manager
        get_manager().remove(job_id)
        click.secho(f"\n✅ Scheduled scan {job_id} removed.", fg="green", bold=True)
    except KeyError as e:
        click.secho(f"\n❌ Not found: {e}", fg="red", bold=True)
        raise SystemExit(1)
    except Exception as e:
        click.secho(f"\n❌ Error: {e}", fg="red", bold=True)
        raise SystemExit(1)


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


@cli.command()
@click.option("--attach", is_flag=True, help="Attach to existing session if running")
def server_launch(attach):
    """Launch SecureFlow server in a screen session."""
    import subprocess
    import time

    session_name = "secureflow-server"

    # Check if screen session already exists
    try:
        result = subprocess.run(
            ["screen", "-list"],
            capture_output=True,
            text=True,
            timeout=5
        )
        session_exists = session_name in result.stdout
    except Exception:
        session_exists = False

    if session_exists:
        if attach:
            click.secho(f"📺 Attaching to existing screen session: {session_name}\n", fg="cyan")
            try:
                os.execvp("screen", ["screen", "-r", session_name])
            except Exception as e:
                click.secho(f"❌ Failed to attach: {e}", fg="red")
                return 1
        else:
            click.secho(f"✅ Server is already running in screen session: {session_name}", fg="green")
            click.secho(f"   To attach: secureflow server-launch --attach", fg="cyan")
            click.secho(f"   To stop: screen -S {session_name} -X quit", fg="cyan")
            return 0

    # Create new screen session and start server
    click.secho(f"🚀 Starting server in new screen session: {session_name}\n", fg="blue", bold=True)

    try:
        # Get python path
        python_path = sys.executable

        # Create screen session and run server
        subprocess.Popen([
            "screen",
            "-dmS", session_name,
            python_path, "-m", "secureflow", "server"
        ])

        click.secho(f"✅ Server launched in screen session", fg="green")
        click.secho(f"   Session name: {session_name}", fg="green")
        click.secho(f"   Dashboard: http://localhost:5000/ui", fg="cyan")
        click.secho(f"   To attach: secureflow server-launch --attach", fg="cyan")
        click.secho(f"   To stop: screen -S {session_name} -X quit", fg="cyan")
        return 0

    except Exception as e:
        click.secho(f"❌ Failed to launch server: {e}", fg="red", bold=True)
        logger.error(f"server-launch failed: {str(e)}", exc_info=True)
        return 1


@cli.command()
def tui():
    """Launch interactive TUI management interface."""
    click.secho("\n📊 SecureFlow TUI Management Interface\n", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")

    try:
        from secureflow.config import LLMProviderStatus
        import requests
        import time

        # Check server status
        try:
            response = requests.get("http://localhost:5000/crew_status", timeout=2)
            server_status = response.json() if response.status_code == 200 else None
        except Exception:
            server_status = None

        # Display status
        if server_status:
            click.secho("✅ Server Status: RUNNING", fg="green")
            click.secho(f"   Host: localhost:5000", fg="cyan")
            click.secho(f"   Dashboard: http://localhost:5000/ui", fg="cyan")
        else:
            click.secho("⚠️  Server Status: NOT RUNNING", fg="yellow")
            click.secho("   Start with: secureflow server-launch", fg="yellow")

        # Display provider status
        click.secho("\n🔌 Provider Status:", fg="cyan")
        providers = LLMProviderStatus.get_available_providers()
        if providers:
            for provider, priority in providers:
                status = "✅" if LLMProviderStatus.check_health(provider) else "❌"
                click.secho(f"   {status} {provider.upper():<10} (Priority: {priority})", fg="green" if status == "✅" else "red")
        else:
            click.secho("   ❌ No providers configured", fg="red")

        # Display quick stats
        from secureflow.crew.history import SessionHistory
        history = SessionHistory()
        sessions = history.get_sessions(limit=5)

        click.secho("\n📈 Recent Sessions:", fg="cyan")
        if sessions:
            for s in sessions[:5]:
                status_color = "green" if s["status"] == "success" else "red"
                click.secho(f"   {s['type']:8} | {s['target'][:30]:30} | {s['status']:8}", fg=status_color)
        else:
            click.secho("   (No sessions yet)", fg="white")

        click.secho("\n" + "=" * 60, fg="cyan")
        click.secho("Commands:", fg="cyan", bold=True)
        click.secho("  secureflow scan <target>          Run security scan", fg="cyan")
        click.secho("  secureflow build '<task>'         Build application", fg="cyan")
        click.secho("  secureflow server-launch          Start server", fg="cyan")
        click.secho("  secureflow config                 Configure providers", fg="cyan")
        click.secho("  secureflow history                View session history", fg="cyan")

        return 0

    except Exception as e:
        click.secho(f"\n❌ Error: {str(e)}", fg="red", bold=True)
        logger.error(f"TUI failed: {str(e)}", exc_info=True)
        return 1


@cli.command()
def config():
    """Configure SecureFlow providers and settings."""
    import subprocess

    click.secho("\n⚙️  SecureFlow Configuration\n", fg="cyan", bold=True)
    click.secho("=" * 60, fg="cyan")

    # Open dashboard config page
    dashboard_url = "http://localhost:5000/ui"
    click.secho("📊 Opening configuration dashboard...", fg="blue")
    click.secho(f"   URL: {dashboard_url}", fg="cyan")
    click.secho("\n📋 Provider Configuration:", fg="cyan")
    click.secho("   1. Go to http://localhost:5000/ui", fg="cyan")
    click.secho("   2. Click 'Settings' in the interface", fg="cyan")
    click.secho("   3. Configure your LLM providers:", fg="cyan")
    click.secho("      - Claude (Anthropic API)", fg="dim")
    click.secho("      - Gemini (Google AI Studio)", fg="dim")
    click.secho("      - Ollama (Local, free)", fg="dim")
    click.secho("   4. Test each provider connection", fg="cyan")
    click.secho("   5. Set provider priorities and quotas", fg="cyan")

    # Try to open browser
    try:
        subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", dashboard_url])
        click.secho("\n✅ Dashboard opened in browser", fg="green")
    except Exception:
        click.secho(f"\n⚠️  Could not open browser. Visit {dashboard_url} manually", fg="yellow")

    click.secho("\n" + "=" * 60, fg="cyan")
    return 0


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
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
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
