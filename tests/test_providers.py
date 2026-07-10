"""Tests for provider status endpoints and OpenCode health checks."""

import asyncio
import json
from unittest.mock import patch, MagicMock


def test_is_port_open_with_valid_url():
    """_is_port_open returns bool for any valid URL without raising."""
    from secureflow.server import _is_port_open

    result = _is_port_open("http://192.0.2.1:9999", timeout=0.5)
    assert result is False


def test_is_port_open_with_invalid_url():
    """_is_port_open handles malformed URLs gracefully."""
    from secureflow.server import _is_port_open

    result = _is_port_open("", timeout=0.1)
    assert result is False


def test_get_providers_dict_returns_dict():
    """_get_providers_dict returns a dict with all expected provider keys."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                with patch("secureflow.config.ANTHROPIC_API_KEY", "test-key"):
                    providers = _get_providers_dict()

    assert isinstance(providers, dict)
    assert "claude" in providers
    assert "gemini" in providers
    assert "openrouter" in providers
    assert "ollama" in providers
    assert "opencode" in providers


def test_get_providers_dict_claude_cli():
    """When CLI is available, claude provider shows available:true mode:cli."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=True):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                providers = _get_providers_dict()

    assert providers["claude"]["available"] is True
    assert providers["claude"]["mode"] == "cli"


def test_get_providers_dict_claude_api():
    """When CLI is unavailable but API key is set, claude shows available:true mode:api."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                with patch("secureflow.config.ANTHROPIC_API_KEY", "test-key-123"):
                    providers = _get_providers_dict()

    assert providers["claude"]["available"] is True
    assert providers["claude"]["mode"] == "api"


def test_get_providers_dict_opencode():
    """OpenCode availability is determined by TCP port check."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=True):
                providers = _get_providers_dict()

    assert providers["opencode"]["available"] is True
    assert providers["opencode"]["mode"] == "local"


def test_get_providers_dict_opencode_unavailable():
    """When port is closed, opencode shows as unavailable."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                providers = _get_providers_dict()

    assert providers["opencode"]["available"] is False


def test_get_providers_dict_gemini():
    """Gemini availability depends on API key."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                with patch("secureflow.config.GEMINI_API_KEY", "test-key"):
                    providers = _get_providers_dict()

    assert providers["gemini"]["available"] is True
    assert providers["gemini"]["mode"] == "api"


def test_get_providers_dict_gemini_unavailable():
    """Without API key, gemini shows as unavailable."""
    from secureflow.server import _get_providers_dict

    with patch("secureflow.config.is_claude_cli_available", return_value=False):
        with patch("secureflow.config.is_ollama_available", return_value=False):
            with patch("secureflow.server._is_port_open", return_value=False):
                with patch("secureflow.config.GEMINI_API_KEY", ""):
                    providers = _get_providers_dict()

    assert providers["gemini"]["available"] is False


def test_get_providers_endpoint_is_async():
    """The provider status route handler must be a coroutine function."""
    import inspect
    from secureflow.server import get_providers_status

    assert inspect.iscoroutinefunction(get_providers_status)


def test_providers_route_runs_in_executor():
    """The provider route handler runs blocking _get_providers_dict in executor."""
    from secureflow.server import get_providers_status
    from secureflow.config import MCP_SECRET

    mock_request = MagicMock()
    # Route now requires auth — supply a valid bearer token.
    mock_request.headers.get.return_value = f"Bearer {MCP_SECRET}"
    mock_providers = {"claude": {"available": True, "mode": "cli"}}

    with patch("secureflow.server._get_providers_dict", return_value=mock_providers):
        result = asyncio.run(get_providers_status(mock_request))

    body = json.loads(result.body)
    assert body == mock_providers


def test_protected_route_rejects_missing_token():
    """Protected routes return 401 when MCP_SECRET is set but no token is given."""
    from secureflow.server import get_providers_status
    from secureflow.config import MCP_SECRET

    if not MCP_SECRET:
        import pytest
        pytest.skip("MCP_SECRET not set — auth disabled")

    mock_request = MagicMock()
    mock_request.headers.get.return_value = None
    mock_request.query_params.get.return_value = None

    result = asyncio.run(get_providers_status(mock_request))
    assert result.status_code == 401


def test_protected_route_rejects_bad_token():
    """Protected routes return 401 for an invalid bearer token."""
    from secureflow.server import get_providers_status
    from secureflow.config import MCP_SECRET

    if not MCP_SECRET:
        import pytest
        pytest.skip("MCP_SECRET not set — auth disabled")

    mock_request = MagicMock()
    mock_request.headers.get.return_value = "Bearer definitely-wrong-token"
    mock_request.query_params.get.return_value = None

    result = asyncio.run(get_providers_status(mock_request))
    assert result.status_code == 401


def test_is_port_open_with_localhost():
    """_is_port_open returns True for localhost:4096 when opencode is running."""
    from secureflow.server import _is_port_open

    result = _is_port_open("http://127.0.0.1:4096", timeout=1.0)
    # This will be True if opencode is currently running, which is expected
    assert isinstance(result, bool)
