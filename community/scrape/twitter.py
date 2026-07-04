"""X / Twitter adapter: CSV backfill (primary local source) + capped live fetch.

Live fetch uses twitterapi.io advanced_search (ported from poc/social_pulse/sources/
twitter.py) but is HARD-CAPPED via registry `x_live_cap` — API credits are scarce
(user decision 2026-07-03); any failure degrades to a note, never an exception.
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import httpx

from community.config.settings import settings
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score

ENDPOINT = "https://api.twitterapi.io/twitter/tweet/advanced_search"


# ── CSV backfill ──────────────────────────────────────────────────────────

def _int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def iter_csv_backfill(path: str | Path) -> Iterator[SocialItem]:
    p = Path(path)
    if not p.exists():
        return
    with open(p, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            text = (row.get("text") or "").strip()
            if not text:
                continue
            try:
                created = datetime.fromisoformat(row["created_at"])
            except Exception:
                created = datetime.now(timezone.utc)
            raw = {}
            try:
                raw = json.loads(row.get("raw_json") or "{}")
            except Exception:
                pass
            likes = _int(row.get("likes"))
            replies = _int(row.get("replies"))
            shares = _int(row.get("retweets")) + _int(row.get("quotes"))
            yield SocialItem(
                source="twitter",
                source_type="reply" if row.get("source_type") == "reply" else "tweet",
                external_id=str(row["external_id"]),
                parent_id=None,  # CSV doesn't carry inReplyToId
                thread_id=str(raw.get("conversation_id") or row["external_id"]),
                author=(row.get("author") or "[unknown]").lstrip("@"),
                author_meta=AuthorMeta(
                    followers=_int(row.get("followers")) or None,
                    verified=str(row.get("verified")).lower() == "true",
                ),
                text=text,
                lang=row.get("lang") or None,
                url=row.get("url") or f"https://x.com/i/status/{row['external_id']}",
                created_at=created,
                engagement=Engagement(
                    score=unified_score(likes, shares, replies),
                    native={
                        "likes": likes, "replies": replies,
                        "retweets": _int(row.get("retweets")),
                        "quotes": _int(row.get("quotes")),
                        "views": _int(row.get("views")),
                    },
                ),
                raw={**raw, "backfill": "twitter_pulse.csv"},
            )


# ── Live fetch (capped) ───────────────────────────────────────────────────

def _live_item(t: dict, query: str) -> SocialItem | None:
    text = (t.get("text") or "").strip()
    if not text:
        return None
    author = t.get("author") or {}
    likes = t.get("likeCount") or 0
    replies = t.get("replyCount") or 0
    shares = (t.get("retweetCount") or 0) + (t.get("quoteCount") or 0)
    try:
        created = datetime.strptime(t.get("createdAt") or "", "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        created = datetime.now(timezone.utc)
    return SocialItem(
        source="twitter",
        source_type="reply" if t.get("isReply") else "tweet",
        external_id=str(t.get("id")),
        parent_id=str(t["inReplyToId"]) if t.get("inReplyToId") else None,
        thread_id=str(t.get("conversationId") or t.get("id")),
        author=(author.get("userName") or "[unknown]").lstrip("@"),
        author_meta=AuthorMeta(
            followers=author.get("followers"),
            verified=bool(author.get("isBlueVerified") or author.get("isVerified")),
        ),
        text=text,
        lang=t.get("lang"),
        url=t.get("url") or t.get("twitterUrl") or f"https://x.com/i/status/{t.get('id')}",
        created_at=created.astimezone(timezone.utc),
        engagement=Engagement(
            score=unified_score(likes, shares, replies),
            native={"likes": likes, "replies": replies,
                    "retweets": t.get("retweetCount") or 0,
                    "quotes": t.get("quoteCount") or 0,
                    "views": t.get("viewCount") or 0},
        ),
        raw={"channel": "x", "query": query, "conversation_id": t.get("conversationId"),
             "live": True},
    )


def fetch_live_capped() -> tuple[list[SocialItem], str]:
    """Try a live fetch, stop at x_live_cap items. Never raises: returns (items, note)."""
    reg = settings.registry.get("sources", {}).get("twitter", {})
    cap = int(reg.get("x_live_cap", 10))
    if not reg.get("live_fetch", False):
        return [], "X live fetch disabled in registry — X data via CSV backfill only"
    if not settings.twitterapi_key:
        return [], "X live fetch skipped: TWITTERAPI_IO_KEY not set — X data via CSV backfill only"

    since = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
    queries = [f"{q} since:{since}" for q in reg.get("queries", [])]
    items: list[SocialItem] = []
    try:
        with httpx.Client(timeout=20.0,
                          headers={"X-API-Key": settings.twitterapi_key}) as client:
            for q in queries:
                if len(items) >= cap:
                    break
                r = client.get(ENDPOINT, params={"query": q, "queryType": "Latest"})
                r.raise_for_status()
                for t in r.json().get("tweets") or []:
                    it = _live_item(t, q)
                    if it is not None:
                        items.append(it)
                    if len(items) >= cap:
                        break
                time.sleep(1.0)
        note = (f"X live fetch capped at {cap} by config — API credits scarce; "
                f"got {len(items)} live tweets; main X data via CSV backfill")
    except Exception as e:  # noqa: BLE001 — any live failure degrades to a note
        note = (f"X live fetch unavailable ({type(e).__name__}: {str(e)[:120]}) — "
                f"X data via CSV backfill only")
    return items, note
