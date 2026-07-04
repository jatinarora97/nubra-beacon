"""Reddit adapter — primary: the vendored zanshash/reddit_scraper (old.reddit via
Playwright — verified working on networks that 403 the JSON API); fallback: the
public JSON endpoints (kept for networks where plain HTTP is fine and faster).

Runtime config (subreddits, posts/sub, comments/post, sort types) is injected
into the vendored module from registry.yaml — its own config.py is defaults only.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone

import httpx

from community.config.settings import settings
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score


def _scraper_fetch(subs: list[str], max_posts: int, comments_cap: int,
                   sorts: list[str]) -> tuple[list[SocialItem], list[str]]:
    """Primary transport: the vendored old.reddit Playwright scraper."""
    from community.lib import reddit_scraper as pkg
    from community.lib.reddit_scraper import scraper as zs

    # inject runtime config (module-level names bound at import time)
    zs.SUBREDDITS = subs
    zs.POSTS_PER_FEED = max_posts
    zs.COMMENTS_PER_POST = comments_cap
    zs.SORT_TYPES = sorts
    zs.DOWNLOAD_IMAGES = False
    zs.HEADLESS = True
    zs.OUTPUT_DIR = str(settings.out_dir.parent / "reddit_scraper")
    pkg.config.OUTPUT_DIR = zs.OUTPUT_DIR

    combined = asyncio.run(zs.run())

    items: list[SocialItem] = []
    health: list[str] = []
    for sub, posts in combined.items():
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
            replies = int(p.get("num_comments") or 0)
            items.append(SocialItem(
                source="reddit", source_type="post",
                external_id=p["id"], parent_id=None, thread_id=p["id"],
                author=p["author"], author_meta=AuthorMeta(),
                text=text[:8000], lang=None,
                url=p.get("permalink") or f"https://www.reddit.com/r/{sub}",
                created_at=created,
                engagement=Engagement(score=unified_score(likes, 0, replies),
                                      native={"upvotes": likes, "comments": replies}),
                raw={"subreddit": sub, "flair": p.get("flair"),
                     "post_type": p.get("post_type"), "via": "zanshash_scraper"},
            ))
            for c in p.get("comments") or []:
                body = (c.get("body") or "").strip()
                if not body or c.get("author") in (None, "[deleted]"):
                    continue
                # DOM comments carry no reddit id — derive a stable one from content
                cid = hashlib.sha1(
                    f"{c['author']}|{body[:120]}".encode()).hexdigest()[:12]
                c_likes = int(c.get("score") or 0)
                items.append(SocialItem(
                    source="reddit", source_type="comment",
                    external_id=f"{p['id']}_c{cid}",
                    parent_id=p["id"], thread_id=p["id"],
                    author=c["author"], author_meta=AuthorMeta(),
                    text=body[:8000], lang=None,
                    url=p.get("permalink") or f"https://www.reddit.com/r/{sub}",
                    created_at=created,  # comment time not in DOM — post time approx
                    engagement=Engagement(score=unified_score(c_likes, 0, 0),
                                          native={"upvotes": c_likes}),
                    raw={"subreddit": sub, "via": "zanshash_scraper",
                         "created_at_approx": True},
                ))
    return items, health

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
_SLEEP = 0.6
_pw_browser = None  # lazy singleton for the Playwright fallback


def _fetch_json_playwright(url: str) -> dict | list | None:
    """Fallback transport: fetch a JSON URL through headless Chromium."""
    global _pw_browser
    from playwright.sync_api import sync_playwright

    if _pw_browser is None:
        _pw = sync_playwright().start()
        _pw_browser = _pw.chromium.launch(headless=True)
    page = _pw_browser.new_page(user_agent=_UA)
    try:
        page.goto(url, timeout=20000)
        body = page.inner_text("body")
        return json.loads(body)
    finally:
        page.close()


def _fetch_json(client: httpx.Client, url: str):
    # Plain HTTP first; Chromium fallback on block OR an HTML body pretending to be 200.
    try:
        r = client.get(url)
        r.raise_for_status()
        return r.json()
    except Exception:  # noqa: BLE001 — includes 403/429 and JSON decode of block pages
        return _fetch_json_playwright(url)


def _post_item(d: dict, sub: str) -> SocialItem | None:
    text = " ".join(x for x in [(d.get("title") or "").strip(),
                                (d.get("selftext") or "").strip()] if x)
    if not text or d.get("author") in (None, "[deleted]"):
        return None
    likes = int(d.get("score") or 0)
    replies = int(d.get("num_comments") or 0)
    return SocialItem(
        source="reddit", source_type="post",
        external_id=d["name"],                       # t3_xxx
        parent_id=None, thread_id=d["name"],
        author=d["author"],
        author_meta=AuthorMeta(),                    # karma not in listing payload
        text=text[:8000],
        lang=None,
        url="https://www.reddit.com" + (d.get("permalink") or f"/r/{sub}"),
        created_at=datetime.fromtimestamp(d["created_utc"], tz=timezone.utc),
        engagement=Engagement(
            score=unified_score(likes, 0, replies),
            native={"upvotes": likes, "comments": replies},
        ),
        raw={"subreddit": sub, "flair": d.get("link_flair_text"),
             "upvote_ratio": d.get("upvote_ratio")},
    )


def _walk_comments(children: list, thread_id: str, sub: str, cap: int) -> list[SocialItem]:
    out: list[SocialItem] = []
    stack = list(children)
    while stack and len(out) < cap:
        node = stack.pop(0)
        if node.get("kind") != "t1":
            continue
        d = node.get("data") or {}
        body = (d.get("body") or "").strip()
        if body and d.get("author") not in (None, "[deleted]"):
            likes = int(d.get("score") or 0)
            out.append(SocialItem(
                source="reddit", source_type="comment",
                external_id=d["name"],               # t1_xxx
                parent_id=d.get("parent_id"),        # t3_ for top-level, t1_ nested
                thread_id=thread_id,
                author=d["author"],
                author_meta=AuthorMeta(),
                text=body[:8000],
                lang=None,
                url="https://www.reddit.com" + (d.get("permalink") or ""),
                created_at=datetime.fromtimestamp(d["created_utc"], tz=timezone.utc),
                engagement=Engagement(score=unified_score(likes, 0, 0),
                                      native={"upvotes": likes}),
                raw={"subreddit": sub},
            ))
        rep = d.get("replies")
        if isinstance(rep, dict):
            stack.extend(rep.get("data", {}).get("children") or [])
    return out


def fetch_live() -> tuple[list[SocialItem], list[str]]:
    """Fetch posts + comments for every registry subreddit.
    Returns (items, health_notes) — a failing sub is a note, never an exception."""
    reg = settings.registry.get("sources", {}).get("reddit", {})
    subs = reg.get("subreddits", [])
    max_posts = int(reg.get("max_posts_per_sub", 15))

    # ── primary: vendored zanshash scraper (works where the JSON API is blocked)
    try:
        items, health = _scraper_fetch(
            subs, max_posts,
            comments_cap=int(reg.get("comments_per_post", 15)),
            sorts=list(reg.get("sort_types", ["new"])),
        )
        if items:
            return items, health
        health.append("reddit scraper returned 0 items everywhere — trying JSON API fallback")
    except Exception as e:  # noqa: BLE001
        health = [f"reddit scraper failed ({type(e).__name__}: {str(e)[:80]}) — JSON API fallback"]

    # ── fallback: public JSON API (plain httpx, then Chromium for the same URL)
    items = []

    consecutive_failures = 0
    with httpx.Client(timeout=20.0, headers={"User-Agent": _UA},
                      follow_redirects=True) as client:
        for sub in subs:
            if consecutive_failures >= 3:
                health.append(
                    "reddit: network-level block detected (3 consecutive sub failures) — "
                    f"skipping remaining {len(subs) - len(health)} subs this run")
                break
            try:
                listing = _fetch_json(
                    client, f"https://www.reddit.com/r/{sub}/new.json?limit={max_posts}")
                children = (listing or {}).get("data", {}).get("children") or []
                if not children:
                    health.append(f"r/{sub}: 0 posts (dead/renamed/empty?)")
                sub_posts = 0
                for ch in children[:max_posts]:
                    d = ch.get("data") or {}
                    post = _post_item(d, sub)
                    if post is None:
                        continue
                    items.append(post)
                    sub_posts += 1
                    time.sleep(_SLEEP)
                    try:
                        tree = _fetch_json(
                            client,
                            f"https://www.reddit.com/comments/{d['id']}.json?limit=50")
                        comments = _walk_comments(
                            (tree[1].get("data", {}).get("children") or []) if
                            isinstance(tree, list) and len(tree) > 1 else [],
                            post.thread_id, sub, cap=50)
                        items.extend(comments)
                    except Exception as e:  # noqa: BLE001 — comments are best-effort
                        health.append(f"r/{sub}/{d.get('id')}: comments failed ({type(e).__name__})")
                time.sleep(_SLEEP)
                consecutive_failures = 0
            except Exception as e:  # noqa: BLE001 — one sub never blocks the run
                consecutive_failures += 1
                health.append(f"r/{sub}: FAILED ({type(e).__name__}: {str(e)[:80]})")
    return items, health
