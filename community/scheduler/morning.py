"""Morning build — the 06:00–07:30 IST orchestrated sequence (arch §8).

The one place stages run as a sequence rather than independent timers:
catch-up scrape (incl. the once-daily `top` feed) → enrich SYNC (skips the
Batch API so the chain closes before the 07:30 roundup) → aggregate → score →
drafts → compose (daily; weekly on Saturdays, inside compose) → dispatch.
"""
from __future__ import annotations

import json
import time


def _echo(name: str, stats: dict) -> None:
    print(f"[morning:{name}] {json.dumps(stats, default=str)[:300]}")


def run_morning_build() -> dict:
    from community.scrape import x_trends
    from community.aggregate import rollups
    from community.clean import dedup
    from community.compose import roundup
    from community.dispatch import local as dispatch
    from community.enrich import tagger
    from community.recommend import draft, score
    from community.scrape import ingest

    all_stats: dict[str, dict] = {}
    t0 = time.time()

    all_stats["scrape"] = ingest.run(daily=True)  # daily=True → include `top` feed (scrape stage owns it)
    print('[morning] trend discovery:', x_trends.discover())
    from community.aggregate import discover
    print('[morning] topic discovery:', discover.discover_topics())
    _echo("scrape", all_stats["scrape"])
    all_stats["clean"] = dedup.run()
    _echo("clean", all_stats["clean"])
    try:
        all_stats["enrich"] = tagger.run(sync=True)  # morning pass = sync (cost plan §2.1)
    except TypeError:  # TODO: `sync` kwarg lands with the Batch-API enrichment task
        all_stats["enrich"] = tagger.run()
    _echo("enrich", all_stats["enrich"])
    all_stats["aggregate"] = rollups.run()
    _echo("aggregate", all_stats["aggregate"])
    all_stats["score"] = score.run()
    _echo("score", all_stats["score"])
    all_stats["draft"] = draft.run()
    _echo("draft", all_stats["draft"])
    all_stats["compose"] = roundup.run()  # daily; +weekly automatically on Saturdays
    _echo("compose", all_stats["compose"])
    all_stats["dispatch"] = dispatch.run(all_stats)
    _echo("dispatch", all_stats["dispatch"])

    print(f"[morning] complete in {time.time() - t0:.0f}s")
    return all_stats
