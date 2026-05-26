"""Tests for M10: NotificationDispatcher — webhook and Telegram providers."""

import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch


def _dispatcher(**env):
    """Build a dispatcher with controlled env vars."""
    import os
    from secureflow.notifications import NotificationDispatcher

    with patch.dict(os.environ, env, clear=False):
        return NotificationDispatcher()


def test_dispatcher_instantiates():
    from secureflow.notifications import NotificationDispatcher
    d = NotificationDispatcher()
    assert hasattr(d, "dispatch")


def test_dispatch_no_providers_is_silent():
    """With no env vars set, dispatch must not raise."""
    import os
    from secureflow.notifications import NotificationDispatcher

    keys = ["WEBHOOK_URL", "WEBHOOK_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    env_patch = {k: "" for k in keys}
    with patch.dict(os.environ, env_patch):
        d = NotificationDispatcher()
        d.dispatch("scan_complete", "target.test", "success")  # must not raise


def test_webhook_called_when_url_set():
    """webhook POST is made when WEBHOOK_URL is set."""
    import os

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.dict(os.environ, {"WEBHOOK_URL": "http://hook.test/post", "WEBHOOK_SECRET": ""}):
        with patch("secureflow.notifications.requests.post", return_value=mock_resp) as mock_post:
            from secureflow.notifications import NotificationDispatcher
            d = NotificationDispatcher()
            d.dispatch("scan_complete", "192.168.1.1", "success", summary="ports found")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs[0][0] == "http://hook.test/post"


def test_webhook_payload_schema():
    """Webhook body must contain required keys."""
    import os

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.dict(os.environ, {"WEBHOOK_URL": "http://hook.test/post", "WEBHOOK_SECRET": ""}):
        with patch("secureflow.notifications.requests.post", return_value=mock_resp) as mock_post:
            from secureflow.notifications import NotificationDispatcher
            NotificationDispatcher().dispatch("scan_complete", "host.local", "success", "summary", "/tmp/r.pdf")

    body = json.loads(mock_post.call_args[1]["data"])
    for key in ("event", "target", "status", "summary", "report_path", "timestamp", "tool"):
        assert key in body, f"Missing key: {key}"
    assert body["event"] == "scan_complete"
    assert body["target"] == "host.local"


def test_webhook_hmac_signature():
    """When WEBHOOK_SECRET is set, X-SecureFlow-Signature header must be valid HMAC-SHA256."""
    import os

    secret = "supersecret123"
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch.dict(os.environ, {"WEBHOOK_URL": "http://hook.test/post", "WEBHOOK_SECRET": secret}):
        with patch("secureflow.notifications.requests.post", return_value=mock_resp) as mock_post:
            from secureflow.notifications import NotificationDispatcher
            NotificationDispatcher().dispatch("scan_complete", "host.local", "success")

    call_kwargs = mock_post.call_args[1]
    body = call_kwargs["data"]
    headers = call_kwargs["headers"]

    expected_sig = "sha256=" + hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    assert headers["X-SecureFlow-Signature"] == expected_sig


def test_telegram_called_when_configured():
    """Telegram POST is made when token + chat_id are set."""
    import os

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    env = {
        "WEBHOOK_URL": "",
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "TELEGRAM_CHAT_ID": "456",
    }
    with patch.dict(os.environ, env):
        with patch("secureflow.notifications.requests.post", return_value=mock_resp) as mock_post:
            from secureflow.notifications import NotificationDispatcher
            NotificationDispatcher().dispatch("scan_complete", "host.local", "success")

    mock_post.assert_called_once()
    url = mock_post.call_args[0][0]
    assert "api.telegram.org" in url
    assert "123:ABC" in url


def test_webhook_network_error_does_not_raise():
    """Network failure in webhook must be swallowed (logged only)."""
    import os
    import requests as req

    with patch.dict(os.environ, {"WEBHOOK_URL": "http://dead.host/post", "WEBHOOK_SECRET": ""}):
        with patch("secureflow.notifications.requests.post", side_effect=req.exceptions.ConnectionError("down")):
            from secureflow.notifications import NotificationDispatcher
            d = NotificationDispatcher()
            d.dispatch("scan_complete", "host", "success")  # must not raise


def test_orchestrator_calls_dispatcher_on_success():
    """CrewOrchestrator must trigger NotificationDispatcher after a successful scan."""
    from unittest.mock import patch, MagicMock

    mock_crew = MagicMock()
    mock_crew.kickoff.return_value = MagicMock(raw_output="report text")

    with patch("secureflow.crew.orchestrator.create_crew", return_value=mock_crew):
        with patch("secureflow.notifications.NotificationDispatcher.dispatch") as mock_dispatch:
            from secureflow.crew.orchestrator import CrewOrchestrator
            orch = CrewOrchestrator()
            orch.run_security_crew("test.host")

    mock_dispatch.assert_called_once()
    call_kwargs = mock_dispatch.call_args[1]
    assert call_kwargs["event"] == "scan_complete"
    assert call_kwargs["status"] == "success"
