"""Notification dispatcher — webhook (generic) and Telegram providers."""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)


def _build_payload(
    event: str,
    target: str,
    status: str,
    summary: str = "",
    report_path: str = "",
) -> Dict[str, Any]:
    return {
        "event": event,
        "target": target,
        "status": status,
        "summary": summary[:500],
        "report_path": report_path,
        "timestamp": datetime.now().isoformat(),
        "tool": "SecureFlow AI",
    }


class NotificationDispatcher:
    """Send post-scan notifications to configured providers."""

    def __init__(self):
        self.webhook_url = os.getenv("WEBHOOK_URL", "")
        self.webhook_secret = os.getenv("WEBHOOK_SECRET", "")
        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def dispatch(
        self,
        event: str,
        target: str,
        status: str,
        summary: str = "",
        report_path: str = "",
    ) -> None:
        """Fire all configured providers. Errors are logged, never raised."""
        payload = _build_payload(event, target, status, summary, report_path)

        if self.webhook_url:
            self._send_webhook(payload)

        if self.telegram_token and self.telegram_chat_id:
            self._send_telegram(payload)

    # ------------------------------------------------------------------
    # Providers
    # ------------------------------------------------------------------

    def _send_webhook(self, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False)
        headers = {"Content-Type": "application/json"}

        if self.webhook_secret:
            sig = hmac.new(
                self.webhook_secret.encode(),
                body.encode(),
                hashlib.sha256,
            ).hexdigest()
            headers["X-SecureFlow-Signature"] = f"sha256={sig}"

        try:
            resp = requests.post(self.webhook_url, data=body, headers=headers, timeout=5)
            if resp.status_code < 300:
                logger.info(f"Webhook delivered → {self.webhook_url} ({resp.status_code})")
            else:
                logger.warning(f"Webhook non-2xx: {resp.status_code} from {self.webhook_url}")
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Webhook delivery failed: {exc}")

    def _send_telegram(self, payload: Dict[str, Any]) -> None:
        text = (
            f"🤖 *SecureFlow* — {payload['event']}\n"
            f"Target: `{payload['target']}`\n"
            f"Status: {payload['status']}\n"
            f"Time: {payload['timestamp']}"
        )
        if payload.get("summary"):
            text += f"\n\n_{payload['summary'][:200]}_"

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        try:
            resp = requests.post(
                url,
                json={"chat_id": self.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=5,
            )
            if resp.status_code == 200:
                logger.info("Telegram notification sent")
            else:
                logger.warning(f"Telegram notification failed: {resp.status_code}")
        except requests.exceptions.RequestException as exc:
            logger.warning(f"Telegram delivery failed: {exc}")
