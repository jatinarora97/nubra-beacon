"""Stage ① INGEST — CSV backfill + Reddit live + X live (capped). LLD-02 §§1–4.

Idempotent: insert-if-absent on (source, external_id); reruns insert ~0.
"""
from __future__ import annotations

from community.config.log import get_logger
from community.config.settings import settings
from community.clean.normalize import norm
from community.scrape import reddit, twitter
from community.scrape.base import SocialItem
from community.store import db, repositories as repo


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


log = get_logger("scrape")


def run(daily: bool = False, **_) -> dict:
    """daily=True adds the once-a-day sorts (top = past-24h best) to the hourly
    new+hot+rising feeds; the scheduler passes it on the morning build."""
    counters = {"inserted": 0, "skipped_existing": 0}
    fetched = {"twitter_csv": 0, "twitter_live": 0, "reddit": 0}
    reddit_by_category: dict[str, int] = {}

    # X backfill (CSV is the main X source locally — user decision 2026-07-03).
    # ONE-TIME: once any CSV row is in the DB, skip the whole file — re-reading
    # it hourly re-asserted stale June author fields (followers/verified) over
    # fresher live-X values and bumped last_seen for 400 authors every run.
    csv_path = settings.registry["sources"]["twitter"].get("csv_backfill")
    csv_note = None
    if csv_path:
        already = db.one(
            "SELECT 1 AS x FROM social_items "
            "WHERE source='twitter' AND raw->>'backfill' IS NOT NULL LIMIT 1")
        if already:
            # keep the counter an int — it is summed for the watermark below
            csv_note = "already backfilled (skipped)"
            log.info("X csv backfill: already in DB — skipped")
        else:
            log.info("X csv backfill: importing %s", csv_path)
            for item in twitter.iter_csv_backfill(csv_path):
                fetched["twitter_csv"] += 1
                _store(item, counters)
            log.info("X csv backfill: %d rows imported", fetched["twitter_csv"])

    # Reddit live — all feeds: hourly new+hot+rising, +top when daily
    r_reg = settings.registry["sources"]["reddit"]
    sorts = list(r_reg.get("sort_types_hourly", ["new"]))
    if daily:
        sorts += list(r_reg.get("sort_types_daily_extra", []))
    log.info("reddit: fetching feeds %s across watched subs (daily=%s)", sorts, daily)
    reddit_items, reddit_health = reddit.fetch_live(sorts=sorts)
    log.info("reddit: %d items fetched (health: %s)", len(reddit_items),
             str(reddit_health)[:150])
    for item in reddit_items:
        fetched["reddit"] += 1
        cat = (item.raw or {}).get("category", "uncategorized")
        reddit_by_category[cat] = reddit_by_category.get(cat, 0) + 1
        _store(item, counters)

    # X live — capped, degrade-to-note
    log.info("X live: fetching (budget-capped)")
    live_items, x_live_note = twitter.fetch_live_capped()
    log.info("X live: %d items — %s", len(live_items), (x_live_note or "ok")[:150])
    for item in live_items:
        fetched["twitter_live"] += 1
        _store(item, counters)

    for source, n in (("twitter", fetched["twitter_csv"] + fetched["twitter_live"]),
                      ("reddit", fetched["reddit"])):
        repo.advance_state("ingest", source, watermark=repo.now_utc(), items=n)

    # engagement refresh for action-candidate threads (work plan B4) — a
    # failure here must never fail the scrape stage
    try:
        from community.scrape import refresh
        log.info("engagement refresh: starting")
        refresh_stats = refresh.run()
        log.info("engagement refresh: %s", refresh_stats)
    except Exception:  # noqa: BLE001
        log.exception("engagement refresh failed — scrape stage continues")
        refresh_stats = {"error": "see traceback in log"}

    # reddit keyword search (2026-07-08) — watched keywords fetch across ALL of
    # reddit, not just watched subs; same never-break-the-stage contract
    try:
        from community.scrape import keyword_search
        log.info("keyword search: starting")
        keyword_stats = keyword_search.run()
        log.info("keyword search: %s", keyword_stats)
    except Exception:  # noqa: BLE001
        log.exception("keyword search failed — scrape stage continues")
        keyword_stats = {"error": "see traceback in log"}

    if csv_note:
        fetched["twitter_csv_note"] = csv_note
    return {"fetched": fetched, "reddit_by_category": reddit_by_category,
            "reddit_sorts": sorts, **counters,
            "x_live_note": x_live_note, "reddit_health": reddit_health,
            "engagement_refresh": refresh_stats,
            "keyword_search": keyword_stats}
