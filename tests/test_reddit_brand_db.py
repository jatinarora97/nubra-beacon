"""A brand comment found by the brand pass shows up on the Nubra Mentions page, proven against a REAL Postgres
(embedded, throwaway) with the project's real migrations. Skipped where `pgserver` is not installed.

The page counts stored items that mention Nubra and are not flagged as noise; it needs no enrichment to show one,
so a mention is visible as soon as the pass has stored it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.scrape import extra_sources, reddit_apify  # noqa: E402
from community.store import db  # noqa: E402
from tests.test_reddit_brand import SUBS, comment, post  # noqa: E402
from tests.test_reddit_apify_pro import ACTOR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def uri(tmp_path_factory):
    server = pgserver.get_server(tmp_path_factory.mktemp("pg"), cleanup_mode="stop")
    url = server.get_uri()
    sys.path.insert(0, str(ROOT))
    import migrations.run_migrations as runner
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner, "settings", SimpleNamespace(db_url=url))
        mp.setattr(db, "settings", SimpleNamespace(db_url=url))
        runner.main()
        with psycopg.connect(url, autocommit=True) as c:
            c.execute("CREATE TABLE social_items_catchall PARTITION OF social_items DEFAULT")
            c.execute("CREATE TABLE item_enrichment_catchall PARTITION OF item_enrichment DEFAULT")
        yield url
    server.cleanup()


def sql(url, statement, params=None):
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.execute(statement, params)
        return cur.fetchall() if cur.description else None


ROWS = {
    "IndianStockMarket": [comment("pgft0av", "1x4q7w3", "IndianStockMarket",
                                  "Nubra has a python SDK for this (I work at Nubra)", author="candlesandstock")],
    "algotrading": [post("p9", "algotrading", "Built charts on Nubra", "options chain walkthrough", author="teamuser2")],
    "all": [post("v1", "ladakh", "Nubra valley in November"),
            comment("c2", "v2", "XEV9S", "my recent trip to Ladakh, Nubra was stunning")],
}


def store_a_brand_pass(uri):
    with patch.object(reddit_apify, "_run_actor",
                      side_effect=lambda a, p, **k: list(ROWS.get(p.get("withinCommunity") or "all", []))), \
         patch.object(reddit_apify, "_token", return_value="tok"), \
         patch.object(reddit_apify, "_subreddits", return_value=SUBS), \
         patch.object(reddit_apify, "brand_queries", return_value=["nubra"]):
        counters = {"inserted": 0, "skipped_existing": 0}
        for item in reddit_apify.collect_brand({"enabled": True, "actor": ACTOR})[0]:
            extra_sources._store(item, counters)
    return counters


def test_the_pass_stores_the_brand_items_and_none_of_the_travel_noise(uri):
    counters = store_a_brand_pass(uri)
    assert counters == {"inserted": 2, "skipped_existing": 0}
    rows = sql(uri, "SELECT source_type, external_id, thread_id FROM social_items WHERE source='reddit' "
                    "ORDER BY external_id")
    assert rows == [("comment", "t1_pgft0av", "t3_1x4q7w3"), ("post", "t3_p9", "t3_p9")]       # t1_ sorts before t3_


def test_running_the_pass_again_adds_nothing(uri):
    assert store_a_brand_pass(uri) == {"inserted": 0, "skipped_existing": 2}


def test_the_nubra_mentions_page_shows_them_straight_away(uri):
    read_api = pytest.importorskip("community.api.read_api")
    out = read_api.nubra_mentions()
    assert out["kpis"]["mentions_window"] == 2
    authors = {p["author"]: p["text"] for p in out["positives"]}
    assert set(authors) == {"candlesandstock", "teamuser2"}
    assert "(I work at Nubra)" in authors["candlesandstock"]
    assert all(p["source"] == "reddit" for p in out["positives"])


def test_a_noise_flagged_mention_is_still_hidden_from_the_page(uri):
    read_api = pytest.importorskip("community.api.read_api")
    item_id = sql(uri, "SELECT item_id FROM social_items WHERE external_id='t3_p9'")[0][0]
    sql(uri, "INSERT INTO item_enrichment (item_id, ingested_at, intent, topic_key, is_noise, model) "
             "VALUES (%s, now(), 'spam', 'x', true, 'm')", (item_id,))
    out = read_api.nubra_mentions()
    assert out["kpis"]["mentions_window"] == 1
    assert [p["author"] for p in out["positives"]] == ["candlesandstock"]
