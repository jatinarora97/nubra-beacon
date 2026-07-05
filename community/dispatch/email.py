"""Email channel — Gmail SMTP (app password). Config-gated: creds unset → skip.

Markdown → simple HTML (headings/bold/links/lists — enough for a readable
email; the archive .md is the canonical artifact).
"""
from __future__ import annotations

import os
import re
import smtplib
from email.mime.text import MIMEText

from community.config.settings import settings


def _creds() -> tuple[str | None, str | None, list[str]]:
    d = settings.registry["delivery"]
    sender = os.getenv(d.get("gmail_sender_env", "GMAIL_SENDER"))
    password = os.getenv(d.get("gmail_app_password_env", "GMAIL_APP_PASSWORD"))
    recipients = d.get("email_recipients") or []
    return sender or None, password or None, recipients


def _to_html(md: str) -> str:
    lines = []
    for raw in md.splitlines():
        line = raw
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', line)
        m = re.match(r"^(#{1,6})\s*(.+)$", line)
        if m:
            lvl = min(len(m.group(1)) + 1, 4)  # h1 → h2 … keep email-modest
            lines.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
            continue
        if line.startswith("> "):
            lines.append(f"<div style='border-left:3px solid #f90;padding-left:8px;color:#555'>{line[2:]}</div>")
            continue
        if line.startswith("- "):
            lines.append(f"&bull; {line[2:]}<br>")
            continue
        if line.strip() in ("---", "___"):
            lines.append("<hr>")
            continue
        lines.append(f"{line}<br>" if line.strip() else "<br>")
    return ("<html><body style='font-family:-apple-system,Segoe UI,sans-serif;"
            "max-width:720px;color:#1a1a2e'>" + "\n".join(lines) + "</body></html>")


def send(markdown: str, subject: str) -> str:
    """Returns 'sent' | 'skipped (no creds)' | 'skipped (no recipients)' | 'error: …'."""
    sender, password, recipients = _creds()
    if not sender or not password:
        return "skipped (no creds)"
    if not recipients:
        return "skipped (no recipients)"
    try:
        msg = MIMEText(_to_html(markdown), "html")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
            smtp.login(sender, password)
            smtp.sendmail(sender, recipients, msg.as_string())
        return "sent"
    except Exception as e:  # noqa: BLE001 — a channel failure never kills dispatch
        return f"error: {type(e).__name__}: {str(e)[:120]}"
