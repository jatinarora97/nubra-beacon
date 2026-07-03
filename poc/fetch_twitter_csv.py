#!/usr/bin/env python3
"""Fetch high-engagement India F&O / algo / broker tweets from the last N days via
twitterapi.io, vet them (drop crypto/forex noise, off-topic, dupes), and save a CSV
that Streamlit reads. Run this offline to refresh the data; the dashboard never calls
the live API itself.

    python fetch_twitter_csv.py            # uses config.yaml `twitter` block + .env key

Budget: bounded by `twitter.max_tweets` in config.yaml (≈ $0.00015/read).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def _load_env():
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

from social_pulse.sources.twitter import (  # noqa: E402
    fetch_twitter, vet, save_twitter_csv, load_twitter_csv, CSV_PATH,
)


def load_config() -> dict:
    for name in ("config.yaml", "config.example.yaml"):
        p = ROOT / name
        if p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def main():
    cfg = load_config()
    print("[1/3] fetching from twitterapi.io …")
    raw = fetch_twitter(cfg)

    print("[2/3] vetting …")
    kept, dropped = vet(raw)
    reasons: dict[str, int] = {}
    for _, why in dropped:
        reasons[why] = reasons.get(why, 0) + 1
    print(f"      kept {len(kept)} / {len(raw)}  ·  dropped {len(dropped)} "
          f"({', '.join(f'{k}:{v}' for k, v in reasons.items()) or 'none'})")

    # accumulate across throttled runs: merge with whatever is already in the CSV
    existing = load_twitter_csv(path=CSV_PATH) if CSV_PATH.exists() else []
    by_id = {it.external_id: it for it in existing}
    added = sum(1 for it in kept if it.external_id not in by_id)
    for it in kept:
        by_id[it.external_id] = it          # newest wins on re-fetch (fresher engagement)
    merged = sorted(by_id.values(), key=lambda it: it.created_at, reverse=True)

    print("[3/3] saving CSV …")
    path = save_twitter_csv(merged)
    print(f"      +{added} new · {len(merged)} total tweets → {path}")
    kept = merged

    # quick top-engagement preview so we can eyeball quality
    top = sorted(kept, key=lambda it: it.engagement.get("score", 0), reverse=True)[:8]
    print("\nTop by likes:")
    for it in top:
        e = it.engagement
        print(f"  ❤{e.get('score',0):>5} 🔁{e.get('retweets',0):>4} 👁{e.get('views',0):>7} "
              f"@{it.author[:18]:18} | {it.text[:80].replace(chr(10),' ')}")


if __name__ == "__main__":
    main()
