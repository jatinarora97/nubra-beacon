# VENDORED from github.com/zanshash/reddit_scraper @ f926fc7
# (+ nested-replies patch — see this script's docstring)
# Do not edit here; update the source repo, then run scripts/sync_reddit_scraper.py
import asyncio
import json
import logging
import os
import random
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import BrowserContext, Page, async_playwright

from .config import (
    COMMENTS_PER_POST,
    DOWNLOAD_IMAGES,
    HEADLESS,
    IMAGES_DIR,
    MAX_DELAY,
    MIN_DELAY,
    OUTPUT_DIR,
    POSTS_PER_FEED,
    SORT_TYPES,
    SUBREDDITS,
)
from .models import Comment, Post

BASE = "https://old.reddit.com"
SKIP_IDS: set = set()  # PATCH: pre-known ids to skip (set by the caller)
log = logging.getLogger(__name__)

# Posts from these accounts are always noise (megathreads, daily threads, promos)
BOT_AUTHORS = {
    "automoderator",
    "sebi-bot",
    "sneakpeekbot",
    "repostsleuthbot",
    "remindmebot",
}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── helpers ────────────────────────────────────────────────────────────────────

async def jitter():
    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def _parse_int(text: str) -> Optional[int]:
    if not text:
        return None
    text = text.strip().lower().replace(",", "")
    if text in ("•", "vote", "-", "hidden", ""):
        return None
    m = re.search(r"([\d.]+)\s*([km]?)", text)
    if not m:
        return None
    val = float(m.group(1))
    suffix = m.group(2)
    if suffix == "k":
        val *= 1_000
    elif suffix == "m":
        val *= 1_000_000
    return int(val)


def _post_type(domain: str, url: str) -> str:
    if domain.startswith("self."):
        return "self"
    if domain == "i.redd.it" or re.search(r"\.(jpe?g|png|gif|webp)(\?|$)", url, re.I):
        return "image"
    if domain == "gallery.reddit.com" or "/gallery/" in url:
        return "gallery"
    if domain == "v.redd.it":
        return "video"
    return "link"


