"""One-time Reddit gap backfill (outage 2026-08-10 → 2026-08-25).

Run on prod AFTER REDDIT_PROXY_URL is set in .env and the api container was
recreated:

    docker compose exec -T api python scripts/backfill_reddit.py

Deep-crawls every watched sub across new/hot/rising/top at 100 posts per feed
(vs the steady-state 10). Idempotent: already-stored posts are skipped before
their detail visit (SKIP_IDS), inserts are if-absent — safe to re-run.
Recovers posts + their CURRENT comments/scores; point-in-time engagement from
the gap is unrecoverable. Estimated proxy spend: $3-5 (metered residential).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.config.settings import settings
from community.scrape import reddit
from community.scrape.extra_sources import _store


def main() -> None:
    if not os.getenv("REDDIT_PROXY_URL", "").strip():
        print("REDDIT_PROXY_URL is not set — the VM's direct IP is blocked by "
              "Reddit; set it in .env and recreate the api container first.")
        sys.exit(1)
    if not reddit._preflight():
        print("preflight FAILED even via the proxy — old.reddit unreachable; "
              "aborting before spending crawl bandwidth.")
        sys.exit(1)
    print("preflight OK via proxy — deep-crawling (this takes 30-60+ min)…")

    cfg = settings.registry["sources"]["reddit"]
    cfg["max_posts_per_sub"] = int(os.getenv("REDDIT_BACKFILL_POSTS", "100"))

    # one sub at a time, stored IMMEDIATELY after each: a killed session or a
    # mid-crawl crash keeps everything already crawled (lesson 2026-08-25 —
    # an all-at-end run died with the user's terminal and lost 40+ min of work)
    subs = list(cfg.get("subreddits") or [])
    flat = []
    for entry in subs:
        flat += list(entry.values())[0] if isinstance(entry, dict) else [entry]
    if isinstance(cfg.get("subreddits"), dict):
        flat = [s for lst in cfg["subreddits"].values() for s in lst]
    totals = {"enabled": True, "fetched": 0, "inserted": 0, "skipped_existing": 0}
    all_health = []
    for i, sub in enumerate(flat, 1):
        cfg["subreddits"] = {"backfill": [sub]}
        try:
            items, health = reddit.fetch_live(sorts=["new", "hot", "rising", "top"])
        except Exception as e:  # noqa: BLE001 — one sub must not sink the rest
            print(f"[{i}/{len(flat)}] r/{sub}: CRAWL ERROR {type(e).__name__}: {str(e)[:100]}",
                  flush=True)
            continue
        before = totals["inserted"]
        for item in items:
            totals["fetched"] += 1
            _store(item, totals)
        all_health += health
        print(f"[{i}/{len(flat)}] r/{sub}: +{totals['inserted'] - before} inserted "
              f"(totals: {totals['inserted']} inserted / {totals['skipped_existing']} known)",
              flush=True)
    print(json.dumps(totals, indent=1))
    if all_health:
        print("health notes:", json.dumps(all_health[:10], indent=1))
    print("done — enrichment picks the new items up on the next pipeline run")


if __name__ == "__main__":
    main()
