"""Five recommendations, proven against a REAL Postgres (embedded, throwaway) with the project's real migrations.

Skipped where `pgserver` is not installed. The content-brief rank rule lives in the database
(`CHECK (rank BETWEEN 1 AND 3)` until migration 0024), which only a real database can prove.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.compose import render  # noqa: E402
from community.recommend import draft  # noqa: E402
from community.store import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).date()

FAMILIES = ["video_short", "carousel", "text_post", "thread"]
PLATFORMS = ["instagram_reels", "linkedin_post", "x_thread", "x_post"]


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
            c.execute("INSERT INTO topic_taxonomy (topic_key, label) VALUES ('sip', 'SIP')")
            c.execute("INSERT INTO topic_daily (topic_key, day, count) VALUES ('sip', %s, 9)", (TODAY,))
            for i in range(1, 8):    # seven open opportunities, priorities 10..70
                c.execute("INSERT INTO opportunities (source, thread_id, day, priority, matched_insight) "
                          "VALUES ('reddit', %s, %s, %s, '{\"kind\": \"question\"}')", (f"t{i}", TODAY, i * 10))
        yield url
    server.cleanup()


def sql(url, statement, params=None):
    with psycopg.connect(url, autocommit=True) as c:
        return c.execute(statement, params).fetchall() if statement.lstrip().upper().startswith("SELECT") else \
            c.execute(statement, params)


def insert_proposal(url, rank):
    sql(url, "INSERT INTO content_proposals (day, rank, format, hook, rides_signal) VALUES (%s, %s, 'x', 'h', '{}')",
        (TODAY, rank))


def test_the_database_now_allows_content_brief_ranks_one_to_five(uri):
    sql(uri, "DELETE FROM content_proposals")
    for rank in (1, 2, 3, 4, 5):
        insert_proposal(uri, rank)
    assert [r[0] for r in sql(uri, "SELECT rank FROM content_proposals ORDER BY rank")] == [1, 2, 3, 4, 5]


def test_ranks_outside_one_to_five_are_still_rejected(uri):
    for rank in (0, 6):
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_proposal(uri, rank)


def candidate(i):
    return {"format_family": FAMILIES[i % 4], "platform": PLATFORMS[i % 4], "treatment": f"treatment {i}",
            "platform_why": "fits", "hook": f"hook {i}",
            "brief": {"beats": ["a"], "caption": "c", "hashtags": [], "cta": "x", "visual_direction": "v"},
            "why": "signal", "recommended_window": "09:00-10:00 IST",
            "scores": {"impact": 0.9 - 0.05 * i, "reach_fit": 0.5, "timeliness": 0.5, "effort_inv": 0.5,
                       "on_brand": 0.5}}


def test_a_day_now_produces_five_briefs_in_score_order(uri):
    sql(uri, "DELETE FROM content_proposals")
    answer = json.dumps({"candidates": [candidate(i) for i in range(draft.CANDIDATES_ASKED)]})
    with patch.object(draft, "complete", return_value=(answer, {})) as llm, \
         patch.object(draft.compliance, "check", return_value=(True, [])):
        stored = draft._content_proposals([{"id": "f_1"}])
    assert stored == 5
    rows = sql(uri, "SELECT rank, hook FROM content_proposals ORDER BY rank")
    assert rows == [(1, "hook 0"), (2, "hook 1"), (3, "hook 2"), (4, "hook 3"), (5, "hook 4")]
    assert llm.call_args.kwargs["max_tokens"] == draft.CONTENT_MAX_TOKENS
    assert f"exactly {draft.CANDIDATES_ASKED} candidates" in llm.call_args.args[1]


def test_the_heads_up_summary_lists_five_opportunities_best_first(uri):
    rows = render._top_standing({"question": "questions"})
    assert [r["priority"] for r in rows] == [70, 60, 50, 40, 30]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4, 5]
    assert rows[0]["kind_label"] == "questions"


def test_the_dashboard_query_returns_five_top_actions_best_first(uri):
    read_api = pytest.importorskip("community.api.read_api")
    rows = read_api._top_action_rows()
    assert [r["priority"] for r in rows] == [70, 60, 50, 40, 30]