def _image_ext(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        if path.endswith(ext):
            return ext
    return ".jpg"


# ── NSFW / age gate ────────────────────────────────────────────────────────────

async def _accept_over18(page: Page):
    try:
        # old Reddit age-gate is a form with a "yes" button
        btn = page.locator("button[name='over18'], input[value='yes'][name='over18']")
        if await btn.count() > 0:
            await btn.first.click()
            await page.wait_for_load_state("domcontentloaded")
    except Exception:
        pass


# ── listing page ───────────────────────────────────────────────────────────────

async def fetch_listing(page: Page, subreddit: str, sort: str) -> List[Dict]:
    # Fetch extra so bot-filtered posts don't shrink us below POSTS_PER_FEED
    fetch_limit = POSTS_PER_FEED + 15
    url = f"{BASE}/r/{subreddit}/{sort}/?limit={fetch_limit}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except Exception as exc:
        log.error(f"Could not load listing for r/{subreddit}/{sort}: {exc}")
        return []

    await _accept_over18(page)

    if await page.locator(".error-page, .privatesubreddit, .quarantine").count() > 0:
        log.warning(f"r/{subreddit} is private/banned/quarantined — skipping")
        return []

    await jitter()

    things = await page.locator(
        "div#siteTable > div.thing.link:not(.promoted)"
    ).all()

    posts: List[Dict] = []
    for thing in things:
        if len(posts) >= POSTS_PER_FEED:
            break
        try:
            pid    = await thing.get_attribute("data-fullname") or ""
            plink  = await thing.get_attribute("data-permalink") or ""
            purl   = await thing.get_attribute("data-url") or ""
            author = await thing.get_attribute("data-author") or "[deleted]"
            domain = await thing.get_attribute("data-domain") or ""

            # Skip bot / AutoModerator posts
            if author.lower() in BOT_AUTHORS:
                log.debug(f"Skipping bot post by {author}")
                continue

            score_attr = await thing.get_attribute("data-score")
            score = int(score_attr) if score_attr and score_attr.lstrip("-").isdigit() else None

            title_el = thing.locator("a.title").first
            title    = (await title_el.inner_text()).strip() if await title_el.count() else ""

            # Link flair on old Reddit uses .linkflairlabel, not .flair
            # (.flair is user flair next to the username)
            flair_el = thing.locator("span.linkflairlabel, a.linkflairlabel").first
            flair    = (await flair_el.inner_text()).strip() if await flair_el.count() else None

            # "456 comments" / "1 comment" / "no comments" → int
            cmt_el   = thing.locator("a.comments").first
            cmt_text = (await cmt_el.inner_text()).strip() if await cmt_el.count() else "0"
            if not cmt_text or "no" in cmt_text.lower():
                num_comments = 0
            else:
                num_comments = _parse_int(cmt_text.split()[0]) or 0

            # data-timestamp is milliseconds since epoch on old Reddit
            ts_attr   = await thing.get_attribute("data-timestamp")
            timestamp = int(ts_attr) // 1000 if ts_attr and ts_attr.lstrip("-").isdigit() else None

            posts.append({
                "id":           pid,
                "permalink":    plink,
                "url":          purl,
                "author":       author,
                "domain":       domain,
                "title":        title,
                "score":        score,
                "num_comments": num_comments,
                "flair":        flair,
                "post_type":    _post_type(domain, purl),
                "timestamp":    timestamp,
            })
        except Exception as exc:
            log.debug(f"Listing extract error: {exc}")

    return posts


# ── post detail page ────────────────────────────────────────────────────────────

async def fetch_post(page: Page, meta: Dict, subreddit: str, sort: str) -> Optional[Post]:
    target = f"{BASE}{meta['permalink']}"
    try:
        await page.goto(target, wait_until="load", timeout=30_000)
        await _accept_over18(page)
        await jitter()
    except Exception as exc:
        log.error(f"Navigation failed for {target}: {exc}")
        return None

    # ── flair (fallback from post page if listing didn't capture it) ──────────
    flair = meta["flair"]
    if not flair:
        flair_el = page.locator(
            "div.thing.link span.linkflairlabel, div.thing.link a.linkflairlabel"
        ).first
        if await flair_el.count():
            flair = (await flair_el.inner_text()).strip() or None

    # ── self text ──────────────────────────────────────────────────────────────
    selftext: Optional[str] = None
    st_el = page.locator("div.thing.link .expando .usertext-body .md").first
    if await st_el.count():
        raw = (await st_el.inner_text()).strip()
        selftext = raw or None

    # ── images ─────────────────────────────────────────────────────────────────
    image_urls: List[str] = []
    ptype = meta["post_type"]

    if ptype == "image":
        u = meta["url"]
        if re.search(r"\.(jpe?g|png|gif|webp)(\?|$)", u, re.I) or "i.redd.it" in u:
            image_urls.append(u)

    elif ptype == "gallery":
        # old Reddit renders gallery thumbnails inside media-preview-content
        for img in await page.locator(
            "a.gallery-item img, div.media-preview-content img, div.gallery-preview img"
        ).all():
            src = await img.get_attribute("src") or ""
            # Prefer the full-resolution URL by replacing preview with i.redd.it
            if "preview.redd.it" in src:
                src = re.sub(r"preview\.redd\.it", "i.redd.it", src)
                src = re.sub(r"\?.*$", "", src)
            if src and src not in image_urls:
                image_urls.append(src)

    # Always capture any i.redd.it images embedded in the post body
    for img in await page.locator("div.thing.link img[src*='i.redd.it']").all():
        src = await img.get_attribute("src") or ""
        if src and src not in image_urls:
            image_urls.append(src)

    # ── comments ───────────────────────────────────────────────────────────────
    comments = await fetch_comments(page)

    # ── download images ────────────────────────────────────────────────────────
    local_images: List[str] = []
    if DOWNLOAD_IMAGES and image_urls:
        local_images = await download_images(image_urls, meta["id"])

    return Post(
        id=meta["id"],
        subreddit=subreddit,
        sort_type=sort,
        title=meta["title"],
        author=meta["author"],
        score=meta["score"],
        num_comments=meta["num_comments"],
        permalink=meta["permalink"],
        url=meta["url"],
        post_type=ptype,
        selftext=selftext,
        flair=flair,
        image_urls=image_urls,
        local_images=local_images,
        comments=comments,
        timestamp=meta.get("timestamp"),
    )


# ── comments ────────────────────────────────────────────────────────────────────

async def fetch_comments(page: Page, limit: Optional[int] = None) -> List[Comment]:
    comments: List[Comment] = []

    # Wait for comment area to appear in DOM (old Reddit is server-rendered,
    # but "load" state still needs a moment for layout)
    try:
        await page.wait_for_selector(".commentarea", timeout=8_000)
    except Exception:
        log.debug("No .commentarea found on this page")
        return comments

    # Expand one batch of "load more" to surface buried top comments
    try:
        more = page.locator("span.morecomments a, a.morecomments").first
        if await more.count():
            await more.click()
            await asyncio.sleep(1.5)
    except Exception:
        pass

    # Old Reddit structure:
    #   div.commentarea
    #     div.sitetable.nestedlisting   ← NOT always a direct child; use descendant
    #       div.thing.comment           ← top-level comment
    # The original selector used strict > chains which broke when any wrapper
    # element was inserted between commentarea and nestedlisting.
    top = await page.locator(
        "div.commentarea div.nestedlisting > div.thing.comment"
    ).all()

    # Fallback for subreddits that add a .top-level class directly
    if not top:
        top = await page.locator("div.thing.comment.top-level").all()

    cap = limit if limit is not None else COMMENTS_PER_POST
    for el in top[:cap]:
        try:
            author_el = el.locator("a.author").first
            author = (
                (await author_el.inner_text()).strip()
                if await author_el.count() else "[deleted]"
            )

            score_el  = el.locator("span.score").first
            score_txt = await score_el.inner_text() if await score_el.count() else ""
            score     = _parse_int(score_txt.split()[0]) if score_txt.strip() else None

            # old Reddit wraps usertext in <form class="usertext">, so the path is:
            #   div.entry > form.usertext > div.usertext-body > div.md
            # Keep the first > to scope to THIS comment's entry (not a nested reply's),
            # then use descendant combinators past the form wrapper.
            body_el = el.locator("> div.entry div.usertext-body div.md").first
            body    = (await body_el.inner_text()).strip() if await body_el.count() else ""

            # PATCH: one nested reply level (strict child chain, cap 3)
            replies = []
            try:
                nested = await el.locator(
                    "> div.child > div.sitetable > div.thing.comment").all()
                for rel in nested[:3]:
                    r_author_el = rel.locator("a.author").first
                    r_author = ((await r_author_el.inner_text()).strip()
                                if await r_author_el.count() else "[deleted]")
                    r_score_el = rel.locator("span.score").first
                    r_score_txt = (await r_score_el.inner_text()
                                   if await r_score_el.count() else "")
                    r_score = (_parse_int(r_score_txt.split()[0])
                               if r_score_txt.strip() else None)
                    r_body_el = rel.locator(
                        "> div.entry div.usertext-body div.md").first
                    r_body = ((await r_body_el.inner_text()).strip()
                              if await r_body_el.count() else "")
                    if r_body:
                        replies.append(
                            {"author": r_author, "score": r_score, "body": r_body})
            except Exception as exc:
                log.debug(f"Reply extract error: {exc}")

            if body:
                comments.append(
                    Comment(author=author, score=score, body=body, replies=replies))
        except Exception as exc:
            log.debug(f"Comment extract error: {exc}")

    return comments


# ── image download ──────────────────────────────────────────────────────────────

async def download_images(urls: List[str], post_id: str) -> List[str]:
    os.makedirs(IMAGES_DIR, exist_ok=True)
    saved: List[str] = []
    headers = {"User-Agent": _UA}

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        for i, url in enumerate(urls):
            if not url.startswith("http"):
                continue
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    ext  = _image_ext(url)
                    path = os.path.join(IMAGES_DIR, f"{post_id}_{i}{ext}")
                    Path(path).write_bytes(r.content)
                    saved.append(path)
                    log.debug(f"Downloaded → {path}")
                else:
                    log.warning(f"Image {url} returned HTTP {r.status_code}")
            except Exception as exc:
                log.warning(f"Image download failed ({url}): {exc}")

    return saved


# ── subreddit orchestration ─────────────────────────────────────────────────────

async def scrape_subreddit(ctx: BrowserContext, subreddit: str) -> List[dict]:
    page = await ctx.new_page()
    seen: set     = set()
    results: List[dict] = []

    try:
        for sort in SORT_TYPES:
            log.info(f"r/{subreddit} [{sort}] — fetching listing")
            metas = await fetch_listing(page, subreddit, sort)
            log.info(f"  {len(metas)} posts in listing")

            for meta in metas:
                if meta["id"] in seen or meta["id"] in SKIP_IDS:
                    continue
                seen.add(meta["id"])

                post = await fetch_post(page, meta, subreddit, sort)
                if post:
                    results.append(post.to_dict())
                    log.info(
                        f"  [{post.post_type:7s}] {post.title[:65]}"
                        f"  ({len(post.comments)} comments, {len(post.image_urls)} imgs)"
                    )

                await jitter()

        # Polite pause between subreddits
        await asyncio.sleep(random.uniform(3, 6))

    except Exception as exc:
        log.error(f"Unexpected error while scraping r/{subreddit}: {exc}")
    finally:
        await page.close()

    return results


# ── entry point ─────────────────────────────────────────────────────────────────

async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    combined: Dict[str, List[dict]] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=HEADLESS)
        ctx = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1280, "height": 900},
            locale="en-US",
        )
        # Block ad/tracker domains to speed things up
        await ctx.route(
            re.compile(r"(doubleclick\.net|googlesyndication|adnxs|amazon-adsystem)"),
            lambda route, _: route.abort(),
        )

        try:
            for sub in SUBREDDITS:
                log.info(f"\n{'─' * 60}\nr/{sub}\n{'─' * 60}")
                posts = await scrape_subreddit(ctx, sub)
                combined[sub] = posts

                out = os.path.join(OUTPUT_DIR, f"{sub}.json")
                with open(out, "w", encoding="utf-8") as f:
                    json.dump(posts, f, ensure_ascii=False, indent=2)
                log.info(f"Saved {len(posts)} posts → {out}")
        finally:
            await ctx.close()
            await browser.close()

    out_all = os.path.join(OUTPUT_DIR, "all_results.json")
    with open(out_all, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)
    log.info(f"\nAll results → {out_all}")

    return combined
