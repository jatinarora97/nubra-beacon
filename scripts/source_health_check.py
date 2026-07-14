"""Lightweight source health check for local Beacon setup.

This is intentionally shallow: it checks credentials, DB reachability and a
small fetch from optional collectors without writing any rows.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
from dataclasses import dataclass

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.config.settings import settings


@dataclass
class Check:
    name: str
    status: str
    detail: str


def _db_check() -> Check:
    try:
        import psycopg

        with psycopg.connect(settings.db_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return Check("postgres", "working", settings.db_url)
    except Exception as exc:  # noqa: BLE001 - diagnostic output
        return Check("postgres", "unavailable", f"{type(exc).__name__}: {str(exc)[:180]}")


def _collector_count(name: str, cap: int = 3) -> tuple[int, str | None]:
    try:
        src = settings.registry.get("sources", {}).get(name, {})
        if name == "github":
            from community.scrape import github_public

            cfg = {**src, "max_queries_per_run": 1, "max_items_per_query": cap}
            items = github_public.fetch(cfg)
        elif name == "youtube":
            if not os.getenv("YOUTUBE_API_KEY"):
                return 0, "YOUTUBE_API_KEY missing"
            from community.scrape import youtube

            cfg = {
                **src,
                "queries": {"retail": ["option chain analysis India"]},
                "max_queries_per_run": 1,
                "max_videos_per_query": 1,
                "max_comments_per_video": 1,
            }
            items = youtube.fetch(cfg)
        elif name == "broker_communities":
            from community.scrape import broker_communities

            cfg = {**src, "max_topics_per_source": 2, "max_replies_per_topic": 1}
            items = broker_communities.fetch(cfg)
        elif name == "app_reviews":
            from community.scrape import app_reviews

            cfg = {**src, "max_reviews_per_app": 1}
            items = app_reviews.fetch(cfg)
        else:
            return 0, "unknown source"

        count = 0
        for _ in items:
            count += 1
            if count >= cap:
                break
        return count, None
    except Exception as exc:  # noqa: BLE001 - diagnostic output
        return 0, f"{type(exc).__name__}: {str(exc)[:180]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Beacon local/source health check")
    parser.add_argument("--skip-network", action="store_true", help="Do not hit external sources")
    args = parser.parse_args()

    checks: list[Check] = []
    checks.append(_db_check())
    checks.append(Check("anthropic_key", "configured" if settings.anthropic_api_key else "missing", "ANTHROPIC_API_KEY"))
    checks.append(Check("twitter_key", "configured" if settings.twitterapi_key else "missing", "TWITTERAPI_IO_KEY"))
    checks.append(Check("youtube_key", "configured" if os.getenv("YOUTUBE_API_KEY") else "missing", "YOUTUBE_API_KEY"))
    checks.append(Check("github_token", "configured" if os.getenv("GITHUB_TOKEN") else "optional_missing", "GITHUB_TOKEN"))

    if not args.skip_network:
        for name in ("github", "broker_communities", "app_reviews", "youtube"):
            count, err = _collector_count(name)
            if err:
                status = "skipped" if "missing" in err.lower() else "failed"
                checks.append(Check(name, status, err))
            else:
                checks.append(Check(name, "working" if count else "empty", f"{count} sample items"))

    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"{c.name:<{width}}  {c.status:<16} {c.detail}")

    hard_fail = any(c.status == "failed" for c in checks)
    return 1 if hard_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())

