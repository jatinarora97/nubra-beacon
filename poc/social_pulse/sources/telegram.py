"""Telegram adapter via Telethon (MTProto user session).

Env: TG_API_ID, TG_API_HASH  (get from https://my.telegram.org)
First run prompts for phone + login code; session cached in tg.session.

ToS NOTE: read PUBLIC channels only. Use a dedicated number, throttle hard,
respect FloodWait. Do not scrape private groups you aren't legitimately in.
"""
from __future__ import annotations

import os
from datetime import timezone

from ..schema import RawItem


def fetch_telegram(cfg: dict) -> list[RawItem]:
    try:
        from telethon.sync import TelegramClient  # lazy import
    except ImportError:
        raise SystemExit("Telegram source needs Telethon: pip install telethon")

    api_id = os.environ.get("TG_API_ID")
    api_hash = os.environ.get("TG_API_HASH")
    if not (api_id and api_hash):
        raise SystemExit("Set TG_API_ID and TG_API_HASH (from my.telegram.org)")

    tc = cfg.get("telegram", {})
    channels = tc.get("channels", [])
    per_channel = int(tc.get("messages_per_channel", 100))
    if not channels:
        return []

    items: list[RawItem] = []
    with TelegramClient("tg", int(api_id), api_hash) as client:
        for ch in channels:
            for msg in client.iter_messages(ch, limit=per_channel):
                if not msg.message:
                    continue
                items.append(
                    RawItem(
                        source="telegram",
                        source_type="message",
                        external_id=f"{ch}:{msg.id}",
                        text=msg.message,
                        author=str(getattr(msg, "sender_id", "anon")),
                        url=None,
                        created_at=msg.date.astimezone(timezone.utc),
                        engagement={"score": getattr(msg, "views", 0) or 0,
                                    "replies": getattr(getattr(msg, "replies", None), "replies", 0) or 0},
                        raw={"channel": ch},
                    )
                )
    return items
