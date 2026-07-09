"""Reddit adapter — the vendored zanshash/reddit_scraper is the ONLY transport
(old.reddit via Playwright; verified working incl. on networks that 403 the
JSON API). The JSON-API fallback was removed by user decision 2026-07-05.

Runtime config (subreddits by category, posts/sub, comments/post, sorts) is
injected into the vendored module from registry.yaml — its config.py is
defaults only. Nested replies (one level, ≤3 per top comment) come from the
sync-script patch; see scripts/sync_reddit_scraper.py.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone

from community.config.settings import settings
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score


def _sub_categories(reg: dict) -> dict[str, str]:
    """{sub: category}. Source of truth = watch_sources (UI-managed; seeded from
    the registry by scripts/seed_sources.py) — new subs added in the UI join the
    NEXT scrape run automatically. Registry is the fallback when the table is
    empty/unavailable."""
    from community.store import db
    try:
        rows = db.query("SELECT value, category FROM watch_sources "
                        "WHERE kind='subreddit' AND active ORDER BY value")
        if rows:
            return {r["value"]: (r["category"] or "custom") for r in rows}
    except Exception:
        pass
    subs = reg.get("subreddits") or {}
    if isinstance(subs, list):  # backward compat
        return {s: "uncategorized" for s in subs}
    return {sub: cat for cat, lst in subs.items() for sub in lst}


def _comment_id(author: str, body: str) -> str:
    # DOM comments carry no reddit id — derive a stable one from content
    return hashlib.sha1(f"{author}|{body[:120]}".encode()).hexdigest()[:12]


def _preflight() -> bool:
    """One old.reddit listing page via httpx: True when it looks like a real
    listing (post links present), False when blocked/challenged/unreachable."""
    import httpx
    try:
        r = httpx.get("https://old.reddit.com/r/IndianStockMarket/new/",
                      headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"},
                      timeout=15.0, follow_redirects=True)
        return r.status_code == 200 and 'data-fullname="t3_' in r.text
    except Exception:  # noqa: BLE001 — unreachable network = don't crawl
        return False


def fetch_live(sorts: list[str] | None = None) -> tuple[list[SocialItem], list[str]]:
    """Fetch posts + comments (+ one level of replies) for every registry sub.
    Returns (items, health_notes) — a failing sub is a note, never an exception."""
    reg = settings.registry.get("sources", {}).get("reddit", {})
    cat_map = _sub_categories(reg)
    sorts = sorts or list(reg.get("sort_types_hourly", ["new"]))

    from community.lib import reddit_scraper as pkg
    from community.lib.reddit_scraper import scraper as zs

    # inject runtime config (module-level names bound at import time)
    zs.SUBREDDITS = list(cat_map)
    zs.POSTS_PER_FEED = int(reg.get("max_posts_per_sub", 10))
    zs.COMMENTS_PER_POST = int(reg.get("comments_per_post", 15))
    zs.SORT_TYPES = sorts
    zs.DOWNLOAD_IMAGES = False
    zs.HEADLESS = True
    zs.OUTPUT_DIR = str(settings.out_dir.parent / "reddit_scraper")
    from community.store import db
    zs.SKIP_IDS = {r["external_id"] for r in db.query(
        "SELECT external_id FROM social_items WHERE source='reddit' AND source_type='post'")}
    pkg.config.OUTPUT_DIR = zs.OUTPUT_DIR

    # Preflight (2026-07-09, prod incident): old.reddit serves block/challenge
    # pages to some datacenter IPs — every selector-wait then burns its full
    # timeout and a "fetch" grinds for hours before yielding nothing. One cheap
    # page decides in seconds whether crawling is worth it at all.
    if not _preflight():
        return [], ["reddit BLOCKED from this network (preflight page had no posts) "
                    "— crawl skipped; verify with: curl -sI -A Mozilla "
                    "https://old.reddit.com/r/IndianStockMarket/new/"]

    combined = asyncio.run(zs.run())

    items: list[SocialItem] = []
    health: list[str] = []
    for sub, posts in combined.items():
        cat = cat_map.get(sub, "uncategorized")
        if not posts:
            health.append(f"r/{sub}: 0 posts via scraper (dead/renamed/blocked?)")
        for p in posts:
            if not p.get("id") or p.get("author") in (None, "[deleted]"):
                continue
            text = " ".join(x for x in [(p.get("title") or "").strip(),
                                        (p.get("selftext") or "").strip()] if x)
            if not text:
                continue
            created = (datetime.fromtimestamp(p["timestamp"], tz=timezone.utc)
                       if p.get("timestamp") else datetime.now(timezone.utc))
            likes = int(p.get("score") or 0)
            n_comments = int(p.get("num_comments") or 0)
            base_raw = {"subreddit": sub, "category": cat, "via": "zanshash_scraper"}
            items.append(SocialItem(
                source="reddit", source_type="post",
                external_id=p["id"], parent_id=None, thread_id=p["id"],
                author=p["author"], author_meta=AuthorMeta(),
                text=text[:8000], lang=None,
                url=p.get("permalink") or f"https://www.reddit.com/r/{sub}",
                created_at=created,
                engagement=Engagement(score=unified_score(likes, 0, n_comments),
                                      native={"upvotes": likes, "comments": n_comments}),
                raw={**base_raw, "flair": p.get("flair"),
                     "post_type": p.get("post_type"), "sort_type": p.get("sort_type")},
            ))
            for c in p.get("comments") or []:
                body = (c.get("body") or "").strip()
                if not body or c.get("author") in (None, "[deleted]"):
                    continue
                cid = _comment_id(c["author"], body)
                c_ext = f"{p['id']}_c{cid}"
                c_likes = int(c.get("score") or 0)
                items.append(SocialItem(
                    source="reddit", source_type="comment",
                    external_id=c_ext, parent_id=p["id"], thread_id=p["id"],
                    author=c["author"], author_meta=AuthorMeta(),
                    text=body[:8000], lang=None,
                    url=p.get("permalink") or f"https://www.reddit.com/r/{sub}",
                    created_at=created,  # comment time not in DOM — post time approx
                    engagement=Engagement(score=unified_score(c_likes, 0, 0),
                                          native={"upvotes": c_likes}),
                    raw={**base_raw, "created_at_approx": True},
                ))
                for r in c.get("replies") or []:
                    r_body = (r.get("body") or "").strip()
                    if not r_body or r.get("author") in (None, "[deleted]"):
                        continue
                    rid = _comment_id(r["author"], r_body)
                    r_likes = int(r.get("score") or 0)
                    items.append(SocialItem(
                        source="reddit", source_type="comment",
                        external_id=f"{c_ext}_r{rid}",
                        parent_id=c_ext,           # linked to the PARENT COMMENT
                        thread_id=p["id"],
                        author=r["author"], author_meta=AuthorMeta(),
                        text=r_body[:8000], lang=None,
                        url=p.get("permalink") or f"https://www.reddit.com/r/{sub}",
                        created_at=created,
                        engagement=Engagement(score=unified_score(r_likes, 0, 0),
                                              native={"upvotes": r_likes}),
                        raw={**base_raw, "created_at_approx": True,
                             "nested_reply": True},
                    ))
    return items, health
