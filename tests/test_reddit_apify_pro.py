"""Reddit collector via Apify, actor harshmaur/reddit-scraper-pro.

Fixtures are real items returned by the actor on 2026-10-11 (post, AutoModerator comment, a search
hit), trimmed to the fields that matter, plus a user comment and a nested reply. The nested reply's
parentId format was NOT seen in the sample, so both the bare and the t1_-prefixed forms are covered.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from community.scrape import reddit_apify

ACTOR = "harshmaur~reddit-scraper-pro"
CATS = {"IndianStockMarket": "market_trading", "Zerodha": "broker_chat"}

POST = {
    "id": "t3_1wzqkgr", "parsedId": "1wzqkgr", "title": "Anyone going through this?", "body": "",
    "contentUrl": "https://i.redd.it/kih099bp20uh1.jpeg", "authorId": "t2_94k774gm9",
    "authorName": "PositiveParking819", "parsedCommunityName": "IndianStockMarket",
    "communityName": "r/IndianStockMarket", "flair": "Shitpost", "postType": "text", "upVotes": 4463,
    "commentsCount": 72, "dataType": "post",
    "postUrl": "https://www.reddit.com/r/IndianStockMarket/comments/1wzqkgr/anyone_going_through_this/",
    "createdAt": "2026-10-07T07:47:12.000Z", "score": 4463, "upvoteRatio": 0.98, "stickied": False,
}
AUTOMOD = {
    "id": "pedxsj2", "url": "https://www.reddit.com/r/IndianStockMarket/comments/1wzqkgr/anyone_going_through_this/pedxsj2/",
    "postId": "t3_1wzqkgr", "parsedPostId": "1wzqkgr", "parentId": "t3_1wzqkgr",
    "authorId": "t1_pedxsj2", "parsedAuthorId": "pedxsj2", "authorName": "AutoModerator",
    "subredditName": "IndianStockMarket", "commentUpVotes": 1, "commentCreatedAt": "2026-10-07T07:47:13.000Z",
    "dataType": "comment", "body": "Guidelines - Buy/Sell posts will be removed.", "score": 1, "depth": 0,
    "stickied": True, "distinguished": "moderator",
}
COMMENT = {**AUTOMOD, "id": "pedy111", "authorName": "jyoticra", "commentUpVotes": 12, "score": 12,
           "body": "Mine is to wait till March 31, 2027.", "stickied": False, "distinguished": None,
           "url": "https://www.reddit.com/r/IndianStockMarket/comments/1wzqkgr/anyone_going_through_this/pedy111/",
           "commentCreatedAt": "2026-10-07T08:01:00.000Z"}
REPLY = {**COMMENT, "id": "pedy222", "authorName": "second-user", "commentUpVotes": 3, "depth": 1,
         "parentId": "t1_pedy111", "body": "Agree, SIPs win.", "commentCreatedAt": "2026-10-07T09:00:00.000Z",
         "url": "https://www.reddit.com/r/IndianStockMarket/comments/1wzqkgr/anyone_going_through_this/pedy222/"}
SEARCH_HIT = {**POST, "id": "t3_1x2itta", "parsedId": "1x2itta", "title": "Visiting Ladakh, stays in Nubra valley?",
              "communityName": "r/ladakhtrip2025", "parsedCommunityName": "ladakhtrip2025", "searchTerm": "nubra",
              "postUrl": "https://www.reddit.com/r/ladakhtrip2025/comments/1x2itta/x/", "contentUrl": "https://x.com/y"}


def run(rows_by_kind, subs=CATS, keywords=(), reg_extra=None, **kw):
    """collect() with the actor stubbed; returns (items, stats, calls) where calls = [(actor, payload, kwargs)]."""
    calls = []

    def fake_run(actor, payload, **kwargs):
        calls.append((actor, payload, kwargs))
        return list(rows_by_kind["listing" if "subredditUrls" in payload else "search"])

    reg = {"enabled": True, "actor": ACTOR, **(reg_extra or {})}
    with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
         patch.object(reddit_apify, "_token", return_value="tok"), \
         patch.object(reddit_apify, "_subreddits", return_value=subs), \
         patch.object(reddit_apify, "_active_keywords", return_value=list(keywords)):
        items, stats = reddit_apify.collect(reg, **kw)
    return items, stats, calls


class ProfileTests(unittest.TestCase):
    def test_the_actor_id_picks_the_profile(self):
        self.assertEqual(reddit_apify._profile("harshmaur~reddit-scraper-pro"), "harshmaur")
        self.assertEqual(reddit_apify._profile("trudax~reddit-scraper-lite"), "trudax")
        self.assertEqual(reddit_apify._profile("someone~else"), "trudax")   # unknown actors keep the old behaviour

    def test_the_slash_form_of_the_id_is_accepted(self):
        self.assertEqual(reddit_apify._profile(reddit_apify._actor({"actor": "harshmaur/reddit-scraper-pro"})),
                         "harshmaur")


class NormalizeTests(unittest.TestCase):
    def test_a_post_gets_the_field_names_the_mapping_reads(self):
        row = reddit_apify.normalize_harshmaur(POST)
        self.assertEqual((row["username"], row["numberOfComments"], row["upVotes"]), ("PositiveParking819", 72, 4463))
        self.assertEqual(row["url"], POST["postUrl"])
        self.assertEqual((row["upVoteRatio"], row["contentType"]), (0.98, "text"))
        self.assertEqual(row["imageUrls"], ["https://i.redd.it/kih099bp20uh1.jpeg"])
        self.assertEqual(row["id"], "t3_1wzqkgr")

    def test_only_reddit_hosted_images_are_kept_as_image_urls(self):
        self.assertEqual(reddit_apify.normalize_harshmaur(SEARCH_HIT)["imageUrls"], [])

    def test_a_comment_id_gets_its_t1_prefix_and_its_own_field_names(self):
        row = reddit_apify.normalize_harshmaur(COMMENT)
        self.assertEqual(row["id"], "t1_pedy111")       # the actor sends the bare id
        self.assertEqual((row["username"], row["upVotes"]), ("jyoticra", 12))
        self.assertEqual(row["createdAt"], "2026-10-07T08:01:00.000Z")
        self.assertEqual(row["parsedCommunityName"], "IndianStockMarket")
        self.assertEqual(row["postId"], "t3_1wzqkgr")

    def test_the_actors_authorId_on_a_comment_is_never_used(self):
        # the actor fills authorId with the COMMENT's own id (t1_pedxsj2); the author is authorName
        self.assertEqual(reddit_apify.normalize_harshmaur(AUTOMOD)["username"], "AutoModerator")

    def test_parent_links_are_normalised_to_reddit_fullnames(self):
        top = reddit_apify.normalize_harshmaur(COMMENT)
        self.assertEqual(top["parentId"], "t3_1wzqkgr")                      # top level hangs off the post
        self.assertEqual(reddit_apify.normalize_harshmaur(REPLY)["parentId"], "t1_pedy111")
        bare = reddit_apify.normalize_harshmaur({**REPLY, "parentId": "pedy111"})
        self.assertEqual(bare["parentId"], "t1_pedy111")                     # bare id gets its prefix
        none = reddit_apify.normalize_harshmaur({**COMMENT, "parentId": ""})
        self.assertIsNone(none["parentId"])                                  # mapping falls back to the post

    def test_a_comment_without_an_id_stays_unusable(self):
        row = reddit_apify.normalize_harshmaur({**COMMENT, "id": ""})
        self.assertFalse(reddit_apify._comment_id(row))

    def test_the_input_row_is_not_mutated_and_other_kinds_pass_through(self):
        before = dict(COMMENT)
        reddit_apify.normalize_harshmaur(COMMENT)
        self.assertEqual(COMMENT, before)
        other = reddit_apify.normalize_harshmaur({"dataType": "community", "id": "t5_x"})
        self.assertEqual(other["dataType"], "community")

    def test_rows_are_tagged_with_the_actor_that_produced_them(self):
        self.assertEqual(reddit_apify.normalize_harshmaur(POST)["_via"], "apify_reddit_pro")


class PayloadTests(unittest.TestCase):
    def since(self, days):
        return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")

    def payloads(self, subs, queries, **reg):
        return reddit_apify.build_payloads({"actor": ACTOR, "max_posts_per_sub": 10, "comments_per_post": 5, **reg},
                                           subs, queries)

    def test_listing_input_is_the_shape_the_actor_accepted(self):
        [(suffix, p)] = self.payloads(["IndianStockMarket", "Zerodha"], [])
        self.assertEqual(suffix, "")
        self.assertEqual(p["subredditUrls"], ["https://www.reddit.com/r/IndianStockMarket/",
                                              "https://www.reddit.com/r/Zerodha/"])
        self.assertEqual((p["maxPostsCount"], p["maxCommentsPerPost"], p["crawlCommentsPerPost"]), (20, 5, True))
        self.assertEqual((p["postedAfter"], p["commentedAfter"]), (self.since(2), self.since(2)))
        self.assertFalse(p["includeNSFW"])
        for trudax_only in ("startUrls", "searches", "maxItems", "proxy", "sort"):
            self.assertNotIn(trudax_only, p)

    def test_search_input_is_a_separate_run_with_its_own_shape(self):
        [(suffix, p)] = self.payloads([], ["nubra broker", "nubra trading app"])
        self.assertEqual(suffix, " search")
        self.assertEqual(p["searchTerms"], ["nubra broker", "nubra trading app"])
        self.assertEqual((p["searchPosts"], p["searchComments"], p["searchSort"]), (True, False, "new"))
        self.assertEqual((p["searchTime"], p["postedAfter"]), ("week", self.since(2)))
        self.assertEqual(p["maxPostsCount"], 20)            # 10 per search term
        self.assertFalse(p["crawlCommentsPerPost"])
        self.assertNotIn("subredditUrls", p)

    def test_subreddits_and_searches_in_one_chunk_become_two_runs_listing_first(self):
        runs = self.payloads(["Zerodha"], ["nubra"])
        self.assertEqual([s for s, _ in runs], ["", " search"])
        self.assertIn("subredditUrls", runs[0][1])
        self.assertIn("searchTerms", runs[1][1])

    def test_no_subreddits_means_no_listing_run_and_no_queries_no_search_run(self):
        self.assertEqual(len(self.payloads(["Zerodha"], [])), 1)
        self.assertEqual(len(self.payloads([], ["nubra"])), 1)

    def test_the_date_window_follows_date_limit_days(self):
        [(_, p)] = self.payloads(["Zerodha"], [], date_limit_days=14)
        self.assertEqual(p["postedAfter"], self.since(14))
        [(_, s)] = self.payloads([], ["nubra"], date_limit_days=14)
        self.assertEqual((s["searchTime"], s["postedAfter"]), ("month", self.since(14)))
        [(_, y)] = self.payloads([], ["nubra"], date_limit_days=90)
        self.assertEqual(y["searchTime"], "year")

    def test_no_comments_wanted_turns_comment_crawling_off(self):
        [(_, p)] = self.payloads(["Zerodha"], [], comments_per_post=0)
        self.assertFalse(p["crawlCommentsPerPost"])

    def test_the_trudax_actor_keeps_its_single_combined_input(self):
        runs = reddit_apify.build_payloads({"actor": "trudax~reddit-scraper-lite", "max_posts_per_sub": 10,
                                            "comments_per_post": 5}, ["Zerodha"], ["nubra"])
        self.assertEqual(len(runs), 1)
        self.assertIn("startUrls", runs[0][1])
        self.assertIn("searches", runs[0][1])


class CollectTests(unittest.TestCase):
    ROWS = {"listing": [POST, AUTOMOD, COMMENT, REPLY], "search": []}

    def test_posts_and_comments_are_mapped_with_threading(self):
        items, stats, _ = run(self.ROWS)
        by_id = {i.external_id: i for i in items}
        self.assertEqual(set(by_id), {"t3_1wzqkgr", "t1_pedy111", "t1_pedy222"})   # AutoModerator dropped
        post, top, reply = by_id["t3_1wzqkgr"], by_id["t1_pedy111"], by_id["t1_pedy222"]
        self.assertEqual((post.author, post.engagement.native["upvotes"], post.raw["subreddit"]),
                         ("PositiveParking819", 4463, "IndianStockMarket"))
        self.assertEqual(post.raw["category"], "market_trading")
        self.assertEqual(post.url, POST["postUrl"])
        self.assertEqual((top.parent_id, top.thread_id, top.raw["nested_reply"]), ("t3_1wzqkgr", "t3_1wzqkgr", False))
        self.assertEqual((reply.parent_id, reply.raw["nested_reply"], reply.author), ("t1_pedy111", True, "second-user"))
        self.assertEqual((stats["posts"], stats["comments"]), (1, 2))
        self.assertEqual(post.raw["via"], "apify_reddit_pro")
        self.assertEqual(top.raw["via"], "apify_reddit_pro")

    def test_search_hits_still_need_a_market_term_unless_the_sub_is_watched(self):
        rows = {"listing": [], "search": [SEARCH_HIT]}
        items, stats, _ = run(rows, subs={}, keywords=[("nubra", "nubra", False)])
        self.assertEqual(items, [])                                    # Nubra Valley travel post stays out
        self.assertEqual(stats["skipped"], {"off_topic_post": 1})

    def test_a_market_search_hit_is_kept_as_a_keyword_post(self):
        hit = {**SEARCH_HIT, "title": "Nubra broker review: brokerage and F&O charges", "communityName": "r/StockMarketIndia",
               "parsedCommunityName": "StockMarketIndia"}
        items, _, _ = run({"listing": [], "search": [hit]}, subs={}, keywords=[("nubra", "nubra", False)])
        self.assertEqual([(i.source_type, i.raw["category"]) for i in items], [("post", "keyword")])

    def test_listing_and_search_are_separate_runs_and_sorts_do_not_multiply_them(self):
        _, stats, calls = run(self.ROWS, keywords=[("nubra", "nubra", False)], sorts=["new", "top", "hot"])
        kinds = ["listing" if "subredditUrls" in p else "search" for _, p, _ in calls]
        # 1 search run, then 2 listing runs (one sub each); 3 sorts do not triple them
        self.assertEqual(kinds, ["search", "listing", "listing"])

    def test_every_run_targets_the_harshmaur_actor_with_the_registry_limits(self):
        _, _, calls = run(self.ROWS, reg_extra={"timeout_s": 321, "memory_mb": 2048})
        actor, _, kwargs = calls[0]
        self.assertEqual(actor, ACTOR)
        self.assertEqual((kwargs["timeout_s"], kwargs["memory_mb"]), (321, 2048))

    def test_the_spend_cap_follows_the_registry_with_a_safe_default(self):
        _, _, calls = run(self.ROWS)
        self.assertEqual(calls[0][2]["max_charge_usd"], 2.0)            # default when the registry is silent
        _, _, calls = run(self.ROWS, reg_extra={"max_charge_usd": 0.75})
        self.assertEqual(calls[0][2]["max_charge_usd"], 0.75)

    def test_one_failed_run_does_not_lose_the_other(self):
        def fake_run(actor, payload, **kw):
            if "searchTerms" in payload:
                raise RuntimeError("input rejected")
            return [POST, COMMENT]
        reg = {"enabled": True, "actor": ACTOR}
        with patch.object(reddit_apify, "_run_actor", side_effect=fake_run), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value=CATS), \
             patch.object(reddit_apify, "_active_keywords", return_value=[("nubra", "nubra", False)]):
            items, stats = reddit_apify.collect(reg)
        self.assertEqual(len(items), 2)
        self.assertEqual(list(stats["errors"]), ["new: run 1/3 search"])   # the search runs first now

    def test_the_trudax_actor_still_gets_its_original_via_tag(self):
        from tests.test_reddit_apify import POST as TRUDAX_POST, collect as trudax_collect
        items, _ = trudax_collect([TRUDAX_POST])
        self.assertEqual(items[0].raw["via"], "apify_reddit_lite")


if __name__ == "__main__":
    unittest.main()


class WorstCaseTests(unittest.TestCase):
    REG = {"max_posts_per_sub": 10, "comments_per_post": 5}

    def test_harshmaur_listing_is_posts_times_one_plus_comments(self):
        [(_, p)] = reddit_apify.build_payloads({**self.REG, "actor": ACTOR}, ["a", "b"], [])
        self.assertEqual(reddit_apify.worst_case_items(p), 20 * (1 + 5))

    def test_harshmaur_search_counts_posts_only_because_comments_are_off(self):
        [(_, p)] = reddit_apify.build_payloads({**self.REG, "actor": ACTOR}, [], ["x", "y"])
        self.assertEqual(reddit_apify.worst_case_items(p), 20)

    def test_trudax_uses_its_own_item_cap_or_what_it_wants_if_lower(self):
        reg = {**self.REG, "actor": "trudax~reddit-scraper-lite"}
        [(_, capped)] = reddit_apify.build_payloads({**reg, "max_items_per_run": 50}, ["a"], [])
        self.assertEqual(reddit_apify.worst_case_items(capped), 50)
        [(_, uncapped)] = reddit_apify.build_payloads({**reg, "max_items_per_run": 1000}, ["a"], [])
        self.assertEqual(reddit_apify.worst_case_items(uncapped), 1 * (1 + 10 * 6))   # community row + 10 posts x (1+5)


class PlanTests(unittest.TestCase):
    """maxPostsCount is ONE total for everything in a run (documented by the actor), so on 2026-10-11 the
    first busy subreddit of each run used up the budget and 16 of 20 watched subreddits came back empty."""
    SUBS = [f"sub{i}" for i in range(20)]
    QUERIES = [f"q{i}" for i in range(16)]

    def plan(self, **reg):
        return reddit_apify.make_plan({"actor": ACTOR, **reg}, self.SUBS, self.QUERIES)

    def test_every_subreddit_gets_its_own_listing_run_by_default(self):
        listing = [(s, q) for s, q in self.plan() if s]
        self.assertEqual(len(listing), 20)
        self.assertTrue(all(len(s) == 1 and q == [] for s, q in listing))
        self.assertEqual([s[0] for s, _ in listing], self.SUBS)

    def test_searches_run_separately_in_groups_of_queries_per_run(self):
        searches = [(s, q) for s, q in self.plan() if q]
        self.assertEqual(len(searches), 4)
        self.assertTrue(all(s == [] and len(q) == 4 for s, q in searches))

    def test_listing_subs_per_run_can_be_raised(self):
        self.assertEqual(len([1 for s, _ in self.plan(listing_subs_per_run=5) if s]), 4)

    def test_the_old_subs_per_run_key_does_not_re_create_the_starvation(self):
        # the VM's registry.yaml still carries subs_per_run: 5 from the trudax setup
        self.assertEqual(len([1 for s, _ in self.plan(subs_per_run=5) if s]), 20)

    def test_nothing_to_search_means_no_search_runs_and_vice_versa(self):
        self.assertEqual(reddit_apify.make_plan({"actor": ACTOR}, ["a"], []), [(["a"], [])])
        self.assertEqual(reddit_apify.make_plan({"actor": ACTOR}, [], ["q"]), [([], ["q"])])

    def test_trudax_keeps_its_original_balanced_plan(self):
        reg = {"actor": "trudax~reddit-scraper-lite", "subs_per_run": 5, "queries_per_run": 4}
        self.assertEqual(reddit_apify.make_plan(reg, self.SUBS, self.QUERIES),
                         reddit_apify.plan_runs(reg, self.SUBS, self.QUERIES))

    def test_collect_sends_one_subreddit_per_listing_run_with_a_full_post_budget(self):
        _, _, calls = run({"listing": [], "search": []}, subs={"A": "x", "B": "x", "C": "x"},
                          reg_extra={"max_posts_per_sub": 7})
        listing = [p for _, p, _ in calls if "subredditUrls" in p]
        self.assertEqual([p["subredditUrls"] for p in listing],
                         [["https://www.reddit.com/r/A/"], ["https://www.reddit.com/r/B/"],
                          ["https://www.reddit.com/r/C/"]])
        self.assertTrue(all(p["maxPostsCount"] == 7 for p in listing))   # each sub keeps its own budget


class PriorityOrderTests(unittest.TestCase):
    """With a spend budget the run can stop part-way, so order is a decision: brand/keyword searches first
    (a handful of cheap runs, and the brand search is the most valuable one), then the broker and F&O/algo
    subreddits, then the rest. Without this the keyword searches came last and the brokers sorted late."""
    CATS = {"Zerodha": "brokers", "groww": "brokers", "IndiaAlgoTrading": "fno_algo", "algotrading": "fno_algo",
            "FIREIndia": "investing_pf", "DalalStreetBets": "market_trading", "IndianStockMarket": "market_trading"}

    def plan(self, **reg):
        return reddit_apify.make_plan({"actor": ACTOR, **reg}, sorted(self.CATS, key=str.lower),
                                      ["nubra broker", "kite connect"], self.CATS)

    def test_searches_run_before_any_listing(self):
        kinds = ["search" if q else "listing" for _, q in self.plan()]
        self.assertEqual(kinds[0], "search")
        self.assertEqual(kinds, sorted(kinds, key=lambda k: k != "search"))      # all searches first

    def test_brokers_then_fno_algo_then_the_rest_keeping_their_own_order(self):
        listing = [s[0] for s, _ in self.plan() if s]
        self.assertEqual(listing, ["groww", "Zerodha", "algotrading", "IndiaAlgoTrading",
                                   "DalalStreetBets", "FIREIndia", "IndianStockMarket"])

    def test_the_priority_categories_are_configurable(self):
        listing = [s[0] for s, _ in self.plan(priority_categories=["market_trading"]) if s]
        self.assertEqual(listing[:2], ["DalalStreetBets", "IndianStockMarket"])

    def test_without_categories_the_given_order_is_kept(self):
        plan = reddit_apify.make_plan({"actor": ACTOR}, ["b", "a"], [])
        self.assertEqual(plan, [(["b"], []), (["a"], [])])

    def test_trudax_is_not_reordered(self):
        reg = {"actor": "trudax~reddit-scraper-lite", "subs_per_run": 5, "queries_per_run": 4}
        self.assertEqual(reddit_apify.make_plan(reg, ["b", "a"], ["q"], {"a": "brokers", "b": "x"}),
                         reddit_apify.plan_runs(reg, ["b", "a"], ["q"]))
