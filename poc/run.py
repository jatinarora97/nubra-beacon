#!/usr/bin/env python3
"""Social Pulse prototype entrypoint.

Real data only — each run scrapes live, appends to the on-disk store (de-duplicated),
then analyses the full accumulated window.

Examples:
  python run.py --sources reddit            # real Reddit (Playwright scraper)
  python run.py --sources reddit,telegram   # multiple
  python run.py --days 14                    # analysis/scrape window
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def _load_env():
    """Load .env (gitignored) so CLI runs get the Anthropic key like the dashboard does."""
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

from social_pulse.schema import connect, upsert_items, load_items  # noqa: E402
from social_pulse.pipeline.dedupe import dedupe  # noqa: E402
from social_pulse.pipeline.prefilter import prefilter  # noqa: E402
from social_pulse.pipeline.classify import classify  # noqa: E402
from social_pulse.pipeline.trend import rank_topics  # noqa: E402
from social_pulse.pipeline import brief as brief_mod  # noqa: E402


def load_config() -> dict:
    for name in ("config.yaml", "config.example.yaml"):
        p = ROOT / name
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def ingest(sources: list[str], cfg: dict):
    items = []
    for s in sources:
        if s == "reddit":
            from social_pulse.sources.reddit import fetch_reddit
            items += fetch_reddit(cfg)
        elif s == "telegram":
            from social_pulse.sources.telegram import fetch_telegram
            items += fetch_telegram(cfg)
        elif s == "twitter":
            from social_pulse.sources.twitter import load_twitter_csv
            items += load_twitter_csv(cfg)
        else:
            print(f"  [warn] unknown source: {s}")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="reddit", help="comma list: reddit,telegram")
    ap.add_argument("--days", type=int, default=None, help="analysis/scrape window in days")
    args = ap.parse_args()

    cfg = load_config()
    con = connect()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    days = args.days if args.days is not None else int(cfg.get("reddit", {}).get("days", 7))
    if args.days is not None:
        cfg.setdefault("reddit", {})["days"] = args.days
    print(f"[1/6] scrape  (sources={sources}, days={days})")
    fetched = ingest(sources, cfg)
    new_rows = upsert_items(con, fetched)
    print(f"      scraped {len(fetched)} items ({new_rows} new in store)")

    # analyse the accumulated store within the window, not just this batch
    items = load_items(con, days=days, sources=sources)
    print(f"      working set from store: {len(items)} items")

    print("[2/6] dedupe")
    groups = dedupe(items)
    print(f"      {len(items)} -> {len(groups)} unique groups")

    print("[3/6] prefilter")
    kept = prefilter(groups, cfg)
    print(f"      {len(groups)} -> {len(kept)} relevant")

    print("[4/6] classify")
    classified = classify(kept)
    noise = sum(1 for c in classified if c.get("is_noise"))
    print(f"      classified {len(classified)} ({noise} flagged noise)")

    print("[5/6] trend rank")
    ranked = rank_topics(classified, cfg)
    print(f"      {len(ranked)} rising topics")

    print("[6/6] brief\n")
    stats = {"ingested": len(items), "unique": len(groups), "relevant": len(kept)}
    payload = brief_mod.to_payload(ranked, stats)
    brief_mod.save_brief(con, payload)
    print(brief_mod.render_terminal(ranked, stats))


if __name__ == "__main__":
    main()
