"""Slack channel — incoming-webhook sender. Config-gated: env unset → clean skip.

Our markdown is converted to Slack mrkdwn (headings → bold lines, links bare)
and chunked under Slack's message ceiling.
"""
from __future__ import annotations

import os
import re

import httpx

from community.config.settings import settings

_CHUNK = 35_000  # Slack rejects ~40k; stay under with headroom


def _webhook() -> str | None:
    env_key = settings.registry["delivery"].get("slack_webhook_env", "SLACK_WEBHOOK_URL")
    return os.getenv(env_key) or None


def _to_mrkdwn(md: str) -> str:
    out = []
    for line in md.splitlines():
        line = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", line)          # headings → bold
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)            # **bold** → *bold*
        line = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", line)  # links
        line = re.sub(r"^_(.+)_$", r"_\1_", line)                 # italics pass through
        out.append(line)
    return "\n".join(out)


def _chunks(text: str) -> list[str]:
    if len(text) <= _CHUNK:
        return [text]
    parts, current = [], []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > _CHUNK and current:
            parts.append("".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line)
    if current:
        parts.append("".join(current))
    return parts


def send(markdown: str, subject: str) -> str:
    """Returns 'sent' | 'skipped (no creds)' | 'skipped (local mode)' | 'error: …'."""
    from community.config.settings import settings
    if settings.mode != "prod":  # dump-restored laptops must never message the team
        return "skipped (local mode — archive only)"
    url = _webhook()
    if not url:
        return "skipped (no creds)"
    try:
        body = _to_mrkdwn(markdown)
        for i, chunk in enumerate(_chunks(body)):
            payload = {"text": chunk if i else f"*{subject}*\n{chunk}"}
            r = httpx.post(url, json=payload, timeout=15.0)
            r.raise_for_status()
        return "sent"
    except Exception as e:  # noqa: BLE001 — a channel failure never kills dispatch
        return f"error: {type(e).__name__}: {str(e)[:120]}"
