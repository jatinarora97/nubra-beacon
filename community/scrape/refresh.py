"""Reddit engagement refresh (work plan 2026-07-07, B4).

Engagement is snapshot-at-fetch; threads that became action candidates never
saw their upvotes/comments grow, so opportunity scores aged on stale numbers.
This module re-visits the ROOT posts behind status='suggested' opportunities
via old.reddit (same Playwright transport philosophy as the vendored zanshash
scraper — the vendored lib has no single-thread fetch, so this is our own thin
fetcher; vendored files stay untouched) and updates social_items.engagement
with fresh counts + a recomputed unified score.

Batch-limited: registry sources.reddit.refresh_max_threads (default 20) per
run, highest-priority opportunities first. X refresh is out of scope until
credits return (twitterapi.io 402).

When sources.reddit_apify is enabled the old.reddit path (dead since its legacy HTML was removed)
is replaced by ONE Apify run over the candidate post URLs (harshmaur actor, comments off, about
$0.01 + $0.0014 per thread), once a day in the morning build, ahead of scoring.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from community.config.settings import settings
from community.scrape.base import unified_score
from community.store import db

_OLD = re.compile(r"^https?://(www\.|old\.)?reddit\.com", re.I)
_POST_ID = re.compile(r"/comments/([a-z0-9]+)/", re.I)


def _old_reddit(url: str) -> str:
    return _OLD.sub("https://old.reddit.com", url)


def _candidates(limit: int) -> list[dict]:
    return db.query(
        """
        SELECT item_id, url, engagement, priority FROM (
            SELECT DISTINCT ON (si.item_id) si.item_id, si.url, si.engagement,
                   o.priority
            FROM opportunities o
            JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id)
            JOIN social_items si ON si.item_id = c.root_item_id
            WHERE o.status = 'suggested' AND o.source = 'reddit'
              AND si.url ~* 'reddit\\.com/r/.+/comments/'
            ORDER BY si.item_id, o.priority DESC
        ) t
        ORDER BY priority DESC NULLS LAST  -- highest-priority threads refresh first
        LIMIT %s
        """,
        (limit,),
    )


async def _fetch_counts(page, url: str) -> dict | None:
    """Current (upvotes, comments) from an old.reddit post page. Returns None
    when the page doesn't expose them (deleted/private/blocked)."""
    from community.lib.reddit_scraper.scraper import _parse_int  # vendored parser

    await page.goto(_old_reddit(url), wait_until="load", timeout=30_000)
    counts: dict = {}
    # exact score from the sidebar linkinfo box when present
    exact = page.locator("div.linkinfo div.score span.number").first
    if await exact.count():
        counts["upvotes"] = _parse_int(await exact.inner_text())
    else:  # midcol score next to the arrows (may be abbreviated, e.g. 1.2k)
        mid = page.locator("div.thing.link div.midcol div.score.unvoted").first
        if await mid.count():
            counts["upvotes"] = _parse_int(await mid.inner_text())
    com = page.locator("div.thing.link a.bylink.comments").first
    if await com.count():
        m = re.search(r"([\d.,km]+)\s*comment", (await com.inner_text()).lower())
        if m:
            counts["comments"] = _parse_int(m.group(1))
    return counts if counts.get("upvotes") is not None else None


