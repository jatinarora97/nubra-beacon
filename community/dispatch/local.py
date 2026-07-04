"""Dispatch — archive channel: renders + writes messages to out/messages/.

Slack + Gmail senders live beside this module (slack.py / email.py) and are
config-gated; the archive copy is ALWAYS written regardless of channels.
"""
from __future__ import annotations

from community.compose import render


def run(all_stats: dict | None = None) -> dict:
    paths = render.write_local_messages(all_stats or {})
    return {"written": [str(p) for p in paths]}
