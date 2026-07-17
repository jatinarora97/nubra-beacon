"""Fetch-only smoke test for optional Beacon collectors.

This script does not write to Postgres. It is safe to run before Docker/Postgres
is installed and is useful for checking whether public sources are reachable.

Examples:
    python scripts/test_collectors_fetch_only.py
    python scripts/test_collectors_fetch_only.py --source github --limit 10
    python scripts/test_collectors_fetch_only.py --source youtube --limit 20
"""
from __future__ import annotations

import argparse
import copy
import pathlib
import sys
from collections import Counter
from collections.abc import Iterable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.config.settings import settings
from community.scrape.base import SocialItem


def _compact_config(name: str, reg: dict, limit: int) -> dict:
    cfg = copy.deepcopy(reg)
    if name == "github":
        cfg["max_queries_per_run"] = min(int(cfg.get("max_queries_per_run", 20)), 3)
        cfg["max_items_per_query"] = min(limit, int(cfg.get("max_items_per_query", 20)))
    elif name == "youtube":
        cfg["max_queries_per_run"] = min(int(cfg.get("max_queries_per_run", 20)), 2)
        cfg["max_videos_per_query"] = min(3, int(cfg.get("max_videos_per_query", 5)))
        cfg["max_comments_per_video"] = min(5, int(cfg.get("max_comments_per_video", 20)))
    elif name == "broker_communities":
        cfg["max_topics_per_source"] = min(4, int(cfg.get("max_topics_per_source", 20)))
        cfg["max_replies_per_topic"] = min(3, int(cfg.get("max_replies_per_topic", 10)))
    elif name == "app_reviews":
        cfg["max_reviews_per_app"] = min(5, int(cfg.get("max_reviews_per_app", 100)))
    return cfg


def _fetch(name: str, reg: dict) -> Iterable[SocialItem]:
    if name == "github":
        from community.scrape import github_public

        return github_public.fetch(reg)
    if name == "youtube":
        from community.scrape import youtube

        return youtube.fetch(reg)
    if name == "broker_communities":
        from community.scrape import broker_communities

        return broker_communities.fetch(reg)
    if name == "app_reviews":
        from community.scrape import app_reviews

        return app_reviews.fetch(reg)
    raise ValueError(f"Unknown source: {name}")


def _print_items(name: str, items: list[SocialItem], show: int) -> None:
    print(f"\n{name}: fetched={len(items)}")
    print("types:", dict(Counter(i.source_type for i in items)))
    print("partitions:", dict(Counter(str(i.raw.get("partition", "")) for i in items if i.raw.get("partition"))))
    for item in items[:show]:
        text = " ".join(item.text.split())[:180]
        print(f"- {item.source_type} | score={item.engagement.score:.2f} | {item.url}")
        print(f"  {text}")


def main() -> int:
    # Windows PowerShell can default to a legacy code page. Collector text is
    # Unicode, so diagnostics must not fail merely while printing a sample.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Fetch-only smoke tests for optional collectors")
    parser.add_argument(
        "--source",
        choices=["all", "github", "youtube", "broker_communities", "app_reviews"],
        default="all",
    )
    parser.add_argument("--limit", type=int, default=25, help="Max items retained per source")
    parser.add_argument("--show", type=int, default=5, help="Sample rows printed per source")
    args = parser.parse_args()

    sources = settings.registry.get("sources", {})
    names = ["github", "broker_communities", "app_reviews", "youtube"]
    if args.source != "all":
        names = [args.source]

    failures: dict[str, str] = {}
    for name in names:
        cfg = _compact_config(name, sources.get(name, {}), args.limit)
        try:
            items = []
            for item in _fetch(name, cfg):
                items.append(item)
                if len(items) >= args.limit:
                    break
            _print_items(name, items, args.show)
        except Exception as exc:  # noqa: BLE001 - this is a diagnostics script
            failures[name] = f"{type(exc).__name__}: {exc}"
            print(f"\n{name}: FAILED: {failures[name]}")

    if failures:
        print("\nFailures:")
        for name, err in failures.items():
            print(f"- {name}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
