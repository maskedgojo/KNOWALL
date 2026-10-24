"""Send transactional emails without a queue, broker, or separate service.

Modes:
- console: local development only; prints the verification/reset link.
- smtp: production/staging delivery over TLS.
- memory: test-only, stores messages in app.extensions['knowall_outbox'].
"""
from email.message import EmailMessage
import smtplib
import ssl

from flask import current_app


def deliver_auth_email(*, to_address: str, subject: str, body: str) -> None:
    mode = current_app.config["MAIL_DELIVERY_MODE"].lower()
    if mode == "memory":
        if not current_app.testing:
            raise RuntimeError("Memory email mode is only available in tests")
        current_app.extensions.setdefault("knowall_outbox", []).append({
            "to": to_address, "subject": subject, "body": body,
        })
        return
    if mode == "console":
        if not current_app.debug and not current_app.testing:
            raise RuntimeError("Console email mode is restricted to development")
        # Local development only. The message contains a sensitive one-time link.
        current_app.logger.info("DEV ONLY email to %s: %s\n%s", to_address, subject, body)
        return
    if mode != "smtp":
        raise RuntimeError("MAIL_DELIVERY_MODE must be smtp, console or memory")

    host = current_app.config.get("SMTP_HOST")
    sender = current_app.config.get("MAIL_FROM")
    username = current_app.config.get("SMTP_USERNAME")
    password = current_app.config.get("SMTP_PASSWORD")
    port = int(current_app.config.get("SMTP_PORT", 587))
    security = current_app.config.get("SMTP_SECURITY", "starttls").lower()
    if not host or not sender:
        raise RuntimeError("SMTP_HOST and MAIL_FROM are required for SMTP")
    if security not in {"starttls", "ssl"}:
        raise RuntimeError("SMTP_SECURITY must be starttls or ssl")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, timeout=10, context=context) as smtp:
            if username:
                smtp.login(username, password or "")
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            if username:
                smtp.login(username, password or "")
            smtp.send_message(message)
