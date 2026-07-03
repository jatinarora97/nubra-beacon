"""Reddit adapter — live fetch via the public JSON API (httpx), Playwright fallback.

Port decision vs LLD-02 §3 (old.reddit DOM scrape): the public JSON endpoints
(www.reddit.com/r/{sub}/new.json, /comments/{id}.json) return the same data with
zero DOM fragility, so they are the primary transport here; if Reddit blocks the
plain HTTP client (403/429), the SAME URL is fetched once more through headless
Chromium (already installed), which clears most blocks. Politeness: ~0.6s between
requests, realistic UA, per-sub failures degrade to a health note.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import httpx

from community.config.settings import settings
from community.sources.base import AuthorMeta, Engagement, SocialItem, unified_score

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
    """Fetch new posts + comments for every registry subreddit.
    Returns (items, health_notes) — a failing sub is a note, never an exception."""
    reg = settings.registry.get("sources", {}).get("reddit", {})
    subs = reg.get("subreddits", [])
    max_posts = int(reg.get("max_posts_per_sub", 15))
    items: list[SocialItem] = []
    health: list[str] = []

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
