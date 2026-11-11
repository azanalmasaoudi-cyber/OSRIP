"""Transactional e-mail for account actions the user requested (never unsolicited).

Backends (``OSRIP_EMAIL_BACKEND``):
* ``outbox``: development sink. The message is stored in ``email_outbox`` and is
  readable only through the development endpoint; nothing leaves the machine.
* ``smtp``: delivery through the configured SMTP server (STARTTLS by default). The
  body is not stored.
* ``disabled``: no e-mail; features that depend on it report themselves unavailable.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import EmailOutbox
from app.services import monitoring

logger = logging.getLogger("osrip.mail")


def delivery_mode() -> str:
    s = get_settings()
    if s.email_backend == "smtp" and s.smtp_host and s.smtp_from:
        return "smtp"
    if s.email_backend == "outbox":
        return "outbox"
    return "disabled"


def require_delivery() -> None:
    if delivery_mode() == "disabled":
        raise ApiError(
            503,
            "email_not_configured",
            "E-mail delivery is not configured on this server, so this action is unavailable.",
        )


def send(
    session: Session, *, to: str, subject: str, body: str, purpose: str, html: str | None = None
) -> None:
    """Send (or, in development, store) one message inside the caller's transaction. With
    ``html``, SMTP sends a multipart message (plain text first, HTML alternative); the
    development outbox keeps the plain text."""
    mode = delivery_mode()
    if mode == "outbox":
        session.add(EmailOutbox(to_address=to, subject=subject, body_text=body, purpose=purpose))
        return
    if mode == "smtp":
        s = get_settings()
        message = EmailMessage()
        message["From"] = s.smtp_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(s.smtp_host or "", s.smtp_port, timeout=15) as smtp:
                if s.smtp_starttls:
                    smtp.starttls()
                if s.smtp_username and s.smtp_password:
                    smtp.login(s.smtp_username, s.smtp_password.get_secret_value())
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.error("smtp delivery failed: %s", type(exc).__name__)
            monitoring.external_failure("smtp", type(exc).__name__)
            raise ApiError(
                503, "email_delivery_failed", "The e-mail could not be sent. Try again later."
            ) from exc
        return
    require_delivery()
