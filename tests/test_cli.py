"""Test CLI commands."""

import pytest
from click.testing import CliRunner
from secureflow.cli import cli


@pytest.fixture
def runner():
    """Return Click CLI test runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "SecureFlow" in result.output
    assert "Usage:" in result.output


def test_cli_version(runner):
    """Test CLI version command."""
    result = runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_status_command(runner):
    """Test status command."""
    result = runner.invoke(cli, ["status"])

    assert result.exit_code in [0, 1]  # May pass or fail depending on system
    assert "Status Check" in result.output or "checks" in result.output.lower()


def test_cli_status_help(runner):
    """Test status command help."""
    result = runner.invoke(cli, ["status", "--help"])

    assert result.exit_code == 0
    assert "Check system status" in result.output or "status" in result.output.lower()


def test_cli_build_help(runner):
    """Test build command help."""
    result = runner.invoke(cli, ["build", "--help"])

    assert result.exit_code == 0
    assert "Build" in result.output or "build" in result.output.lower()


def test_cli_scan_help(runner):
    """Test scan command help."""
    result = runner.invoke(cli, ["scan", "--help"])

    assert result.exit_code == 0
    assert "scan" in result.output.lower()


def test_cli_server_help(runner):
    """Test server command help."""
    result = runner.invoke(cli, ["server", "--help"])

    assert result.exit_code == 0
    assert "server" in result.output.lower()


def test_cli_unknown_command(runner):
    """Test unknown command."""
    result = runner.invoke(cli, ["unknown"])

    assert result.exit_code != 0
    assert "Error" in result.output or "No such command" in result.output
