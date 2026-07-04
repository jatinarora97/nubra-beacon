"""Stage ① INGEST — CSV backfill + Reddit live + X live (capped). LLD-02 §§1–4.

Idempotent: insert-if-absent on (source, external_id); reruns insert ~0.
"""
from __future__ import annotations

from community.config.settings import settings
from community.clean.normalize import norm
from community.scrape import reddit, twitter
from community.scrape.base import SocialItem
from community.store import repositories as repo


def _store(item: SocialItem, counters: dict) -> None:
    author_id = repo.upsert_author(
        item.source, item.author,
        followers=item.author_meta.followers,
        verified=item.author_meta.verified,
        meta=item.author_meta.model_dump(exclude_none=True, mode="json"),
    )
    item_id = repo.insert_item_if_absent({
        "source": item.source,
        "source_type": item.source_type,
        "external_id": item.external_id,
        "parent_id": item.parent_id,
        "thread_id": item.thread_id,
        "author_id": author_id,
        "text": item.text,
        "lang": item.lang,
        "url": item.url,
        "content_hash": repo.content_hash(norm(item.text)),
        "engagement": item.engagement.model_dump(mode="json"),
        "raw": item.raw,
        "created_at": item.created_at,
    })
    counters["inserted" if item_id else "skipped_existing"] += 1


def run(**_) -> dict:
    counters = {"inserted": 0, "skipped_existing": 0}
    fetched = {"twitter_csv": 0, "twitter_live": 0, "reddit": 0}

    # X backfill (CSV is the main X source locally — user decision 2026-07-03)
    csv_path = settings.registry["sources"]["twitter"].get("csv_backfill")
    if csv_path:
        for item in twitter.iter_csv_backfill(csv_path):
            fetched["twitter_csv"] += 1
            _store(item, counters)

    # Reddit live
    reddit_items, reddit_health = reddit.fetch_live()
    for item in reddit_items:
        fetched["reddit"] += 1
        _store(item, counters)

    # X live — capped, degrade-to-note
    live_items, x_live_note = twitter.fetch_live_capped()
    for item in live_items:
        fetched["twitter_live"] += 1
        _store(item, counters)

    for source, n in (("twitter", fetched["twitter_csv"] + fetched["twitter_live"]),
                      ("reddit", fetched["reddit"])):
        repo.advance_state("ingest", source, watermark=repo.now_utc(), items=n)

    return {"fetched": fetched, **counters,
            "x_live_note": x_live_note, "reddit_health": reddit_health}
