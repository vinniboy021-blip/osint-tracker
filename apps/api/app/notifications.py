"""Optional internal, SMTP and signed webhook notifications."""

from __future__ import annotations

import hashlib
import hmac
import json
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx

from app.config import settings


def deliver(alert: Any, recipient: str = "") -> dict[str, Any]:
    payload = {
        "id": alert.id,
        "investigation_id": alert.investigation_id,
        "event_type": alert.event_type,
        "title": alert.title,
        "details": alert.details,
    }
    results: dict[str, Any] = {"internal": True}
    if settings.smtp_host and recipient:
        message = EmailMessage()
        message["Subject"] = f"OSINT Tracker: {alert.title}"
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message.set_content(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        results["email"] = "sent"
    if settings.alert_webhook_url:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        signature = hmac.new(settings.alert_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        response = httpx.post(
            settings.alert_webhook_url,
            content=body,
            headers={"Content-Type": "application/json", "X-OSINT-Signature": f"sha256={signature}"},
            timeout=10,
            follow_redirects=False,
            trust_env=False,
        )
        response.raise_for_status()
        results["webhook"] = "sent"
    return results