def _store_counts(r: dict, counts: dict) -> None:
    """Write fresh (upvotes[, comments]) into the item's engagement with a recomputed unified score."""
    native = dict((r["engagement"] or {}).get("native") or {})
    native["upvotes"] = counts["upvotes"]
    if counts.get("comments") is not None:
        native["comments"] = counts["comments"]
    engagement = {
        "score": unified_score(native.get("upvotes", 0), 0, native.get("comments", 0)),
        "native": native,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
    db.execute("UPDATE social_items SET engagement = %s WHERE item_id = %s",
               (db.jsonb(engagement), r["item_id"]))


async def _refresh(rows: list[dict]) -> dict:
    from playwright.async_api import async_playwright

    from community.lib.reddit_scraper.scraper import _UA  # vendored UA string

    stats = {"refreshed": 0, "unreadable": 0, "errors": 0}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=_UA,
                                        viewport={"width": 1280, "height": 900},
                                        locale="en-US")
        page = await ctx.new_page()
        try:
            for r in rows:
                try:
                    counts = await _fetch_counts(page, r["url"])
                except Exception:  # noqa: BLE001 — one bad thread never stops the batch
                    stats["errors"] += 1
                    continue
                if not counts:
                    stats["unreadable"] += 1
                    continue
                _store_counts(r, counts)
                stats["refreshed"] += 1
                await asyncio.sleep(1.0)  # be polite — sequential, jittered enough
        finally:
            await ctx.close()
            await browser.close()
    return stats


def _refresh_via_apify(rows: list[dict], reg: dict) -> dict:
    """One actor run over the post URLs; match each returned post back to its candidate by id."""
    from community.scrape import reddit_apify

    payload = {"startUrls": [{"url": r["url"]} for r in rows], "crawlCommentsPerPost": False,
               "maxPostsCount": len(rows), "includeNSFW": False}
    kw = {"timeout_s": int(reg.get("timeout_s", 900)), "memory_mb": int(reg.get("memory_mb", 1024))}
    cap = reg.get("max_charge_usd", reddit_apify.DEFAULT_MAX_CHARGE_USD)
    if cap is not None:
        kw["max_charge_usd"] = float(cap)
    items = reddit_apify._run_actor(reddit_apify._actor(reg), payload, **kw)
    by_id: dict[str, dict] = {}
    for it in items:
        raw_id = str(it.get("id") or "")
        if it.get("dataType") == "post" and raw_id:
            by_id[raw_id if raw_id.startswith("t3_") else f"t3_{raw_id}"] = it
    stats = {"refreshed": 0, "unreadable": 0, "errors": 0}
    for r in rows:
        m = _POST_ID.search(r["url"] or "")
        it = by_id.get(f"t3_{m.group(1)}") if m else None
        upvotes = None if it is None else (it.get("upVotes") if it.get("upVotes") is not None else it.get("score"))
        if upvotes is None:
            stats["unreadable"] += 1
            continue
        counts = {"upvotes": int(upvotes)}
        if it.get("commentsCount") is not None:
            counts["comments"] = int(it["commentsCount"])
        _store_counts(r, counts)
        stats["refreshed"] += 1
    return stats


def run(daily: bool = False, **_) -> dict:
    sources = settings.registry.get("sources", {})
    apify = sources.get("reddit_apify") or {}
    if apify.get("enabled"):
        from community.scrape import reddit_apify
        if reddit_apify._profile(reddit_apify._actor(apify)) != "harshmaur":
            return {"note": "engagement refresh via Apify needs the harshmaur actor"}
        limit = int(apify.get("refresh_max_threads", 20))
        if limit <= 0:
            return {"note": "engagement refresh disabled (refresh_max_threads <= 0)"}
        if not daily:
            return {"note": "engagement refresh via Apify runs in the morning build"}
        why = reddit_apify.Budget(apify).why_stop()       # the Apify account is shared with other sources
        if why:
            return {"note": f"engagement refresh skipped: {why}"}
        rows = _candidates(limit)
        if not rows:
            return {"note": "no suggested reddit opportunities to refresh"}
        return {"candidates": len(rows), **_refresh_via_apify(rows, apify)}
    reg = sources.get("reddit", {})
    limit = int(reg.get("refresh_max_threads", 20))
    if limit <= 0:
        return {"note": "engagement refresh disabled (refresh_max_threads <= 0)"}
    rows = _candidates(limit)
    if not rows:
        return {"note": "no suggested reddit opportunities to refresh"}
    stats = asyncio.run(_refresh(rows))
    return {"candidates": len(rows), **stats}
