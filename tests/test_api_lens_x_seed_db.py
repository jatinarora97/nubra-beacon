"""X (Twitter) is a seed venue in the content queue, proven against a REAL Postgres (embedded, throwaway) with the
project's real migrations. Skipped where `pgserver` is not installed.

"Target thread - post this reply there" appears on a queue card when the brief is a `seed_reply` with a `seed_url`.
Until 2026-10-15 only Reddit, broker forums and Stack Overflow could produce one: evidence from X was never marked
seedable, the prompt told X to write standalone posts only, and the venue map rejected any other seed target.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pgserver = pytest.importorskip("pgserver")
import psycopg  # noqa: E402

from community.config.settings import settings  # noqa: E402
from community.social_recommend import api_lens  # noqa: E402
from community.store import db  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TWEET = "https://x.com/someone/status/1700000000000000001"
TWEET_2 = "https://x.com/other/status/1700000000000000002"
POST = "https://www.reddit.com/r/IndiaAlgoTrading/comments/abc/how_do_i_place_orders/"


class Feat:
    def __init__(self, fid, segment):
        self.id, self.segment = fid, segment

    def model_dump(self):
        return {"id": self.id, "segment": self.segment, "name": "Option chain API"}


CTX = SimpleNamespace(version="ctx-1", features=[Feat("api_1", "api"), Feat("shared_1", "shared")])


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


@pytest.fixture(autouse=True)
def clean(uri):
    sql(uri, "TRUNCATE social_recommendations, social_recommendation_runs, api_trader_items, item_enrichment, "
             "social_items, authors RESTART IDENTITY CASCADE")
    sql(uri, "INSERT INTO authors (source, handle) VALUES ('twitter','t'), ('reddit','r'), ('community_forum','f')")


def sql(url, statement, params=None):
    with psycopg.connect(url, autocommit=True) as c:
        cur = c.execute(statement, params)
        return cur.fetchall() if cur.description else None


def add_item(uri, source, text, url, *, hours_ago=1.0, score=10.0, kind="guidance_seeking", intent="question",
             lens="api"):
    """One piece of evidence. lens 'api' -> api_trader_items row; lens 'general' -> item_enrichment row only."""
    item_id = sql(uri,
                  "INSERT INTO social_items (source, source_type, external_id, thread_id, author_id, text, "
                  "content_hash, raw, url, engagement, created_at) VALUES (%s, 'post', %s, %s, "
                  "(SELECT author_id FROM authors WHERE source=%s), %s, md5(random()::text) || md5(random()::text), "
                  "'{}', %s, %s, now() - make_interval(secs => %s)) RETURNING item_id",
                  (source, url or text[:20], url or text[:20], source, text, url, json.dumps({"score": score}),
                   hours_ago * 3600))[0][0]
    sql(uri, "INSERT INTO item_enrichment (item_id, ingested_at, intent, topic_key, model) "
             "VALUES (%s, now(), %s, 'api', 'x')", (item_id, intent))
    if lens == "api":
        sql(uri, "INSERT INTO api_trader_items (item_id, stage, kind, gist) VALUES (%s, 'exploring', %s, %s)",
            (item_id, kind, f"gist of {text[:30]}"))
    return item_id


def by_url(evidence):
    return {e["url"]: e for e in evidence}


# ── evidence: which X posts can be a target ────────────────────────────────

def test_a_fresh_x_question_is_a_seedable_target_for_the_api_lens(uri):
    add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    ev = by_url(api_lens._evidence())
    assert ev[TWEET]["seedable"] is True and ev[TWEET]["source"] == "twitter"


def test_reddit_evidence_is_unchanged(uri):
    add_item(uri, "reddit", "how do I place orders through an api?", POST)
    assert by_url(api_lens._evidence())[POST]["seedable"] is True


def test_an_old_x_post_is_no_target_because_a_reply_to_it_would_be_pointless(uri):
    add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET,
             hours_ago=24 * (api_lens.X_SEED_MAX_AGE_DAYS + 2))
    ev = by_url(api_lens._evidence())
    assert not ev.get(TWEET, {}).get("seedable")           # may still inspire a brief, but is not a target


def test_x_posts_that_are_not_questions_or_friction_are_not_targets(uri):
    add_item(uri, "twitter", "look at my algo dashboard", TWEET, kind="showcase")
    assert not by_url(api_lens._evidence())[TWEET]["seedable"]


def test_an_x_post_without_a_url_cannot_be_a_target(uri):
    add_item(uri, "twitter", "how do I place orders through an api with python?", None)
    assert not any(e["seedable"] and e["source"] == "twitter" for e in api_lens._evidence())


def test_a_post_that_names_nubra_is_never_a_target(uri):
    add_item(uri, "twitter", "nubra api docs are confusing, how do I place orders?", TWEET)
    assert TWEET not in by_url(api_lens._evidence())


def test_an_x_post_found_by_both_queries_appears_once_and_is_seedable(uri):
    add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    items = [e for e in api_lens._evidence() if e["url"] == TWEET]
    assert len(items) == 1 and items[0]["seedable"] is True


def test_x_targets_are_not_crowded_out_by_a_full_window_of_reddit_threads(uri):
    for i in range(45):                                    # more seedable Reddit threads than the window holds
        add_item(uri, "reddit", f"question {i} about orders via api", f"{POST}{i}", score=500 - i)
    add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET, score=1)
    add_item(uri, "twitter", "which api gives option chain data for free?", TWEET_2, score=1)
    ev = api_lens._evidence()
    reddit = [e for e in ev if e["source"] == "reddit"]
    assert len(reddit) == 40                               # the existing window is untouched
    assert {e["url"] for e in ev if e["source"] == "twitter" and e["seedable"]} == {TWEET, TWEET_2}


def test_the_retail_lens_gets_x_targets_too(uri):
    add_item(uri, "twitter", "which broker has the clearest option charges?", TWEET, lens="general",
             intent="question")
    add_item(uri, "twitter", "great day for the markets", TWEET_2, lens="general", intent="praise")
    ev = by_url(api_lens._evidence(lens=api_lens.GENERAL_LENS))
    assert ev[TWEET]["seedable"] is True
    assert not ev[TWEET_2]["seedable"]


# ── the prompt ─────────────────────────────────────────────────────────────

def test_the_prompt_lets_x_reply_into_a_tweet_and_keeps_it_to_one_tweet():
    text = " ".join(api_lens._SYSTEM.split())
    assert "x: format text_post, thread or seed_reply" in text
    assert "a reply to the given tweet" in text
    assert "ONE tweet" in text and "280" in text


def test_every_other_platform_norm_is_still_there():
    text = " ".join(api_lens._SYSTEM.split())
    for needle in ("reddit: format seed_reply or text_post", "linkedin: format text_post, image_post or carousel",
                   "forum: format seed_reply ONLY", "stackoverflow: format seed_reply ONLY"):
        assert needle in text


# ── top_up: what is stored, i.e. what the page shows ───────────────────────

def rec(platform, content_type, fmt, hook, *, seed_url=None, evidence=(), hashtags=(), key="k1", body="",
        features=("api_1",)):
    return {"recommendation_key": key, "platform": platform, "content_type": content_type, "format": fmt,
            "ai_brief": "write it", "title": f"title {key}", "hook": hook, "body": body, "cta": "",
            "hashtags": list(hashtags), "feature_ids": list(features), "evidence_item_ids": list(evidence),
            "seed_url": seed_url, "rationale": "because", "recommended_timing": "now", "priority_score": 80}


def top_up(uri, *recs, lens=api_lens.LENS):
    seen = {}

    def fake_complete(model, system, user, max_tokens=0):
        seen.update(system=system, user=user)
        return json.dumps({"recommendations": list(recs)}), {}

    with patch.dict("os.environ", {"API_TRADING_ENABLED": "true"}), \
         patch.object(api_lens, "settings", SimpleNamespace(registry=settings.registry, anthropic_api_key="k",
                                                            draft_model="m")), \
         patch.object(api_lens, "complete", fake_complete), \
         patch.object(api_lens, "compliance_check", return_value=(True, [])), \
         patch.object(api_lens, "_stackoverflow_evidence", return_value=[]), \
         patch.object(api_lens, "_created_today",          # its SQL needs the Asia/Kolkata zone the embedded DB lacks
                      lambda lens: {p: 0 for p in api_lens._platforms(lens)}), \
         patch.object(api_lens.product_context, "load", return_value=CTX):
        stats = api_lens.top_up(lens=lens)
    stored = sql(uri, "SELECT platform, post_format, seed_url, hashtags, exact_copy FROM social_recommendations "
                      "ORDER BY id")
    return stats, stored, seen


def test_the_model_is_shown_the_x_thread_as_a_seedable_target(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    _, _, seen = top_up(uri, rec("x", "seed_reply", "seed_reply", "hi", seed_url=TWEET, evidence=[tid]))
    sent = json.loads(seen["user"].split("Evidence pack:\n", 1)[1])
    tweet = next(e for e in sent["evidence"] if e["url"] == TWEET)
    assert tweet["seedable"] is True and tweet["source"] == "twitter"


def test_an_x_seed_reply_is_stored_with_its_target_thread(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    stats, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply",
                                       "Start with the order endpoint and a paper account first. (I work at Nubra)",
                                       seed_url=TWEET, evidence=[tid]))
    assert stats["status"] == "succeeded" and stats["stored"] == 1
    platform, fmt, seed_url, _, _ = stored[0]
    assert (platform, fmt, seed_url) == ("x", "seed_reply", TWEET)         # what makes the card say "Target thread"


def test_a_reply_into_a_tweet_is_filed_under_x_even_if_the_model_labels_it_reddit(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    _, stored, _ = top_up(uri, rec("reddit", "seed_reply", "seed_reply", "Short and useful. (I work at Nubra)",
                                   seed_url=TWEET, evidence=[tid]))
    assert stored[0][0] == "x"                                              # the venue is where the thread lives


def test_a_seed_reply_longer_than_one_tweet_is_rejected(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    stats, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply", "x" * 281, seed_url=TWEET, evidence=[tid]))
    assert stored == [] and stats["rejected"] == 1


def test_a_seed_reply_of_exactly_one_tweet_is_accepted(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    _, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply", "x" * 280, seed_url=TWEET, evidence=[tid]))
    assert len(stored) == 1


def test_hashtags_are_dropped_from_an_x_seed_reply(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    _, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply", "Paper trade first.", seed_url=TWEET,
                                   evidence=[tid], hashtags=["#algotrading", "#api"]))
    assert stored[0][3] == [] and "#" not in stored[0][4]


def test_an_invented_target_url_is_still_rejected(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    stats, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply", "Paper trade first.",
                                       seed_url="https://x.com/nobody/status/1", evidence=[tid]))
    assert stored == [] and stats["rejected"] == 1


def test_a_standalone_x_post_still_has_no_target_thread(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    _, stored, _ = top_up(uri, rec("x", "standalone", "text_post", "Three things to check before going live.",
                                   seed_url=TWEET, evidence=[tid], hashtags=["#algo"]))
    platform, fmt, seed_url, hashtags, _ = stored[0]
    assert (platform, fmt, seed_url) == ("x", "text_post", None) and hashtags == ["#algo"]


def test_reddit_seed_replies_work_exactly_as_before(uri):
    tid = add_item(uri, "reddit", "how do I place orders through an api?", POST)
    _, stored, _ = top_up(uri, rec("reddit", "seed_reply", "seed_reply", "x" * 600, seed_url=POST, evidence=[tid],
                                   hashtags=["#kept"]))
    assert stored[0][:3] == ("reddit", "seed_reply", POST)
    assert stored[0][3] == ["#kept"]                       # no X rule leaks into Reddit: no length cap, tags kept


def test_the_retail_queue_stores_x_seed_replies_too(uri):
    tid = add_item(uri, "twitter", "which broker has the clearest option charges?", TWEET, lens="general")
    _, stored, _ = top_up(uri, rec("x", "seed_reply", "seed_reply", "Read the contract note line by line.",
                                   seed_url=TWEET, evidence=[tid], features=("shared_1",)),
                        lens=api_lens.GENERAL_LENS)
    assert stored[0][:3] == ("x", "seed_reply", TWEET)


def warnings_logged(uri, *recs, lens=api_lens.LENS):
    with patch.object(api_lens.log, "warning") as warn:
        stats, stored, _ = top_up(uri, *recs, lens=lens)
    return stats, stored, [c.args[0] % c.args[1:] for c in warn.call_args_list]


def test_every_rejection_says_why(uri):
    tid = add_item(uri, "twitter", "how do I place orders through an api with python?", TWEET)
    stats, stored, logged = warnings_logged(
        uri,
        rec("x", "seed_reply", "seed_reply", "x" * 281, seed_url=TWEET, evidence=[tid], key="too-long"),
        rec("x", "seed_reply", "seed_reply", "ok", seed_url="https://x.com/nobody/status/1", evidence=[tid],
            key="bad-url"),
        rec("x", "seed_reply", "seed_reply", "ok", seed_url=TWEET, evidence=[tid + 99], key="bad-evidence"),
        rec("x", "seed_reply", "seed_reply", "ok", seed_url=TWEET, evidence=[tid], key="bad-feature",
            features=("nope",)))
    assert stored == [] and stats["rejected"] == 4
    text = "\n".join(logged)
    assert "the X reply is 281 characters, max 280" in text
    assert "is not one of its evidence threads" in text
    assert "evidence id that was not in the pack" in text
    assert "feature id that was not supplied" in text
    assert len([line for line in logged if "api-lens brief rejected" in line]) == 4     # none is silent
