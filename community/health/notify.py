# community/health/notify.py
"""Alert text and delivery. Each message leads with an icon from icons.py (Slack-only
emoji, user decision 2026-10-09) and keeps its plain [TAG].

Delivery goes through dispatch/slack.send (prod-only gate lives there) to the
dedicated alerts webhook. The default delivery webhook carries SSO access
approvals, so there is no fallback to it unless `fallback_to_default_webhook`.
"""
from __future__ import annotations

import os
from datetime import datetime

from community.dispatch import slack
from community.health import icons
from community.health.model import Result


def _dur(hours: float) -> str:
    if hours < 1:
        return f"{max(round(hours * 60), 1)} min"  # round: 40 min is 39.999... after float division
    if hours < 48:
        return f"{hours:.0f} h"
    return f"{hours / 24:.0f} d"


def fmt_alert(res: Result) -> str:
    text = f"{icons.CRITICAL} [CRITICAL] {res.key}: {res.detail}"
    return text + (f"\n    What to check: {res.hint}" if res.hint else "")


def fmt_remind(res: Result, since: datetime, now: datetime) -> str:
    hours = (now - since).total_seconds() / 3600
    return f"{icons.REMINDER} [CRITICAL, still failing] {res.key}: {res.detail} (for {_dur(hours)})"


def fmt_resolved(key: str, since: datetime, now: datetime) -> str:
    hours = (now - since).total_seconds() / 3600
    return f"{icons.OK} [RESOLVED] {key} (was critical for {_dur(hours)})"


def post(text: str, subject: str, cfg: dict, dry_run: bool = False) -> str:
    if dry_run:
        return "dry-run"
    env = cfg["slack_webhook_env"]
    if os.getenv(env):
        return slack.send(text, subject, webhook_env=env)
    if cfg["fallback_to_default_webhook"]:
        return slack.send(text, subject)
    return "skipped (no alerts webhook)"
