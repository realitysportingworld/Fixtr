"""
Outgoing email. EMAIL_BACKEND=console (the default) writes messages to the
log, which is all development needs; EMAIL_BACKEND=smtp sends them through
any SMTP provider (Amazon SES, Postmark, SendGrid, Mailgun, Gmail...).

Callers send from a background task, so a slow mail server never slows a
request and response times don't reveal whether an address has an account.
"""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger("fixtr.email")

# Tests read what would have been sent from here
outbox: list[EmailMessage] = []


def _message(to: str, subject: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def send_email(to: str, subject: str, body: str) -> None:
    msg = _message(to, subject, body)
    if settings.EMAIL_BACKEND == "console":
        outbox.append(msg)
        logger.warning("Email (console backend, not sent)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return
    try:
        context = ssl.create_default_context()
        if settings.SMTP_STARTTLS:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                smtp.starttls(context=context)
                if settings.SMTP_USERNAME:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15, context=context) as smtp:
                if settings.SMTP_USERNAME:
                    smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD or "")
                smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        # Never surface mail errors to the client; the user can ask again
        logger.exception("Sending email to %s failed", to)
