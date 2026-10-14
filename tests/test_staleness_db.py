"""The staleness report's SQL against a REAL Postgres (embedded, throwaway) with the project's real migrations.

Skipped where the embedded server is not installed (`pip install pgserver`); it is what proves the queries run
and count correctly, which the mocked tests in test_staleness.py cannot.
"""
from __future__ import annotations

import json
import pathlib
import sys
from types import SimpleNamespace

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.health import staleness  # noqa: E402
from community.store import db  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent

SEED = """
INSERT INTO authors (source, handle) VALUES ('twitter', 'tw_user'), ('reddit', 'rd_user');

-- twitter: a one-off CSV backfill 20 days ago (content 25+ days old) ...
INSERT INTO social_items (source, source_type, external_id, author_id, text, content_hash, raw, created_at, ingested_at)
SELECT 'twitter', 'tweet', 'csv' || g, (SELECT author_id FROM authors WHERE handle = 'tw_user'), 'csv tweet ' || g,
       repeat('a', 64), jsonb_build_object('backfill', 'twitter_pulse.csv'),
       now() - interval '25 days' - g * interval '1 hour', now() - interval '20 days'
FROM generate_series(1, 50) g;
-- ... and the live API, which last delivered 9 days ago
INSERT INTO social_items (source, source_type, external_id, author_id, text, content_hash, raw, created_at, ingested_at)
SELECT 'twitter', 'tweet', 'live' || g, (SELECT author_id FROM authors WHERE handle = 'tw_user'), 'live tweet ' || g,
       repeat('b', 64), jsonb_build_object('live', true, 'query', 'nubra since:2026-10-01'),
       now() - interval '9 days' - interval '2 hours', now() - interval '9 days'
FROM generate_series(1, 5) g;

-- reddit via the old scraper, 15 days ago: Zerodha and IndianStockMarket, 10 posts + 10 comments each
INSERT INTO social_items (source, source_type, external_id, author_id, text, content_hash, raw, created_at, ingested_at)
SELECT 'reddit', CASE WHEN g <= 10 THEN 'post' ELSE 'comment' END, 'old_' || s || '_' || g,
       (SELECT author_id FROM authors WHERE handle = 'rd_user'), 'old ' || s || ' ' || g, repeat('c', 64),
       jsonb_build_object('subreddit', s, 'category', 'brokers', 'via', 'zanshash_scraper'),
       now() - interval '15 days' - interval '3 hours', now() - interval '15 days'
FROM unnest(ARRAY['Zerodha', 'IndianStockMarket']) s, generate_series(1, 20) g;

-- reddit via Apify, 3 hours ago, content 5 h old: IndianStockMarket 10 posts + 30 comments; yugioh 2 keyword posts
INSERT INTO social_items (source, source_type, external_id, author_id, text, content_hash, raw, created_at, ingested_at)
SELECT 'reddit', CASE WHEN g <= 10 THEN 'post' ELSE 'comment' END, 'new_' || g,
       (SELECT author_id FROM authors WHERE handle = 'rd_user'), 'new ' || g, repeat('d', 64),
       jsonb_build_object('subreddit', 'IndianStockMarket', 'category', 'market_trading', 'via', 'apify_reddit_pro'),
       now() - interval '8 hours', now() - interval '3 hours'
FROM generate_series(1, 40) g;
INSERT INTO social_items (source, source_type, external_id, author_id, text, content_hash, raw, created_at, ingested_at)
SELECT 'reddit', 'post', 'kw_' || g, (SELECT author_id FROM authors WHERE handle = 'rd_user'), 'kw ' || g,
       repeat('e', 64), jsonb_build_object('subreddit', 'yugioh', 'category', 'keyword', 'via', 'apify_reddit_pro'),
       now() - interval '8 hours', now() - interval '3 hours'
FROM generate_series(1, 2) g;

-- 10 of the 42 fresh canonical items are enriched
INSERT INTO item_enrichment (item_id, ingested_at, intent, topic_key, model)
SELECT item_id, ingested_at, 'question', 't', 'test' FROM social_items
WHERE external_id LIKE 'new\\_%' AND item_id IN (SELECT item_id FROM social_items WHERE external_id LIKE 'new\\_%' LIMIT 10);

INSERT INTO watch_sources (kind, value, category) VALUES
  ('subreddit', 'Zerodha', 'brokers'), ('subreddit', 'IndianStockMarket', 'market_trading'),
  ('subreddit', 'groww', 'brokers'), ('x_handle', 'someone', 'brokers'), ('x_hashtag', 'nubra', NULL);

INSERT INTO pipeline_state (stage, source, last_success_at, items_last_run) VALUES
  ('ingest', 'reddit_apify', now() - interval '3 hours', 699), ('enrich', '', now() - interval '1 hour', 10);
INSERT INTO pipeline_state (stage, source, last_success_at, last_error, last_error_at) VALUES
  ('ingest', 'twitter', now() - interval '9 days', 'RuntimeError: 402 credits exhausted', now() - interval '1 hour');

INSERT INTO conversations (source, thread_id, item_count, last_seen) VALUES
  ('reddit', 't3_a', 5, now() - interval '3 hours'), ('twitter', 'tw1', 2, now() - interval '9 days');
INSERT INTO opportunities (source, thread_id, day, priority) VALUES ('reddit', 't3_a', current_date, 70);
INSERT INTO topic_daily (topic_key, day, count) VALUES ('t', current_date, 3);
"""


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    uri = server.get_uri()
    sys.path.insert(0, str(ROOT))
    import migrations.run_migrations as runner
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner, "settings", SimpleNamespace(db_url=uri))
        mp.setattr(db, "settings", SimpleNamespace(db_url=uri))
        runner.main()
        with psycopg.connect(uri, autocommit=True) as c:
            # partitions are pre-created only through Oct 2026 (the cliff itself): catch-alls keep this test
            # independent of the date it is run on
            c.execute("CREATE TABLE social_items_catchall PARTITION OF social_items DEFAULT")
            c.execute("CREATE TABLE item_enrichment_catchall PARTITION OF item_enrichment DEFAULT")
            c.execute(SEED)
        yield staleness.collect(days=30)
    server.cleanup()


