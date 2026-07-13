"""
Notification transport module for CertOps.
Handles delivery of expiry warnings via Webhook and SMTP transports.
"""
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import requests

logger = logging.getLogger("certops.notifier")


def dispatch_webhook(url: str, payload: dict[str, Any], timeout: int = 5) -> bool:
    """
    Deliver notification payload via HTTP POST Webhook.
    Raises RuntimeError on non-2xx response or connection failure.
    """
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        logger.info("Webhook notification delivered to %s (HTTP %s)", url, response.status_code)
        return True
    except Exception as exc:
        logger.error("Failed to deliver webhook notification to %s: %s", url, exc)
        raise RuntimeError(f"Webhook delivery failed to {url}: {exc}") from exc


def dispatch_smtp(
    host: str,
    port: int,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    username: str | None = None,
    password: str | None = None,
    use_tls: bool = True,
) -> bool:
    """
    Deliver notification via SMTP.
    Raises RuntimeError on connection or authentication failure.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=10)
        else:
            server = smtplib.SMTP(host, port, timeout=10)
            if use_tls:
                server.starttls()
        with server:
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        logger.info("SMTP notification delivered to %s via %s:%s", recipient, host, port)
        return True
    except Exception as exc:
        logger.error("Failed to deliver SMTP notification to %s: %s", recipient, exc)
        raise RuntimeError(f"SMTP delivery failed to {host}:{port}: {exc}") from exc


def dispatch_notification(
    cert_name: str,
    vault_source: str,
    remaining_days: float,
    threshold_days: float,
) -> dict[str, bool]:
    """
    Unified notification dispatcher checking environment for configured transports.
    Delivers to all configured transports (WEBHOOK_URL, SMTP_HOST).
    Raises on delivery failure so notification_log is not prematurely updated.
    """
    webhook_url = os.getenv("WEBHOOK_URL")
    smtp_host = os.getenv("SMTP_HOST")

    payload = {
        "event": "certificate_expiry_warning",
        "cert_name": cert_name,
        "vault_source": vault_source,
        "remaining_days": remaining_days,
        "threshold_days": threshold_days,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    results = {"webhook": False, "smtp": False}

    if webhook_url:
        results["webhook"] = dispatch_webhook(webhook_url, payload)

    if smtp_host:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        sender = os.getenv("SMTP_SENDER", "certops@localhost")
        recipient = os.getenv("SMTP_RECIPIENT", "admin@localhost")
        username = os.getenv("SMTP_USER")
        password = os.getenv("SMTP_PASSWORD")
        use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")

        subject = f"[CertOps Warning] Certificate '{cert_name}' expiring in {remaining_days:.2f} days"
        body = (
            f"Certificate Expiry Warning\n\n"
            f"Certificate: {cert_name}\n"
            f"Source: {vault_source}\n"
            f"Remaining Lifetime: {remaining_days:.2f} days\n"
            f"Policy Threshold: {threshold_days} days\n\n"
            f"CertOps auto-renewal or operator attention required."
        )
        results["smtp"] = dispatch_smtp(
            host=smtp_host,
            port=smtp_port,
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            username=username,
            password=password,
            use_tls=use_tls,
        )

    return results
