"""A draft attempt that gets no draft is remembered, proven against a REAL Postgres (embedded, throwaway) with the
project's real migrations. Skipped where `pgserver` is not installed.

Before migration 0025 a thread the model skipped (or whose drafts failed every attempt) kept `brand_reply` NULL and
was picked again by every draft run, top priority first, so a few such threads could fill all `max_drafted` slots
every hour and starve better ones.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.config.settings import settings  # noqa: E402
from community.recommend import draft, score  # noqa: E402
from community.store import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TODAY = datetime.now(timezone.utc).date()
SLOTS = settings.registry["recommend"]["max_drafted"]


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
        yield url
    server.cleanup()


def sql(url, statement, params=None):
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.execute(statement, params)
        return cur.fetchall() if cur.description else None


def seed(url, *threads, source="twitter"):
    """threads: (thread_id, priority). Replaces every opportunity."""
    sql(url, "DELETE FROM opportunities")
    for tid, priority in threads:
        sql(url, "INSERT INTO opportunities (source, thread_id, day, priority, matched_insight) VALUES (%s,%s,%s,%s,%s)",
            (source, tid, TODAY, priority, json.dumps({"kind": "question", "tid": tid})))


def row(url, tid):
    return sql(url, "SELECT draft_attempts, draft_last_outcome, draft_attempted_at IS NOT NULL, "
                    "brand_reply IS NOT NULL FROM opportunities WHERE thread_id=%s", (tid,))[0]


def age(url, tid, hours=25):
    sql(url, "UPDATE opportunities SET draft_attempted_at = now() - make_interval(hours => %s) WHERE thread_id=%s",
        (hours, tid))


def stage(modes):
    """Run the real draft stage. modes: thread_id -> 'ok' | 'skip' | 'bad' ('bad' = a reply too long for one tweet,
    which the validator rejects on every attempt). Returns (stats, threads the model was called for)."""
    called = []

    def fake_complete(model, system, user, max_tokens=0):
        tid = re.search(r'"tid": "(\w+)"', user).group(1)
        called.append(tid)
        mode = modes[tid]
        if mode == "skip":
            return json.dumps({"skip_reason": "not a thread worth joining"}), {}
        rep = "x" * 400 if mode == "bad" else "honest answer: read the charges line by line first"
        return json.dumps({"brand": {"text": "A plain factual reply.", "features_cited": []},
                           "rep": {"text": rep, "features_cited": []}, "skip_reason": None}), {}

    with patch.object(draft, "complete", fake_complete), \
         patch.object(draft.compliance, "check", return_value=(True, [])), \
         patch.object(draft.features, "catalog_for_prompt", return_value=[{"id": "f_1", "feature": "x",
                      "description": "y", "status": "live", "category": "c"}]), \
         patch.object(draft.features, "current_version", return_value="v2"), \
         patch.object(draft, "_content_proposals", return_value=0):
        stats = draft.run()
    return stats, called


def test_the_migration_gives_existing_and_new_rows_a_clean_slate(uri):
    seed(uri, ("t1", 80))
    assert row(uri, "t1") == (0, None, False, False)


def test_a_thread_the_model_skips_is_remembered_and_not_picked_again(uri):
    seed(uri, ("t1", 80))
    stats, called = stage({"t1": "skip"})
    assert (stats["skipped"], stats["drafted"], called) == (1, 0, ["t1"])
    assert row(uri, "t1") == (1, "skipped", True, False)

    stats, called = stage({"t1": "skip"})
    assert called == [] and stats["skipped"] == 0           # no model call, no slot used


def test_failing_drafts_are_retried_only_after_a_day_and_parked_after_three_failed_runs(uri):
    assert (draft.MAX_DRAFT_ATTEMPTS, draft.RETRY_AFTER_HOURS) == (3, 24)
    seed(uri, ("t1", 80))
    stats, called = stage({"t1": "bad"})
    assert stats["dropped"] == 1 and called == ["t1"] * 3        # three attempts inside the run, as before
    assert row(uri, "t1") == (1, "dropped", True, False)

    assert stage({"t1": "bad"})[1] == []                        # the next hourly run leaves it alone

    for attempts_after in (2, 3):
        age(uri, "t1")                                          # a day passes
        assert stage({"t1": "bad"})[1] == ["t1"] * 3
        assert row(uri, "t1")[:2] == (attempts_after, "dropped")

    age(uri, "t1")
    assert stage({"t1": "bad"})[1] == []                        # three failed runs: parked for good


def test_a_retry_that_works_is_drafted_and_the_marker_is_cleared(uri):
    seed(uri, ("t1", 80))
    stage({"t1": "bad"})
    age(uri, "t1")
    stats, called = stage({"t1": "ok"})
    assert (stats["drafted"], called) == (1, ["t1"])
    attempts, outcome, _, has_draft = row(uri, "t1")
    assert has_draft and outcome is None
    assert attempts == 1            # it counts the runs that ended WITHOUT a draft, so the success adds nothing


def test_parked_threads_no_longer_fill_the_run_so_better_work_gets_its_slots(uri):
    stuck = [(f"s{i}", 90 - i) for i in range(SLOTS)]           # the best-scored threads are the ones the model skips
    fresh = [("f1", 60), ("f2", 59)]                            # still above the draft bar (40), just lower
    seed(uri, *stuck, *fresh)
    modes = {**{tid: "skip" for tid, _ in stuck}, "f1": "ok", "f2": "ok"}

    stats, called = stage(modes)                                # run 1: the skip-prone threads take every slot
    assert stats["drafted"] == 0 and sorted(called) == sorted(t for t, _ in stuck)

    stats, called = stage(modes)                                # run 2: before 0025 they would take them all again
    assert stats["drafted"] == 2 and sorted(called) == ["f1", "f2"]


def test_a_transient_model_error_is_not_counted_against_the_thread(uri):
    seed(uri, ("t1", 80))
    with patch.object(draft, "complete", side_effect=RuntimeError("API overloaded")), \
         patch.object(draft.features, "catalog_for_prompt", return_value=[{"id": "f_1"}]), \
         patch.object(draft.features, "current_version", return_value="v2"):
        with pytest.raises(RuntimeError):
            draft.run()
    assert row(uri, "t1") == (0, None, False, False)
    assert stage({"t1": "ok"})[0]["drafted"] == 1


def test_rescoring_a_parked_thread_does_not_reopen_it(uri):
    seed(uri, ("t1", 45))
    stage({"t1": "skip"})
    sql(uri, "INSERT INTO conversations (source, thread_id, item_count, velocity, last_seen) "
             "VALUES ('twitter', 't1', 1, 0, now())")
    enriched = [{"item_id": 1, "text": "why does my broker keep failing", "followers": 100000,
                 "engagement": {"native": {"likes": 200}}, "intent": "complaint",
                 "entities": {"broker": "otherbroker", "issue_type": "outage"}, "topic_key": None, "is_noise": False}]
    with patch.object(score, "_thread_rows", return_value=enriched):
        stats = score.run()
    assert stats["persisted"] == 1
    assert sql(uri, "SELECT priority FROM opportunities WHERE thread_id='t1'")[0][0] > 45     # the upsert really ran
    assert row(uri, "t1") == (1, "skipped", True, False)                                      # and left the marker alone
    assert stage({"t1": "skip"})[1] == []


def test_a_parked_thread_can_be_reopened_with_one_statement(uri):
    seed(uri, ("t1", 80))
    stage({"t1": "skip"})
    sql(uri, "UPDATE opportunities SET draft_attempts=0, draft_last_outcome=NULL, draft_attempted_at=NULL "
             "WHERE source='twitter' AND brand_reply IS NULL")
    assert stage({"t1": "ok"})[0]["drafted"] == 1


def test_only_known_outcomes_are_accepted(uri):
    seed(uri, ("t1", 80))
    with pytest.raises(psycopg.errors.CheckViolation):
        sql(uri, "UPDATE opportunities SET draft_last_outcome='whatever' WHERE thread_id='t1'")
