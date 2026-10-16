"""The Reddit brand pass: finds posts and comments that mention Nubra, which the nightly run cannot see.

2026-10-15 diagnosis: the nightly search skips comments, a mention in a thread that is not collected is never read, and
a bare global search for "nubra" is mostly Nubra Valley travel posts (19 of 20 rows). The brand pass searches for the
brand inside each finance subreddit (the actor's `withinCommunity`), searches comments too, adds one global search, and
stores a brand comment even when its thread is not collected.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from community.health import config as health_config
from community.scrape import extra_sources, reddit_apify
from tests.test_reddit_apify_pro import ACTOR

SUBS = {"IndianStockMarket": "market_trading", "algotrading": "fno_algo", "Zerodha": "brokers",
        "mutualfunds": "investing_pf"}


def post(pid, sub, title, body="", author="someone"):
    return {"dataType": "post", "id": f"t3_{pid}", "parsedId": pid, "title": title, "body": body,
            "communityName": f"r/{sub}", "parsedCommunityName": sub, "authorName": author,
            "createdAt": "2026-10-14T10:00:00.000Z", "postUrl": f"https://www.reddit.com/r/{sub}/comments/{pid}/x/",
            "upVotes": 3, "commentsCount": 1, "postType": "text", "contentUrl": ""}


def comment(cid, post_id, sub, body, author="teamuser"):
    return {"dataType": "comment", "id": cid, "postId": f"t3_{post_id}", "body": body, "authorName": author,
            "commentCreatedAt": "2026-10-14T11:00:00.000Z", "subredditName": sub,
            "url": f"https://www.reddit.com/r/{sub}/comments/{post_id}/x/{cid}/", "commentUpVotes": 2}


def run_brand(rows_by_run=None, reg_extra=None, subs=SUBS, queries=None, errors=()):
    """collect_brand() with the actor stubbed. rows_by_run: community name (or "all") -> rows."""
    calls = []

    def fake_run(actor, payload, **kw):
        key = payload.get("withinCommunity") or "all"
        calls.append((key, payload, kw))
        if key in errors:
            raise RuntimeError("apify run failed")
        return list((rows_by_run or {}).get(key, []))

    reg = {"enabled": True, "actor": ACTOR, **(reg_extra or {})}
    with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
         patch.object(reddit_apify, "_token", return_value="tok"), \
         patch.object(reddit_apify, "_subreddits", return_value=subs), \
         patch.object(reddit_apify, "brand_queries", return_value=queries or ["nubra"]):
        items, stats = reddit_apify.collect_brand(reg)
    return items, stats, calls


class BrandMentionTests(unittest.TestCase):
    def test_real_mentions_pass(self):
        for text in ("Nubra has a python SDK for options chain (I work at Nubra)", "nubra broker review",
                     "NUBRA api vs kite connect", "Anyone tried Nubra? brokerage looks low",
                     "Nubra valley trek, also my Zerodha account is stuck"):      # travel words AND finance words
            self.assertTrue(reddit_apify.is_brand_mention(text), text)

    def test_the_valley_in_ladakh_does_not(self):
        for text in ("Solo bike trip to Ladakh and Zanskar via Nubra valley", "Nubra to Pangong via Shyok in early October",
                     "Best homestay in Diskit, Nubra", "Hey guys visiting Leh this october, Nubra itinerary?"):
            self.assertFalse(reddit_apify.is_brand_mention(text), text)

    def test_text_that_does_not_name_it_does_not(self):
        for text in ("", "Nubras everywhere", "anubra", "zerodha vs groww"):
            self.assertFalse(reddit_apify.is_brand_mention(text), text)


class BrandSearchPlanTests(unittest.TestCase):
    def test_one_search_inside_each_finance_subreddit_plus_one_global(self):
        _, _, calls = run_brand()
        scoped = sorted(k for k, _, _ in calls if k != "all")
        self.assertEqual(scoped, ["IndianStockMarket", "Zerodha", "algotrading"])      # not mutualfunds (investing_pf)
        self.assertEqual([k for k, _, _ in calls][-1], "all")
        self.assertEqual(len(calls), 4)

    def test_posts_and_comments_are_both_searched_over_a_recent_window(self):
        _, _, calls = run_brand()
        for key, payload, _ in calls:
            self.assertEqual(payload["searchTerms"], ["nubra"], key)
            self.assertTrue(payload["searchPosts"] and payload["searchComments"], key)
            self.assertEqual(payload["searchSort"], "new")
            self.assertFalse(payload["crawlCommentsPerPost"])         # the comments are the hits, not a thread read
            self.assertEqual(payload["postedAfter"], payload["commentedAfter"])
            self.assertEqual(payload["searchTime"], "week")
        self.assertEqual(calls[0][1]["withinCommunity"], calls[0][0])
        self.assertNotIn("withinCommunity", calls[-1][1])             # the global search is not scoped

    def test_the_global_search_can_be_switched_off_and_more_communities_added(self):
        _, _, calls = run_brand(reg_extra={"brand": {"global_search": False, "communities": ["r/IndianInvestments"]}})
        self.assertNotIn("all", [k for k, _, _ in calls])
        self.assertIn("IndianInvestments", [k for k, _, _ in calls])

    def test_the_categories_searched_are_configurable(self):
        _, _, calls = run_brand(reg_extra={"brand": {"categories": ["brokers"], "global_search": False}})
        self.assertEqual([k for k, _, _ in calls], ["Zerodha"])

    def test_every_run_has_a_spend_cap_that_the_registry_can_change(self):
        _, _, calls = run_brand()
        self.assertTrue(all(kw["max_charge_usd"] == 0.5 for _, _, kw in calls))
        _, _, calls = run_brand(reg_extra={"brand": {"max_charge_usd": 0.1}})
        self.assertTrue(all(kw["max_charge_usd"] == 0.1 for _, _, kw in calls))

    def test_the_window_and_result_caps_come_from_the_registry(self):
        _, _, calls = run_brand(reg_extra={"brand": {"days": 1, "max_posts": 7, "max_comments": 9}})
        payload = calls[0][1]
        self.assertEqual((payload["maxPostsCount"], payload["maxCommentsCount"]), (7, 9))
        self.assertEqual(payload["postedAfter"], reddit_apify._since(1))


class BrandCollectionTests(unittest.TestCase):
    def test_a_brand_comment_is_kept_even_though_its_thread_was_never_collected(self):
        rows = {"IndianStockMarket": [comment("pgft0av", "1x4q7w3", "IndianStockMarket",
                                              "Nubra has a python SDK for this (I work at Nubra)")]}
        items, stats, _ = run_brand(rows)
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual((item.source, item.source_type, item.external_id), ("reddit", "comment", "t1_pgft0av"))
        self.assertEqual(item.thread_id, "t3_1x4q7w3")
        self.assertEqual((item.author, item.raw["category"], item.raw["subreddit"]),
                         ("teamuser", "brand", "IndianStockMarket"))
        self.assertEqual((stats["posts"], stats["comments"]), (0, 1))

    def test_a_brand_post_is_kept(self):
        items, stats, _ = run_brand({"algotrading": [post("p1", "algotrading", "Built charts on Nubra", "options chain")]})
        self.assertEqual([(i.source_type, i.external_id) for i in items], [("post", "t3_p1")])
        self.assertEqual(items[0].raw["category"], "brand")

    def test_travel_posts_and_comments_from_the_global_search_are_dropped(self):
        rows = {"all": [post("v1", "ladakh", "Nubra valley in November"),
                        comment("c1", "v2", "XEV9S", "my recent trip to Ladakh, Nubra was stunning"),
                        post("b1", "x", "Nubra broker review", "F&O charges")]}
        items, stats, _ = run_brand(rows)
        self.assertEqual([i.external_id for i in items], ["t3_b1"])
        self.assertEqual(stats["skipped"]["off_brand"], 2)

    def test_rows_that_do_not_mention_it_are_dropped_even_if_the_search_returned_them(self):
        items, stats, _ = run_brand({"all": [post("z1", "x", "Zerodha outage today", "orders stuck")]})
        self.assertEqual(items, [])
        self.assertEqual(stats["skipped"]["off_brand"], 1)

    def test_the_same_comment_found_by_several_searches_is_kept_once(self):
        c = comment("dup", "t", "IndianStockMarket", "Nubra has this (I work at Nubra)")
        items, _, _ = run_brand({"IndianStockMarket": [c], "all": [c]})
        self.assertEqual(len(items), 1)

    def test_bots_are_dropped(self):
        rows = {"all": [comment("a1", "t", "x", "Nubra is mentioned in the sidebar", author="AutoModerator")]}
        items, _, _ = run_brand(rows)
        self.assertEqual(items, [])

    def test_a_failed_search_does_not_lose_the_others(self):
        rows = {"algotrading": [comment("ok1", "t", "algotrading", "Nubra has an SDK")]}
        items, stats, _ = run_brand(rows, errors=("IndianStockMarket",))
        self.assertEqual(len(items), 1)
        self.assertIn("IndianStockMarket", " ".join(stats["errors"]))

    def test_when_every_search_fails_the_pass_fails_so_the_ledger_shows_it(self):
        with self.assertRaises(RuntimeError) as ctx:
            run_brand(errors=("IndianStockMarket", "algotrading", "Zerodha", "all"))
        self.assertIn("every", str(ctx.exception))

    def test_without_a_token_nothing_runs(self):
        with patch.object(reddit_apify, "_token", return_value=""), \
             patch.object(reddit_apify, "_run_actor") as actor:
            items, stats = reddit_apify.collect_brand({"enabled": True, "actor": ACTOR})
        self.assertEqual(items, [])
        actor.assert_not_called()


class BrandBudgetTests(unittest.TestCase):
    def test_a_budget_stop_keeps_what_was_found_and_is_reported(self):
        stops = iter([None, "the Apify account is at 90% of its monthly limit"] + ["stop"] * 9)
        fake_budget = SimpleNamespace(why_stop=lambda: next(stops), summary=lambda: {})
        rows = {"IndianStockMarket": [comment("c1", "t", "IndianStockMarket", "Nubra SDK works")]}
        with patch.object(reddit_apify, "Budget", return_value=fake_budget):
            items, stats, calls = run_brand(rows)
        self.assertEqual(len(items), 1)
        self.assertEqual(len(calls), 1)
        self.assertIn("monthly limit", stats["budget_stopped"])

    def test_fetch_reports_the_stop_after_yielding_the_items(self):
        stops = iter([None, "the budget is spent"] + ["stop"] * 9)
        fake_budget = SimpleNamespace(why_stop=lambda: next(stops), summary=lambda: {})
        rows = {"IndianStockMarket": [comment("c1", "t", "IndianStockMarket", "Nubra SDK works")]}
        seen = []
        with patch.object(reddit_apify, "Budget", return_value=fake_budget), \
             patch.object(reddit_apify, "_run_actor", side_effect=lambda a, p, **k: list(rows.get(p.get("withinCommunity") or "all", []))), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=SUBS), \
             patch.object(reddit_apify, "brand_queries", return_value=["nubra"]):
            gen = reddit_apify.fetch_brand({"enabled": True, "actor": ACTOR})
            with self.assertRaises(RuntimeError) as ctx:
                for item in gen:
                    seen.append(item)
        self.assertEqual(len(seen), 1)
        self.assertIn("stopped early", str(ctx.exception))


class BrandQueriesAndCommunitiesTests(unittest.TestCase):
    def test_the_sources_page_brand_keywords_are_what_is_searched(self):
        rows = [{"value": "nubra", "config": {"x": True, "reddit": True}},
                {"value": "nubra app", "config": {"reddit": True, "reddit_query": '"nubra" app'}}]
        with patch.object(reddit_apify.db, "query", return_value=rows) as q:
            self.assertEqual(reddit_apify.brand_queries({}), ["nubra", '"nubra" app'])
        self.assertIn("category='brand'", q.call_args.args[0].replace(" ", ""))

    def test_with_no_brand_keyword_or_no_database_it_still_searches_for_nubra(self):
        with patch.object(reddit_apify.db, "query", return_value=[]):
            self.assertEqual(reddit_apify.brand_queries({}), ["nubra"])
        with patch.object(reddit_apify.db, "query", side_effect=RuntimeError("db down")):
            self.assertEqual(reddit_apify.brand_queries({}), ["nubra"])

    def test_communities_are_the_watched_subreddits_of_the_brand_categories(self):
        with patch.object(reddit_apify, "_subreddits", return_value=SUBS):
            self.assertEqual(sorted(reddit_apify.brand_communities({})), ["IndianStockMarket", "Zerodha", "algotrading"])
            extra = reddit_apify.brand_communities({"brand": {"communities": ["indianstockmarket", "r/IndiaTax"]}})
        self.assertEqual({c.lower() for c in extra}, {"indianstockmarket", "zerodha", "algotrading", "indiatax"})
        self.assertEqual(len(extra), 4)                    # "indianstockmarket" is the watched IndianStockMarket: once
        self.assertIn("IndiaTax", extra)                   # and the "r/" prefix is stripped


class BrandWiringTests(unittest.TestCase):
    def run_sources(self, registry, **kw):
        stored = []
        item = reddit_apify.comment_item(reddit_apify.normalize_harshmaur(
            comment("w1", "t", "IndianStockMarket", "Nubra SDK works")), "brand")
        with patch.object(extra_sources, "settings", SimpleNamespace(registry={"sources": registry})), \
             patch.object(reddit_apify, "fetch_brand", side_effect=lambda reg: iter([item])), \
             patch.object(extra_sources, "_store", side_effect=lambda it, counters: (stored.append(it),
                          counters.__setitem__("inserted", counters["inserted"] + 1))), \
             patch.object(extra_sources.repo, "advance_state"):
            out = extra_sources.run(**kw)
        return out, stored

    def test_it_runs_on_its_own_when_asked_and_reddit_via_apify_is_enabled(self):
        out, stored = self.run_sources({"reddit_apify": {"enabled": True, "cadence": "nightly"}},
                                       daily=True, only=["reddit_brand"])
        self.assertEqual(list(out), ["reddit_brand"])
        self.assertEqual(out["reddit_brand"]["inserted"], 1)
        self.assertEqual(len(stored), 1)

    def test_it_stays_off_while_reddit_via_apify_is_off(self):
        out, stored = self.run_sources({"reddit_apify": {"enabled": False, "cadence": "nightly"}},
                                       daily=True, only=["reddit_brand"])
        self.assertEqual(out["reddit_brand"]["enabled"], False)
        self.assertEqual(stored, [])

    def test_the_hourly_and_morning_runs_leave_it_to_its_own_slot(self):
        for daily in (False, True):
            out, stored = self.run_sources({"reddit_apify": {"enabled": True, "cadence": "nightly"}}, daily=daily)
            self.assertIn("own cron slot", out["reddit_brand"]["skipped"])
            self.assertEqual(stored, [])


class BrandHealthTests(unittest.TestCase):
    def test_the_daily_slot_is_monitored_once_the_source_has_run(self):
        job = health_config.DEFAULTS["jobs"]["source:reddit_brand"]
        self.assertEqual((job["hours"], job["minute"]), ([20], 45))           # 20:45 IST = 15:15 UTC
        self.assertEqual(job["crit_after_missed"], 1)
        self.assertEqual(job["enabled_by"], "reddit_apify")
        self.assertTrue(job["since_first_run"])


if __name__ == "__main__":
    unittest.main()
