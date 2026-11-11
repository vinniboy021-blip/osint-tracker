"""Optional internal, SMTP and signed webhook notifications."""

from __future__ import annotations

import email.utils
import hashlib
import hmac
import json
import re
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx
import httpcore

from app.config import settings
from app.connectors.security import PublicNetworkBackend, validate_public_url

_EMAIL_RE = re.compile(r"^[^@\s]{1,254}@[^@\s]+\.[^@\s]+$")


def _validate_recipient(recipient: str) -> str:
    """Reject addresses that could cause SMTP header injection or are malformed."""
    stripped = recipient.strip()
    if not stripped:
        return ""
    if "\n" in stripped or "\r" in stripped or len(stripped) > 320:
        raise ValueError("Endereço de e-mail inválido")
    if not _EMAIL_RE.match(stripped):
        raise ValueError("Endereço de e-mail inválido")
    return stripped


def _webhook_client() -> httpx.Client:
    """httpx client with DNS-pinned transport — mirrors connector SSRF protection."""
    transport = httpx.HTTPTransport(retries=0, trust_env=False)
    transport._pool._network_backend = PublicNetworkBackend()
    return httpx.Client(
        transport=transport,
        timeout=10,
        follow_redirects=False,
        trust_env=False,
    )


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
        address = _validate_recipient(recipient)
        if not address:
            raise ValueError("Endereço de e-mail inválido")
        message = EmailMessage()
        message["Subject"] = f"OSINT Tracker: {alert.title}"
        message["From"] = settings.smtp_from
        message["To"] = address
        message.set_content(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        results["email"] = "sent"
    if settings.alert_webhook_url:
        # Webhook destinations are deployment configuration, but still validate them
        # before opening a server-side request to prevent accidental SSRF through a
        # compromised or misconfigured environment. DNS-pinned transport prevents
        # rebinding attacks even when the URL passes static validation.
        validate_public_url(settings.alert_webhook_url)
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode()
        signature = hmac.HMAC(settings.alert_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        with _webhook_client() as client:
            response = client.post(
                settings.alert_webhook_url,
                content=body,
                headers={"Content-Type": "application/json", "X-OSINT-Signature": f"sha256={signature}"},
            )
        response.raise_for_status()
        results["webhook"] = "sent"
    return results
