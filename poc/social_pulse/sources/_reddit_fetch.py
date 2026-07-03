"""Subprocess worker: runs the vendored git scraper (reference/reddit_scraper)
against our configured subreddits and writes the raw post JSON to a file.

Run as a subprocess (not imported) so Playwright's asyncio runs in a clean main
thread — avoids event-loop-in-worker-thread issues under Streamlit.

    python -m social_pulse.sources._reddit_fetch '<json-config>' <out_path>
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]              # project root (6.MarketPulse)
REF = ROOT / "reference" / "reddit_scraper"             # the cloned git scraper
sys.path.insert(0, str(REF))

import scraper as R  # noqa: E402  — the git code's core extraction
from playwright.async_api import async_playwright  # noqa: E402


async def scrape(subs, sorts, posts_per, comments_per):
    # Override the git module's globals (scraper.py imports these by value at import time,
    # so we set them on the module object itself, not on its config module).
    R.SORT_TYPES = sorts
    R.POSTS_PER_FEED = posts_per
    R.COMMENTS_PER_POST = comments_per
    R.DOWNLOAD_IMAGES = False

    out = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent=R._UA, viewport={"width": 1280, "height": 900}, locale="en-US",
        )
        await ctx.route(
            re.compile(r"(doubleclick\.net|googlesyndication|adnxs|amazon-adsystem)"),
            lambda route, _: route.abort(),
        )
        try:
            for sub in subs:
                out[sub] = await R.scrape_subreddit(ctx, sub)  # returns list of post dicts
        finally:
            await ctx.close()
            await browser.close()
    return out


def main():
    cfg = json.loads(sys.argv[1])
    out_path = sys.argv[2]
    res = asyncio.run(scrape(
        cfg["subreddits"], cfg["listings"],
        int(cfg["posts_per"]), int(cfg["comments_per"]),
    ))
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
