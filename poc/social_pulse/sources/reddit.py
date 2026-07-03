"""Reddit adapter — fetches via the vendored git scraper (Playwright + old.reddit.com).

No Reddit API credentials needed: the git core extraction drives a real headless
browser against old.reddit.com, which bypasses the API/IP block. We run it in a
subprocess (see _reddit_fetch.py) and map its post dicts into our RawItem contract.
Each post AND each top-level comment becomes its own RawItem.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..schema import RawItem

ROOT = Path(__file__).resolve().parents[2]
WORKER = ["-m", "social_pulse.sources._reddit_fetch"]

# Curated Indian-market communities, grouped so the UI can offer checkboxes by theme.
# The scraper hits old.reddit.com/r/<sub> and is resilient to dead/empty subs, so a
# brand community that doesn't exist just yields nothing rather than crashing the run.
SUB_GROUPS: dict[str, list[str]] = {
    "F&O / Options": [
        "IndianStreetBets", "NSEbets", "IndiaOptionsSelling",
        "IndianStockMarket", "OptionsTrading", "options",
    ],
    "Algo / Dev / API": [
        "IndiaAlgoTrading", "algotrading", "Daytrading", "quant",
    ],
    "Investing / Stocks": [
        "IndiaInvestments", "DalalStreetTalks", "StockMarketIndia",
        "IndianStockMarketLive", "SecurityAnalysis",
    ],
    "Brokers / Platforms": [
        "Zerodha", "dhanhq", "smallcase", "Upstox", "groww",
    ],
    "Macro / Personal finance": [
        "IndianFinance", "personalfinanceindia", "IndianEconomy",
    ],
}

# Flat default selection — the high-signal core (kept small; live scrape is slow).
DEFAULT_SUBS = [
    "IndiaInvestments", "IndianStreetBets", "IndianStockMarket",
    "IndiaAlgoTrading", "DalalStreetTalks", "NSEbets", "IndiaOptionsSelling",
]

# Everything we know about, de-duplicated, preserving group order.
ALL_SUBS = list(dict.fromkeys(s for subs in SUB_GROUPS.values() for s in subs))


def _ts(unix_seconds) -> datetime:
    try:
        return datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _to_items(scraped: dict, days: int | None = None) -> list[RawItem]:
    items: list[RawItem] = []
    cutoff = None
    if days and days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for sub, posts in (scraped or {}).items():
        srname = f"r/{sub}"
        for p in posts:
            created = _ts(p.get("timestamp"))
            # last-N-days window: drop stale posts (and their comments, which inherit
            # the post time on old.reddit). Posts with no usable timestamp are kept.
            if cutoff is not None and p.get("timestamp") and created < cutoff:
                continue
            permalink = p.get("permalink") or ""
            title = p.get("title") or ""
            selftext = p.get("selftext") or ""
            text = (title + ("\n" + selftext if selftext else "")).strip()
            items.append(RawItem(
                source="reddit",
                source_type="post",
                external_id=p.get("id") or permalink,
                text=text,
                author=p.get("author") or "[deleted]",
                url=permalink,
                created_at=created,
                engagement={"score": p.get("score") or 0,
                            "replies": p.get("num_comments") or 0,
                            "upvote_ratio": None},
                raw={"subreddit": srname, "listing": p.get("sort_type"),
                     "permalink": permalink, "flair": p.get("flair"),
                     "post_type": p.get("post_type"),
                     "image_urls": p.get("image_urls") or [],
                     "external_url": p.get("url"), "title": title},
            ))
            # each top-level comment → its own item (this is where strategy/API talk lives)
            for i, c in enumerate(p.get("comments") or []):
                body = (c.get("body") or "").strip()
                if not body:
                    continue
                items.append(RawItem(
                    source="reddit",
                    source_type="comment",
                    external_id=f"{p.get('id')}:c{i}",
                    text=body,
                    author=c.get("author") or "[deleted]",
                    url=permalink,                      # old-reddit comment perma not exposed; use post link
                    created_at=created,                 # comment ts not captured; inherit post time
                    engagement={"score": c.get("score") or 0, "replies": 0, "upvote_ratio": None},
                    raw={"subreddit": srname, "post_id": p.get("id"),
                         "post_title": title, "permalink": permalink},
                ))
    return items


def fetch_reddit(cfg: dict) -> list[RawItem]:
    rc = cfg.get("reddit", {})
    days = int(rc.get("days", 0) or 0)
    payload = {
        "subreddits": rc.get("subreddits") or DEFAULT_SUBS,
        "listings": rc.get("listings") or ["hot", "rising", "new"],
        "posts_per": int(rc.get("limit_per_listing", 15)),
        "comments_per": int(rc.get("comment_limit", 15)),
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        out_path = f.name
    try:
        proc = subprocess.run(
            [sys.executable, *WORKER, json.dumps(payload), out_path],
            cwd=str(ROOT), capture_output=True, text=True, timeout=1800,
        )
        if proc.returncode != 0:
            raise SystemExit(f"Reddit scrape failed (exit {proc.returncode}):\n"
                             f"{proc.stderr[-2000:]}")
        scraped = json.loads(Path(out_path).read_text())
    finally:
        try:
            os.unlink(out_path)
        except OSError:
            pass
    return _to_items(scraped, days=days)
