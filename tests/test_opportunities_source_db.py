"""The Opportunities page can be filtered by source, proven against a REAL Postgres (embedded, throwaway) with the
project's real migrations. Skipped where `pgserver` is not installed.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.store import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).date()


@pytest.fixture(scope="module")
def read_api(tmp_path_factory):
    module = pytest.importorskip("community.api.read_api")
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
            rows = [("twitter", "1700000000000000001", 90, "suggested"), ("twitter", "1700000000000000002", 50, "suggested"),
                    ("twitter", "1700000000000000003", 70, "dismissed"), ("reddit", "t3_abc", 80, "suggested"),
                    ("instagram", "ig1", 60, "suggested")]
            for source, thread, priority, status in rows:
                c.execute("INSERT INTO opportunities (source, thread_id, day, priority, status, matched_insight) "
                          "VALUES (%s, %s, %s, %s, %s, '{\"kind\": \"question\"}')",
                          (source, thread, TODAY, priority, status))
        yield module
    server.cleanup()


def listing(read_api, **kw):
    args = {"response": SimpleNamespace(headers={}), "date_": None, "status": None, "min_priority": 0, "window": None,
            "from_ts": None, "to_ts": None, "source": None, "limit": 50}
    return read_api.opportunities(**{**args, **kw})


def test_without_a_source_every_source_is_listed_best_first(read_api):
    rows = listing(read_api)
    assert [r["priority"] for r in rows] == [90, 80, 70, 60, 50]
    assert {r["source"] for r in rows} == {"twitter", "reddit", "instagram"}


def test_a_source_filter_returns_only_that_source(read_api):
    rows = listing(read_api, source="twitter")
    assert {r["source"] for r in rows} == {"twitter"}
    assert [r["priority"] for r in rows] == [90, 70, 50]
    assert [r["priority"] for r in listing(read_api, source="reddit")] == [80]


def test_the_source_filter_combines_with_the_status_tab(read_api):
    assert [r["priority"] for r in listing(read_api, source="twitter", status="suggested")] == [90, 50]
    assert [r["priority"] for r in listing(read_api, source="twitter", status="dismissed")] == [70]


def test_a_source_with_no_opportunities_returns_an_empty_list_not_everything(read_api):
    assert listing(read_api, source="youtube") == []


def test_every_row_says_which_source_it_came_from(read_api):
    assert all(r.get("source") for r in listing(read_api))


def test_a_hostile_source_value_is_just_a_value(read_api):
    assert listing(read_api, source="twitter' OR '1'='1") == []
    assert len(listing(read_api)) == 5         # and nothing was harmed


def test_the_overview_top_actions_keep_their_source_for_the_badge(read_api):
    with patch.object(read_api, "_freshness", return_value={}):
        top = read_api.overview()["top_actions"]
    assert [a["source"] for a in top][:2] == ["twitter", "reddit"]
    assert "brand_reply" not in top[0]          # the rest of the overview's slimming is unchanged