def channel(world, source, name):
    return next(c for c in world["channels"] if c["source"] == source and c["channel"] == name)


def test_every_query_in_the_report_runs_against_the_real_schema(world):
    assert world["errors"] == {}


def test_row_counts_by_source_and_by_channel(world):
    assert world["summary"]["twitter"]["total"] == 55
    assert world["summary"]["reddit"]["total"] == 82
    assert channel(world, "twitter", "csv_backfill")["rows"] == 50
    assert channel(world, "twitter", "live_api")["rows"] == 5
    assert channel(world, "reddit", "zanshash_scraper")["rows"] == 40
    assert channel(world, "reddit", "apify_reddit_pro")["rows"] == 42


def test_the_verdicts_separate_a_dead_live_feed_from_fresh_reddit(world):
    by = {v["source"]: v for v in world["verdicts"]}
    assert by["reddit"]["status"] == "ok"
    assert by["twitter"]["status"] == "STALE"
    assert "live X API last delivered" in by["twitter"]["why"]


def test_arrival_windows_and_content_age_at_arrival(world):
    reddit = world["summary"]["reddit"]
    assert reddit["last_24h"] == 42 and reddit["last_7d"] == 42 and reddit["last_30d"] == 82
    assert world["summary"]["twitter"]["last_7d"] == 0            # the live feed stopped 9 days ago
    assert 4.9 < world["lag"]["reddit"]["median_h"] < 5.1         # 3 h ago, content 8 h old -> 5 h at arrival


def test_per_day_table_covers_the_window_and_splits_the_channels(world):
    assert len(world["daily"]) == 31
    assert sum(d["twitter_csv"] for d in world["daily"]) == 50
    assert sum(d["twitter_live"] for d in world["daily"]) == 5
    assert sum(d["reddit_posts"] for d in world["daily"]) == 32      # 10 old + 10 old + 10 new + 2 keyword
    assert sum(d["reddit_comments"] for d in world["daily"]) == 50   # 10 + 10 + 30
    empty = [d for d in world["daily"] if not (d["twitter_csv"] + d["twitter_live"] + d["reddit_posts"])]
    assert len(empty) >= 25                                           # most days had nothing arrive


def test_watched_subreddits_with_the_window_and_the_newest_post_ever(world):
    # a 30-day window sees the old scraper's rows too; a silent subreddit is one with no posts at all
    subs = {s["sub"]: s for s in world["subreddits"]}
    assert subs["groww"]["posts"] == 0 and subs["groww"]["newest_post"] is None
    assert subs["Zerodha"]["posts"] == 10
    assert subs["IndianStockMarket"]["posts"] == 20
    assert world["subreddits"][0]["sub"] == "groww"                   # silent first
    assert [o["sub"] for o in world["other_subreddits"]] == ["yugioh"]


def test_the_short_window_makes_zerodha_silent_but_remembers_its_last_post(tmp_path_factory, world):
    short = staleness.collect(days=7)
    z = next(s for s in short["subreddits"] if s["sub"] == "Zerodha")
    assert z["posts"] == 0 and z["newest_post"] is not None


def test_enrichment_backlog_and_downstream_freshness(world):
    e = world["enrichment"]["reddit"]
    assert (e["items"], e["enriched"]) == (42, 10)
    assert e["oldest_unenriched"] is not None
    assert world["conversations"]["reddit"]["threads"] == 1
    assert world["opportunities"]["reddit"]["suggested"] == 1
    assert world["topics_newest_day"] is not None


def test_pipeline_state_shows_the_twitter_402(world):
    twitter = next(p for p in world["pipeline"] if p["source"] == "twitter")
    assert "402" in twitter["last_error"]


def test_the_partition_horizon_is_reported(world):
    assert {p["parent"] for p in world["partitions"]} >= {"social_items", "item_enrichment"}
    assert all(p["upper_bound"] is not None for p in world["partitions"] if p["parent"] == "social_items")


def test_the_full_text_report_and_the_json_both_render(world):
    text = staleness.render(world)
    for needle in ("twitter  STALE", "reddit   ok", "csv_backfill", "live_api", "apify_reddit_pro",
                   "1 of 3 watched subreddits produced no posts", "402 credits exhausted", "days left"):
        assert needle in text, needle
    text.encode("ascii")
    json.dumps(world, default=str)
