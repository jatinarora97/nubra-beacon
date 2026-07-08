"""Reddit keyword-search collection (user request 2026-07-08, item 1).

Active watch_sources keywords with config.reddit=true FETCH matching posts via
old.reddit search (https://old.reddit.com/search?q=...&sort=new&t=week) — all
of Reddit, not just watched subreddits — using the same thin-Playwright
transport philosophy as refresh.py (vendored community/lib stays untouched;
we import only its _parse_int/_UA helpers). Additive post-step in the scrape
stage: a failure here never breaks subreddit collection.

Design choices (v1):
- Posts only, NO comment-tree fetch for keyword hits — cost control. The post
  itself is the signal; if it becomes an action candidate its thread engagement
  is refreshed by refresh.py, and its comments arrive naturally if the sub is
  (or becomes) watched.
- external_id = t3_<base36 from the permalink> — identical to the vendored
  scraper's id format, so a post found via BOTH paths dedups to one row via
  ingest's insert-if-absent on (source, external_id).
- Text = title + the search-result selftext snippet old.reddit exposes (search
  listings don't carry full selftext; the snippet is enough for enrichment and
  the permalink is stored for humans).
- Caps: registry sources.reddit.keyword_max_posts per keyword (default 10),
  fixed one-week search window, 1s polite delay between keywords.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import quote

from community.clean.normalize import norm
from community.config.settings import settings
from community.reference.taxonomy import MARKET_TERMS
from community.scrape.base import AuthorMeta, Engagement, SocialItem, unified_score
from community.store import db, repositories as repo

_PERMALINK_ID = re.compile(r"/comments/([a-z0-9]+)/", re.I)

# Market-context gate: old.reddit search matching is loose (verified live —
# bare 'nubra' returns Nubra Valley travel posts even with OR qualifiers), so
# a fetched post must mention at least one market term to be ingested.
# Opt out per keyword with config.skip_context_gate=true.
_MARKET_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(t) for t in MARKET_TERMS) + r")(?![a-z])", re.I)


def _active_keywords() -> list[tuple[str, str]]:
    """[(keyword, search_query)]. config.reddit_query overrides the raw keyword
    as the old.reddit search string — needed for homonyms (e.g. bare 'nubra'
    surfaces Nubra Valley travel posts; the override anchors the broker sense)."""
    try:
        return [(r["value"],
                 (r["config"] or {}).get("reddit_query") or r["value"],
                 bool((r["config"] or {}).get("skip_context_gate")))
                for r in db.query(
                    "SELECT value, config FROM watch_sources WHERE kind='keyword' "
                    "AND active AND COALESCE((config->>'reddit')::boolean, false) "
                    "ORDER BY value")]
    except Exception:  # noqa: BLE001 — DB hiccup: skip quietly, main scrape owns health
        return []


async def _search(page, keyword: str, cap: int) -> list[dict]:
    """Parse up to `cap` result rows from an old.reddit search page."""
    from community.lib.reddit_scraper.scraper import _parse_int  # vendored parser

    url = (f"https://old.reddit.com/search?q={quote(keyword)}"
           f"&sort=new&t=week&restrict_sr=off")
    await page.goto(url, wait_until="load", timeout=30_000)
    rows = page.locator("div.search-result.search-result-link")
    out: list[dict] = []
    for i in range(min(await rows.count(), cap)):
        row = rows.nth(i)
        try:
            title_el = row.locator("a.search-title").first
            if not await title_el.count():
                continue
            title = (await title_el.inner_text()).strip()
            permalink = await title_el.get_attribute("href") or ""
            m = _PERMALINK_ID.search(permalink)
            if not title or not m:
                continue
            sub_el = row.locator("a.search-subreddit-link").first
            subreddit = ((await sub_el.inner_text()).strip().removeprefix("r/")
                         if await sub_el.count() else "unknown")
            author_el = row.locator("span.search-author a").first
            author = ((await author_el.inner_text()).strip().removeprefix("u/")
                      if await author_el.count() else None)
            score_el = row.locator("span.search-score").first
            points = (_parse_int((await score_el.inner_text()).split()[0])
                      if await score_el.count() else 0) or 0
            com_el = row.locator("a.search-comments").first
            comments = 0
            if await com_el.count():
                cm = re.search(r"([\d.,km]+)", (await com_el.inner_text()).lower())
                comments = (_parse_int(cm.group(1)) if cm else 0) or 0
            time_el = row.locator("time").first
            created = None
            if await time_el.count():
                dt = await time_el.get_attribute("datetime")
                if dt:
                    created = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            snippet_el = row.locator("div.search-result-body").first
            snippet = ((await snippet_el.inner_text()).strip()
                       if await snippet_el.count() else "")
            out.append({
                "id": f"t3_{m.group(1)}", "title": title, "snippet": snippet,
                "permalink": permalink, "subreddit": subreddit, "author": author,
                "points": points, "comments": comments,
                "created": created or datetime.now(timezone.utc),
            })
        except Exception:  # noqa: BLE001 — one bad row never stops the page
            continue
    return out


def _to_item(r: dict, keyword: str) -> SocialItem:
    text = " ".join(x for x in (r["title"], r["snippet"]) if x)
    return SocialItem(
        source="reddit", source_type="post",
        external_id=r["id"], parent_id=None, thread_id=r["id"],
        author=r["author"], author_meta=AuthorMeta(),
        text=text[:8000], lang=None,
        url=r["permalink"],
        created_at=r["created"],
        engagement=Engagement(
            score=unified_score(r["points"], 0, r["comments"]),
            native={"upvotes": r["points"], "comments": r["comments"]}),
        raw={"subreddit": r["subreddit"], "category": "keyword",
             "via": "keyword_search", "keyword": keyword},
    )


def _store(item: SocialItem) -> bool:
    """Same persistence path as ingest._store (insert-if-absent dedup)."""
    author_id = repo.upsert_author(
        item.source, item.author,
        followers=item.author_meta.followers,
        verified=item.author_meta.verified,
        meta=item.author_meta.model_dump(exclude_none=True, mode="json"),
    )
    return bool(repo.insert_item_if_absent({
        "source": item.source, "source_type": item.source_type,
        "external_id": item.external_id, "parent_id": item.parent_id,
        "thread_id": item.thread_id, "author_id": author_id,
        "text": item.text, "lang": item.lang, "url": item.url,
        "content_hash": repo.content_hash(norm(item.text)),
        "engagement": item.engagement.model_dump(mode="json"),
        "raw": item.raw, "created_at": item.created_at,
    }))


async def _run(keywords: list[tuple[str, str]], cap: int) -> dict:
    from playwright.async_api import async_playwright

    from community.lib.reddit_scraper.scraper import _UA  # vendored UA string

    stats = {"keywords": len(keywords), "found": 0, "inserted": 0,
             "skipped_existing": 0, "off_context": 0, "errors": 0}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=_UA,
                                        viewport={"width": 1280, "height": 900},
                                        locale="en-US")
        page = await ctx.new_page()
        try:
            for kw, query, skip_gate in keywords:
                try:
                    rows = await _search(page, query, cap)
                except Exception:  # noqa: BLE001 — one bad keyword never stops the batch
                    stats["errors"] += 1
                    continue
                stats["found"] += len(rows)
                for r in rows:
                    if not r["author"] or r["author"] == "[deleted]":
                        continue
                    if not skip_gate and not _MARKET_RE.search(
                            f"{r['title']} {r['snippet']}"):
                        stats["off_context"] += 1
                        continue
                    if _store(_to_item(r, kw)):
                        stats["inserted"] += 1
                    else:
                        stats["skipped_existing"] += 1
                await asyncio.sleep(1.0)  # polite — sequential
        finally:
            await ctx.close()
            await browser.close()
    return stats


def run(**_) -> dict:
    reg = settings.registry.get("sources", {}).get("reddit", {})
    cap = int(reg.get("keyword_max_posts", 10))
    if cap <= 0:
        return {"note": "keyword search disabled (keyword_max_posts <= 0)"}
    keywords = _active_keywords()
    if not keywords:
        return {"note": "no active reddit-enabled keywords"}
    return asyncio.run(_run(keywords, cap))
