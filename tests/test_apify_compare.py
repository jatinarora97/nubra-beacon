"""Tooling to compare Reddit actors on Apify with one small standard job (no DB, capped spend)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.scrape import apify_compare, reddit_apify
from tests.test_reddit_apify import FakeApifyClient

SUBS = ["IndianStockMarket", "Zerodha"]
SINCE = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")


class BuildInputTests(unittest.TestCase):
    def test_harshmaur_listing_job_uses_its_subreddit_comment_and_date_fields(self):
        i = apify_compare.build_input("harshmaur", "listing", SUBS, posts=5, comments=3, days=3)
        self.assertEqual(i["subredditUrls"], ["https://www.reddit.com/r/IndianStockMarket/",
                                              "https://www.reddit.com/r/Zerodha/"])
        self.assertEqual((i["maxPostsCount"], i["maxCommentsPerPost"]), (10, 3))  # posts is a TOTAL
        self.assertTrue(i["crawlCommentsPerPost"])
        self.assertEqual((i["postedAfter"], i["commentedAfter"]), (SINCE, SINCE))

    def test_harshmaur_search_job_searches_a_keyword_by_date(self):
        i = apify_compare.build_input("harshmaur", "search", SUBS, posts=5, comments=3, days=3)
        self.assertEqual((i["searchTerms"], i["searchSort"], i["searchTime"]), (["nubra"], "new", "week"))
        self.assertEqual(i["postedAfter"], SINCE)

    def test_automation_lab_listing_job_asks_for_new_posts_with_nested_comments(self):
        i = apify_compare.build_input("automation-lab", "listing", SUBS, posts=5, comments=3, days=3)
        self.assertEqual(i["urls"], ["https://www.reddit.com/r/IndianStockMarket/",
                                     "https://www.reddit.com/r/Zerodha/"])
        self.assertEqual((i["sort"], i["maxPostsPerSource"], i["maxCommentsPerPost"]), ("new", 5, 3))
        self.assertTrue(i["includeComments"])
        self.assertEqual(i["commentDepth"], 3)

    def test_automation_lab_search_job_is_a_single_query_without_comments(self):
        i = apify_compare.build_input("automation-lab", "search", SUBS, posts=5, comments=3, days=3)
        self.assertEqual((i["searchQuery"], i["timeFilter"], i["sort"]), ("nubra", "week", "new"))
        self.assertFalse(i["includeComments"])

    def test_epctex_jobs_use_start_urls_and_a_single_search(self):
        listing = apify_compare.build_input("epctex", "listing", SUBS, posts=5, comments=3, days=3)
        self.assertEqual(len(listing["startUrls"]), 2)
        self.assertTrue(listing["includeComments"])
        self.assertEqual(listing["maxItems"], 2 * 5 * (1 + 3))
        search = apify_compare.build_input("epctex", "search", SUBS, posts=5, comments=3, days=3)
        self.assertEqual((search["search"], search["sort"], search["time"]), ("nubra", "new", "week"))

    def test_unknown_actor_or_job_is_an_error(self):
        with self.assertRaises(KeyError):
            apify_compare.build_input("nope", "listing", SUBS, 5, 3, 3)
        with self.assertRaises(KeyError):
            apify_compare.build_input("epctex", "nope", SUBS, 5, 3, 3)

    def test_the_actor_ids_are_the_real_store_ids(self):
        self.assertEqual(apify_compare.ACTORS["harshmaur"], "harshmaur~reddit-scraper-pro")
        self.assertEqual(apify_compare.ACTORS["automation-lab"], "automation-lab~reddit-scraper")
        self.assertEqual(apify_compare.ACTORS["epctex"], "epctex~reddit-scraper")
        self.assertNotIn("microworlds", " ".join(apify_compare.ACTORS.values()))  # that actor is an Apollo scraper


class InspectItemsTests(unittest.TestCase):
    POST = {"id": "t3_a", "dataType": "post", "title": "Hi", "createdAt": "2026-10-09T07:07:48.365Z", "upVotes": 3}
    COMMENT = {"id": "t1_b", "dataType": "comment", "body": "yes", "createdAt": "2026-10-09T08:00:00.000Z",
               "parentId": "t1_a", "depth": 1}

    def test_it_reports_fields_dates_and_whether_replies_are_nested(self):
        info = apify_compare.inspect_items([self.POST, self.COMMENT])
        self.assertEqual(info["count"], 2)
        self.assertIn("createdAt", info["fields"])
        self.assertTrue(info["has_threading"])
        self.assertEqual(info["date_field"], "createdAt")
        self.assertEqual(info["oldest"], "2026-10-09T07:07:48.365Z")
        self.assertEqual(info["newest"], "2026-10-09T08:00:00.000Z")
        self.assertEqual(info["sample_post"]["id"], "t3_a")
        self.assertEqual(info["sample_comment"]["id"], "t1_b")

    def test_an_actor_with_no_dates_or_threading_is_reported_as_such(self):
        info = apify_compare.inspect_items([{"title": "x", "url": "u"}])
        self.assertIsNone(info["date_field"])
        self.assertFalse(info["has_threading"])
        self.assertIsNone(info["sample_comment"])

    def test_empty_output_is_not_an_error(self):
        info = apify_compare.inspect_items([])
        self.assertEqual((info["count"], info["fields"], info["oldest"]), (0, [], None))


class SpendCapTests(unittest.TestCase):
    def test_the_actor_run_carries_a_hard_charge_cap_when_asked(self):
        client = FakeApifyClient("SUCCEEDED", [], cost=0.05)
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            reddit_apify._run_actor("a~b", {}, max_charge_usd=0.15)
        self.assertEqual(client.posts[0][1]["maxTotalChargeUsd"], 0.15)

    def test_no_cap_parameter_is_sent_by_default(self):
        client = FakeApifyClient("SUCCEEDED", [])
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            reddit_apify._run_actor("a~b", {})
        self.assertNotIn("maxTotalChargeUsd", client.posts[0][1])


class RunJobTests(unittest.TestCase):
    ITEMS = [InspectItemsTests.POST, InspectItemsTests.COMMENT]

    def run_job(self, client, job="listing"):
        del reddit_apify.run_log[:]
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            return apify_compare.run_job("harshmaur", job, SUBS, posts=5, comments=3, days=3,
                                         cap_usd=0.15, timeout_s=60)

    def test_a_good_run_reports_items_cost_and_carries_the_cap(self):
        client = FakeApifyClient("SUCCEEDED", self.ITEMS, cost=0.04)
        r = self.run_job(client)
        self.assertEqual((r["status"], r["info"]["count"], r["error"]), ("SUCCEEDED", 2, None))
        self.assertAlmostEqual(r["cost_usd"], 0.04)
        self.assertEqual(client.posts[0][1]["maxTotalChargeUsd"], 0.15)

    def test_a_rejected_input_reports_the_reason_apify_gave(self):
        class Rejecting(FakeApifyClient):
            def post(self, url, params=None, json=None):
                def boom():
                    raise reddit_apify.httpx.HTTPStatusError(
                        "400 Bad Request", request=None,
                        response=SimpleNamespace(text='{"error":{"message":"Field input.crawlComments is not allowed"}}'))
                return SimpleNamespace(raise_for_status=boom, json=lambda: {})
        r = self.run_job(Rejecting("SUCCEEDED", []))
        self.assertIn("crawlComments is not allowed", r["error"])
        self.assertEqual((r["status"], r["info"]["count"]), ("ERROR", 0))
        self.assertIn("subredditUrls", r["payload"])   # the input that was sent stays reportable

    def test_a_run_that_dies_with_nothing_is_an_error_not_a_crash(self):
        r = self.run_job(FakeApifyClient("FAILED", []))
        self.assertIn("FAILED", r["error"])
        self.assertEqual(r["status"], "FAILED")


class BilledEventsAndFullSamplesTests(unittest.TestCase):
    """Cost is only trustworthy with Apify's own per-event counts; samples must not be cut mid-field."""

    def test_the_run_log_keeps_apifys_charged_event_counts(self):
        class Billed(FakeApifyClient):
            def get(self, url, params=None):
                if "/actor-runs/" in url:
                    return self._resp({"data": {"status": "SUCCEEDED", "usageTotalUsd": 0.01,
                                                "chargedEventCounts": {"result": 36, "actor-start": 1}}})
                return self._resp(self.items)
        client = Billed("SUCCEEDED", [InspectItemsTests.POST])
        del reddit_apify.run_log[:]
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            r = apify_compare.run_job("harshmaur", "listing", SUBS, posts=5, comments=3, days=3,
                                      cap_usd=0.15, timeout_s=60)
        self.assertEqual(reddit_apify.run_log[-1]["events"], {"result": 36, "actor-start": 1})
        self.assertEqual(r["events"], {"result": 36, "actor-start": 1})

    def test_a_run_without_event_counts_logs_an_empty_dict(self):
        client = FakeApifyClient("SUCCEEDED", [])
        del reddit_apify.run_log[:]
        with patch.object(reddit_apify.httpx, "Client", return_value=client), \
             patch.object(reddit_apify.time, "sleep"), \
             patch.object(reddit_apify, "_token", return_value="tok"):
            reddit_apify._run_actor("a~b", {})
        self.assertEqual(reddit_apify.run_log[-1]["events"], {})

    def report_text(self, **kw):
        import contextlib
        import io
        post = dict(InspectItemsTests.POST, body="x" * 3000, tail="END-OF-ITEM")
        result = {"actor": "harshmaur", "job": "listing", "payload": {}, "error": None,
                  "info": apify_compare.inspect_items([post, InspectItemsTests.COMMENT]),
                  "status": "SUCCEEDED", "cost_usd": 0.01, "seconds": 12, "events": {"result": 2}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            apify_compare.report([result], **kw)
        return buf.getvalue()

    def test_the_report_prints_the_billed_events(self):
        self.assertIn("billed events: {'result': 2}", self.report_text())

    def test_samples_are_cut_by_default_but_whole_when_asked(self):
        self.assertNotIn("END-OF-ITEM", self.report_text())
        self.assertIn("END-OF-ITEM", self.report_text(sample_chars=10000))
