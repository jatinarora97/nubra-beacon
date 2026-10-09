"""Reddit collector via Apify (trudax/reddit-scraper-lite).

Fixtures are the real items returned by the actor on 2026-10-09 (post, comments, community),
plus a reply, a search hit from a non-watched subreddit and a deleted author.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from community.health import config as health_config
from community.scrape import extra_sources, reddit_apify

CATEGORIES = {"IndianStockMarket": "market_trading", "IndiaInvestments": "investing_pf"}

COMMUNITY = {
    "url": "https://www.reddit.com/r/IndianStockMarket/", "dataType": "community",
    "id": "t5_30ke2", "title": "Front page of Indian Stock Market", "displayName": "IndianStockMarket",
    "createdAt": "2026-10-09T07:32:50.543Z", "scrapedAt": "2026-10-09T07:32:50.544Z", "parsedId": "30ke2",
}
POST = {
    "id": "t3_1x1enu2", "title": "Do get any new opportunity to buy the dip",
    "url": "https://www.reddit.com/r/IndianStockMarket/comments/1x1enu2/do_get_any_new_opportunity_to_buy_the_dip/",
    "username": "Illustrious-Nose3457", "upVotes": 0, "upVoteRatio": 0.5, "numberOfComments": 3,
    "createdAt": "2026-10-09T07:07:48.365Z",
    "body": "Buying this dip or holding cash for a deeper flush?\n\nWhat's everyone's game plan right now?\n\nRead more",
    "communityName": "r/IndianStockMarket", "parsedCommunityName": "IndianStockMarket",
    "contentType": "text", "imageUrls": [], "dataType": "post", "parsedId": "1x1enu2",
    "scrapedAt": "2026-10-09T07:34:17.038Z",
}
AUTOMOD = {
    "id": "t1_pesucr8", "username": "AutoModerator", "upVotes": 1, "createdAt": "2026-10-09T07:07:48.497Z",
    "body": "\n\n", "html": "<shreddit-mod-comment>Moderator Announcement</shreddit-mod-comment>",
    "depth": 0, "parentId": None, "postId": "t3_1x1enu2", "dataType": "comment", "numberOfReplies": 0,
    "parsedId": "pesucr8", "communityName": "r/IndianStockMarket",
    "url": "https://www.reddit.com/r/IndianStockMarket/comments/1x1enu2/comment/pesucr8/",
}
COMMENT = {
    "id": "t1_pesvek6", "username": "jyoticra", "upVotes": 2, "createdAt": "2026-10-09T07:16:07.391Z",
    "body": "Mine is to wait till March 31, 2027.\nIn the meantime my Funds are in 7% IDFC Savings Bank Account.",
    "depth": 0, "parentId": None, "postId": "t3_1x1enu2", "dataType": "comment", "numberOfReplies": 1,
    "parsedId": "pesvek6", "communityName": "r/IndianStockMarket",
    "url": "https://www.reddit.com/r/IndianStockMarket/comments/1x1enu2/comment/pesvek6/",
}
REPLY = {**COMMENT, "id": "t1_abc123", "username": "second-user", "upVotes": 3, "body": "Agree, SIPs win.",
         "depth": 1, "parentId": "t1_pesvek6", "parsedId": "abc123", "numberOfReplies": 0,
         "createdAt": "2026-10-09T08:00:00.000Z",
         "url": "https://www.reddit.com/r/IndianStockMarket/comments/1x1enu2/comment/abc123/"}
DELETED = {**COMMENT, "id": "t1_del001", "username": "[deleted]", "parsedId": "del001", "body": "gone"}
ORPHAN = {**COMMENT, "id": "t1_orph01", "postId": "t3_unknown", "parsedId": "orph01", "body": "no parent post"}


def search_hit(post_id, sub, title, body=""):
    return {**POST, "id": f"t3_{post_id}", "parsedId": post_id, "title": title, "body": body,
            "communityName": f"r/{sub}", "parsedCommunityName": sub,
            "url": f"https://www.reddit.com/r/{sub}/comments/{post_id}/x/"}


def collect(rows, *, since=None, keywords=(), subs=None, **kw):
    reg = {"enabled": True, "actor": "trudax~reddit-scraper-lite"}
    subs = CATEGORIES if subs is None else subs
    with patch.object(reddit_apify, "_run_actor", return_value=rows), \
         patch.object(reddit_apify, "_token", return_value="tok"), \
         patch.object(reddit_apify, "_subreddits", return_value=subs), \
         patch.object(reddit_apify, "_active_keywords", return_value=list(keywords)):
        return reddit_apify.collect(reg, since=since, **kw)


class PostMappingTests(unittest.TestCase):
    def setUp(self):
        self.item = reddit_apify.post_item(POST, "market_trading")

    def test_ids_and_identity_match_the_existing_reddit_rows(self):
        self.assertEqual((self.item.source, self.item.source_type), ("reddit", "post"))
        self.assertEqual(self.item.external_id, "t3_1x1enu2")  # same t3_ form as the old scraper
        self.assertEqual(self.item.thread_id, "t3_1x1enu2")
        self.assertIsNone(self.item.parent_id)
        self.assertEqual(self.item.author, "Illustrious-Nose3457")

    def test_real_timestamp_is_used(self):
        self.assertEqual(self.item.created_at,
                         datetime(2026, 10, 9, 7, 7, 48, 365000, tzinfo=timezone.utc))

    def test_text_is_title_plus_body_without_the_read_more_suffix(self):
        self.assertTrue(self.item.text.startswith("Do get any new opportunity to buy the dip "))
        self.assertIn("game plan right now?", self.item.text)
        self.assertFalse(self.item.text.rstrip().endswith("Read more"))

    def test_engagement_and_raw_fields(self):
        self.assertEqual(self.item.engagement.native, {"upvotes": 0, "comments": 3})
        raw = self.item.raw
        self.assertEqual((raw["subreddit"], raw["category"]), ("IndianStockMarket", "market_trading"))
        self.assertEqual(raw["via"], "apify_reddit_lite")
        self.assertEqual((raw["upvote_ratio"], raw["post_type"]), (0.5, "text"))

    def test_an_id_less_row_falls_back_to_parsed_id_then_the_url(self):
        no_id = {**POST}
        no_id.pop("id")
        self.assertEqual(reddit_apify.post_item(no_id, "x").external_id, "t3_1x1enu2")
        no_ids = {**no_id}
        no_ids.pop("parsedId")
        self.assertEqual(reddit_apify.post_item(no_ids, "x").external_id, "t3_1x1enu2")


class CommentMappingTests(unittest.TestCase):
    def test_top_level_comment_hangs_off_the_post(self):
        item = reddit_apify.comment_item(COMMENT, "market_trading")
        self.assertEqual((item.source, item.source_type), ("reddit", "comment"))
        self.assertEqual(item.external_id, "t1_pesvek6")
        self.assertEqual((item.parent_id, item.thread_id), ("t3_1x1enu2", "t3_1x1enu2"))
        self.assertEqual(item.created_at, datetime(2026, 10, 9, 7, 16, 7, 391000, tzinfo=timezone.utc))
        self.assertEqual(item.raw["depth"], 0)
        self.assertFalse(item.raw["nested_reply"])
        self.assertEqual(item.engagement.native, {"upvotes": 2})

    def test_a_reply_hangs_off_its_parent_comment(self):
        item = reddit_apify.comment_item(REPLY, "market_trading")
        self.assertEqual(item.parent_id, "t1_pesvek6")
        self.assertEqual(item.thread_id, "t3_1x1enu2")
        self.assertTrue(item.raw["nested_reply"])


class CollectTests(unittest.TestCase):
    def test_posts_and_good_comments_come_through_and_noise_is_dropped(self):
        items, stats = collect([COMMUNITY, POST, AUTOMOD, COMMENT, REPLY, DELETED, ORPHAN])
        self.assertEqual([i.external_id for i in items], ["t3_1x1enu2", "t1_pesvek6", "t1_abc123"])
        self.assertEqual((stats["posts"], stats["comments"]), (1, 2))
        self.assertEqual(stats["skipped"], {"community": 1, "bot_or_empty_comment": 2,
                                            "orphan_comment": 1})

    def test_a_post_from_a_watched_subreddit_is_kept_without_the_market_filter(self):
        items, _ = collect([search_hit("a1", "IndiaInvestments", "How was your weekend trip?")])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].raw["category"], "investing_pf")

    def test_search_hits_from_other_subreddits_must_pass_the_market_filter(self):
        rows = [search_hit("t1", "travel", "Visiting Nubra Valley this summer", "Great views near Leh"),
                search_hit("t2", "indiatrading", "Nubra app: option chain is slow on expiry day")]
        items, stats = collect(rows)
        self.assertEqual([i.external_id for i in items], ["t3_t2"])
        self.assertEqual(items[0].raw["category"], "keyword")
        self.assertEqual(stats["skipped"], {"off_topic_post": 1})

    def test_a_keyword_that_opts_out_of_the_gate_lets_its_matches_through(self):
        rows = [search_hit("t1", "travel", "Visiting Nubra Valley this summer")]
        items, _ = collect(rows, keywords=[("nubra valley", "nubra valley", True)])
        self.assertEqual(len(items), 1)

    def test_comments_of_a_rejected_post_are_dropped_with_it(self):
        rows = [search_hit("t1", "travel", "Visiting Nubra Valley"),
                {**COMMENT, "id": "t1_c1", "postId": "t3_t1", "parsedId": "c1"}]
        items, stats = collect(rows)
        self.assertEqual(items, [])
        self.assertEqual(stats["skipped"]["orphan_comment"], 1)

    def test_since_drops_older_posts_and_their_comments(self):
        since = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
        items, stats = collect([POST, COMMENT], since=since)
        self.assertEqual(items, [])
        self.assertEqual(stats["skipped"]["older_than_since"], 1)

    def test_rows_without_any_id_are_skipped_not_fatal(self):
        broken = {"dataType": "post", "title": "no id here", "url": "https://www.reddit.com/r/x/"}
        items, stats = collect([broken, POST])
        self.assertEqual(len(items), 1)
        self.assertEqual(stats["skipped"]["no_id"], 1)

    def test_nothing_is_fetched_without_an_apify_token(self):
        with patch.object(reddit_apify, "_token", return_value=""), \
             patch.object(reddit_apify, "_run_actor") as run:
            items, stats = reddit_apify.collect({"enabled": True})
        run.assert_not_called()
        self.assertEqual((items, stats["rows"]), ([], 0))

    def test_fetch_is_an_iterator_over_the_collected_items(self):
        with patch.object(reddit_apify, "collect", return_value=(["a", "b"], {})):
            self.assertEqual(list(reddit_apify.fetch({"enabled": True})), ["a", "b"])


class RestrictedRunTests(unittest.TestCase):
    """The probe / backfill restrict the run to chosen subreddits (only_subs)."""

    def run_with(self, **kw):
        with patch.object(reddit_apify, "_run_actor", return_value=[]) as run,              patch.object(reddit_apify, "_token", return_value="tok"),              patch.object(reddit_apify, "_subreddits", return_value=CATEGORIES),              patch.object(reddit_apify, "_active_keywords", return_value=[("nubra", "nubra", False)]):
            reddit_apify.collect({"enabled": True}, **kw)
        return run.call_args.args[1]

    def test_only_subs_runs_just_those_subreddits_without_keyword_searches(self):
        payload = self.run_with(only_subs=["Zerodha"])
        self.assertEqual(payload["startUrls"], [{"url": "https://www.reddit.com/r/Zerodha/"}])
        self.assertEqual(payload["searches"], [])

    def test_with_keywords_adds_the_keyword_searches_to_a_restricted_run(self):
        payload = self.run_with(only_subs=["Zerodha"], with_keywords=True)
        self.assertEqual(payload["searches"], ["nubra"])
        self.assertEqual(len(payload["startUrls"]), 1)

    def test_a_normal_run_covers_every_watched_subreddit_and_keyword(self):
        payload = self.run_with()
        self.assertEqual(len(payload["startUrls"]), len(CATEGORIES))
        self.assertEqual(payload["searches"], ["nubra"])


class MultiSortTests(unittest.TestCase):
    """The old collector ran `new` every time plus top/hot/rising once a day; here one run per sort."""

    def run_sorts(self, rows_by_sort, sorts, **kw):
        calls = []

        def fake_run(actor, payload, **_kw):
            calls.append(payload["sort"])
            result = rows_by_sort[payload["sort"]]
            if isinstance(result, Exception):
                raise result
            return result

        with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=CATEGORIES), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]):
            items, stats = reddit_apify.collect({"enabled": True}, sorts=sorts, **kw)
        return calls, items, stats

    def test_one_actor_run_per_sort_and_the_same_post_or_comment_is_kept_once(self):
        calls, items, stats = self.run_sorts(
            {"new": [POST, COMMENT], "hot": [POST, COMMENT, REPLY]}, ["new", "hot"])
        self.assertEqual(calls, ["new", "hot"])
        self.assertEqual([i.external_id for i in items], ["t3_1x1enu2", "t1_pesvek6", "t1_abc123"])
        self.assertEqual(stats["by_sort"], {"new": 2, "hot": 3})

    def test_a_sort_the_actor_rejects_is_reported_and_the_other_sorts_still_count(self):
        calls, items, stats = self.run_sorts(
            {"new": [POST], "top": RuntimeError("apify run X: FAILED")}, ["new", "top"])
        self.assertEqual(calls, ["new", "top"])
        self.assertEqual([i.external_id for i in items], ["t3_1x1enu2"])
        self.assertIn("FAILED", stats["errors"]["top"])

    def test_if_every_sort_fails_the_collector_raises_so_the_error_is_recorded(self):
        with self.assertRaises(RuntimeError):
            self.run_sorts({"new": RuntimeError("boom"), "hot": RuntimeError("boom")}, ["new", "hot"])

    def test_with_no_sorts_given_the_registry_sort_is_used_once(self):
        with patch.object(reddit_apify, "_run_actor", return_value=[]) as run, \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=CATEGORIES), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]):
            reddit_apify.collect({"enabled": True, "sort": "rising"})
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[1]["sort"], "rising")

    def test_a_sorts_list_in_the_registry_runs_each_sort(self):
        with patch.object(reddit_apify, "_run_actor", return_value=[]) as run, \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=CATEGORIES), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]):
            reddit_apify.collect({"enabled": True, "sorts": ["new", "hot"]})
        self.assertEqual([c.args[1]["sort"] for c in run.call_args_list], ["new", "hot"])

    def test_the_time_filter_is_only_sent_for_the_top_sort_and_only_when_configured(self):
        reg = {"top_time": "day"}
        self.assertEqual(reddit_apify.build_payload({**reg, "sort": "top"}, ["a"], [])["time"], "day")
        self.assertNotIn("time", reddit_apify.build_payload({**reg, "sort": "new"}, ["a"], []))
        self.assertNotIn("time", reddit_apify.build_payload({"sort": "top"}, ["a"], []))


class SummaryTests(unittest.TestCase):
    def test_summary_describes_what_a_run_would_store(self):
        items, _ = collect([POST, COMMENT, REPLY,
                            search_hit("t2", "indiatrading", "Nubra app: option chain is slow")])
        summary = reddit_apify.summarize(items)
        self.assertEqual((summary["posts"], summary["comments"], summary["nested_replies"]), (2, 2, 1))
        self.assertEqual(summary["by_subreddit"]["IndianStockMarket"], {"posts": 1, "comments": 2})
        self.assertEqual(summary["by_category"]["market_trading"], {"posts": 1, "comments": 2})
        self.assertEqual(summary["keyword_posts"], 1)
        self.assertEqual(summary["newest"], datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc))
        self.assertEqual(summary["oldest"], datetime(2026, 10, 9, 7, 7, 48, 365000, tzinfo=timezone.utc))

    def test_summary_of_nothing_is_empty_not_an_error(self):
        summary = reddit_apify.summarize([])
        self.assertEqual((summary["posts"], summary["comments"], summary["oldest"]), (0, 0, None))


class FakeApifyClient:
    """Stands in for httpx.Client: start a run, poll its status, read the dataset."""

    def __init__(self, status, items, cost=0.25):
        self.status, self.items, self.cost = status, items, cost
        self.posts = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @staticmethod
    def _resp(payload):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: payload)

    def post(self, url, params=None, json=None):
        self.posts.append((url, params, json))
        return self._resp({"data": {"id": "run1", "defaultDatasetId": "ds1", "status": "READY"}})

    def get(self, url, params=None):
        if "/actor-runs/" in url:
            return self._resp({"data": {"status": self.status, "usageTotalUsd": self.cost}})
        return self._resp(self.items)


class RunActorTests(unittest.TestCase):
    """A timed-out run still holds the results it collected (and was paid for): keep them."""

    def run_actor(self, status, items, **kw):
        client = FakeApifyClient(status, items)
        reddit_apify.run_costs_usd = 0.0
        del reddit_apify.run_log[:]
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            return reddit_apify._run_actor("trudax~reddit-scraper-lite", {"sort": "new"}, **kw), client

    def test_a_finished_run_returns_its_items_and_is_logged(self):
        items, client = self.run_actor("SUCCEEDED", [POST, COMMENT])
        self.assertEqual(items, [POST, COMMENT])
        entry = reddit_apify.run_log[-1]
        self.assertEqual((entry["status"], entry["items"], entry["partial"]), ("SUCCEEDED", 2, False))
        self.assertAlmostEqual(reddit_apify.run_costs_usd, 0.25)
        self.assertIn("trudax~reddit-scraper-lite", client.posts[0][0])

    def test_a_timed_out_run_keeps_what_it_collected_and_says_it_is_partial(self):
        items, _ = self.run_actor("TIMED-OUT", [POST])
        self.assertEqual(items, [POST])
        entry = reddit_apify.run_log[-1]
        self.assertEqual((entry["status"], entry["partial"]), ("TIMED-OUT", True))

    def test_a_run_that_ended_badly_with_nothing_still_raises(self):
        for status in ("TIMED-OUT", "FAILED", "ABORTED"):
            with self.assertRaises(RuntimeError) as ctx:
                self.run_actor(status, [])
            self.assertIn(status, str(ctx.exception))
            self.assertEqual(reddit_apify.run_log[-1]["items"], 0)


class ChunkingTests(unittest.TestCase):
    """One giant run (20 subreddits + 16 searches) timed out at 15 min. Split the work into several
    smaller runs; each run keeps the input shape the console accepted (some subreddits AND some
    searches together), so no new, untested input shape is introduced."""

    def collect_chunks(self, subs, queries, reg=None, fail_on=None):
        calls = []

        def fake_run(actor, payload, **_kw):
            calls.append(payload)
            if fail_on and fail_on(payload):
                raise RuntimeError("apify run X: FAILED")
            return []

        keywords = [(q, q, False) for q in queries]
        with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value={f"sub{i}": "x" for i in range(subs)}), \
             patch.object(reddit_apify, "_active_keywords", return_value=keywords):
            items, stats = reddit_apify.collect({"enabled": True, **(reg or {})})
        return calls, stats

    def shape(self, calls):
        return [(len(c["startUrls"]), len(c["searches"])) for c in calls]

    def test_the_old_full_scope_becomes_four_balanced_runs(self):
        calls, _ = self.collect_chunks(20, [f"q{i}" for i in range(16)],
                                       {"subs_per_run": 5, "queries_per_run": 4})
        self.assertEqual(self.shape(calls), [(5, 4)] * 4)

    def test_uneven_work_is_spread_evenly_and_nothing_is_lost_or_repeated(self):
        calls, _ = self.collect_chunks(12, [f"q{i}" for i in range(6)],
                                       {"subs_per_run": 5, "queries_per_run": 4})
        self.assertEqual(self.shape(calls), [(4, 2)] * 3)
        urls = [u["url"] for c in calls for u in c["startUrls"]]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertEqual(sorted(q for c in calls for q in c["searches"]), sorted(f"q{i}" for i in range(6)))

    def test_only_subreddits_or_only_searches_still_chunk_correctly(self):
        calls, _ = self.collect_chunks(11, [], {"subs_per_run": 5})
        self.assertEqual(self.shape(calls), [(4, 0), (4, 0), (3, 0)])
        calls, _ = self.collect_chunks(0, [f"q{i}" for i in range(9)], {"queries_per_run": 4})
        self.assertEqual(self.shape(calls), [(0, 3)] * 3)

    def test_a_small_scope_stays_a_single_run(self):
        calls, _ = self.collect_chunks(3, ["q"], {})
        self.assertEqual(self.shape(calls), [(3, 1)])

    def test_the_item_cap_applies_to_each_run_not_to_the_whole_job(self):
        calls, _ = self.collect_chunks(10, [], {"subs_per_run": 5, "max_items_per_run": 100})
        self.assertEqual([c["maxItems"] for c in calls], [100, 100])

    def test_one_failing_run_is_reported_and_the_rest_still_count(self):
        calls, stats = self.collect_chunks(
            12, [], {"subs_per_run": 5},
            fail_on=lambda p: p["startUrls"][0]["url"].endswith("/sub4/"))
        self.assertEqual(len(calls), 3)
        self.assertEqual(list(stats["errors"]), ["new: run 2/3"])
        self.assertEqual(sorted(stats["by_sort"]), ["new"])

    def test_if_every_run_fails_it_raises(self):
        with self.assertRaises(RuntimeError):
            self.collect_chunks(7, ["q"], {"subs_per_run": 5}, fail_on=lambda p: True)

    def test_runs_are_logged_with_their_labels_for_the_probe_report(self):
        def fake_run(actor, payload, **_kw):
            reddit_apify.run_log.append({"run_id": "r", "status": "SUCCEEDED", "items": 0,
                                         "cost_usd": 0.1, "partial": False, "seconds": 5.0})
            return []

        with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value={"a": "x", "b": "x", "c": "x"}), \
             patch.object(reddit_apify, "_active_keywords", return_value=[("k", "k", False)]):
            _items, stats = reddit_apify.collect({"enabled": True, "subs_per_run": 2, "queries_per_run": 1})
        self.assertEqual([r["label"] for r in stats["runs"]], ["new: run 1/2", "new: run 2/2"])


class PlanRunsTests(unittest.TestCase):
    def test_plan_runs_matches_what_collect_will_do(self):
        plan = reddit_apify.plan_runs({"subs_per_run": 5, "queries_per_run": 4},
                                      [f"s{i}" for i in range(20)], [f"q{i}" for i in range(16)])
        self.assertEqual([(len(a), len(b)) for a, b in plan], [(5, 4)] * 4)

    def test_an_empty_scope_is_one_empty_run_not_a_crash(self):
        self.assertEqual(reddit_apify.plan_runs({}, [], []), [([], [])])


class PayloadTests(unittest.TestCase):
    REG = {"sort": "new", "max_posts_per_sub": 10, "comments_per_post": 5, "max_items_per_run": 1500,
           "proxy_groups": ["RESIDENTIAL"]}

    def test_payload_uses_the_input_shape_the_console_accepted(self):
        p = reddit_apify.build_payload(self.REG, ["IndianStockMarket", "Zerodha"], ["nubra"])
        self.assertEqual(p["startUrls"], [{"url": "https://www.reddit.com/r/IndianStockMarket/"},
                                          {"url": "https://www.reddit.com/r/Zerodha/"}])
        self.assertEqual(p["searches"], ["nubra"])
        self.assertEqual((p["sort"], p["maxPostCount"], p["maxComments"]), ("new", 10, 5))
        self.assertEqual(p["proxy"], {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]})
        self.assertTrue(p["searchPosts"])
        for off in ("searchComments", "searchCommunities", "searchMedia", "searchUsers", "skipUserPosts"):
            self.assertFalse(p[off], off)
        self.assertNotIn("postDateLimit", p)  # the console rejected an input carrying date limits
        self.assertNotIn("time", p)

    def test_max_items_covers_posts_comments_and_community_rows_but_respects_the_cap(self):
        p = reddit_apify.build_payload(self.REG, ["a", "b"], ["kw"])
        # 2 subs * (1 community + 10 posts * (1 + 5 comments)) + 1 query * 10 * 6
        self.assertEqual(p["maxItems"], 2 * (1 + 10 * 6) + 10 * 6)
        capped = reddit_apify.build_payload({**self.REG, "max_items_per_run": 300}, ["s"] * 21, ["kw"])
        self.assertEqual(capped["maxItems"], 300)

    def test_skipping_community_rows_frees_item_budget(self):
        p = reddit_apify.build_payload({**self.REG, "skip_community": True}, ["a", "b"], [])
        self.assertTrue(p["skipCommunity"])
        self.assertEqual(p["maxItems"], 2 * (10 * 6))


class DormantByDefaultTests(unittest.TestCase):
    def test_the_collector_is_registered_but_does_nothing_until_enabled(self):
        with patch.object(extra_sources, "settings", SimpleNamespace(registry={"sources": {}})), \
             patch.object(reddit_apify, "fetch") as fetch:
            out = extra_sources.run(only=["reddit_apify"])
        fetch.assert_not_called()
        self.assertFalse(out["reddit_apify"]["enabled"])

    def test_the_shipped_registry_block_is_disabled_and_names_the_actor(self):
        path = Path(__file__).resolve().parent.parent / "community" / "config" / "registry.yaml"
        block = yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]["reddit_apify"]
        self.assertIs(block["enabled"], False)
        self.assertEqual(block["actor"], "trudax~reddit-scraper-lite")
        self.assertEqual(block["cadence"], "nightly")  # own cron slot, not the morning build
        self.assertEqual((block["subs_per_run"], block["queries_per_run"]), (5, 4))  # small runs: one big run timed out

    def test_health_knows_the_source_name_so_staleness_is_judged_once_it_is_enabled(self):
        self.assertEqual(health_config.load({})["sources"]["map"]["reddit_apify"], "reddit_apify")
