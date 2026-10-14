"""The data-staleness report: verdicts, gap filling, silent-subreddit matching and rendering (no database)."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from community.health import config as health_config
from community.health import staleness

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def ago(**kw):
    return NOW - timedelta(**kw)


def row(total=100, arrival=None, content=None):
    return {"total": total, "newest_ingested": arrival or ago(hours=1), "newest_created": content or ago(hours=2)}


class FormatTests(unittest.TestCase):
    def test_ages_use_the_unit_that_reads_best(self):
        self.assertEqual(staleness.fmt_age(ago(minutes=20), NOW), "20 min ago")
        self.assertEqual(staleness.fmt_age(ago(hours=5), NOW), "5.0 h ago")
        self.assertEqual(staleness.fmt_age(ago(days=12), NOW), "12.0 d ago")
        self.assertEqual(staleness.fmt_age(None, NOW), "never")

    def test_timestamps_are_shown_in_ist(self):
        self.assertEqual(staleness.fmt_ts(datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)), "2026-10-14 05:30 IST")
        self.assertEqual(staleness.fmt_ts(None), "never")


class LimitTests(unittest.TestCase):
    cfg = health_config.load({})

    def test_the_limits_are_the_health_monitors(self):
        self.assertEqual(staleness.freshness_limit_hours("twitter", self.cfg, {}), 10)
        self.assertEqual(staleness.freshness_limit_hours("reddit", self.cfg, {}), 12)

    def test_reddit_is_judged_nightly_once_the_apify_collector_is_on(self):
        on = {"sources": {"reddit_apify": {"enabled": True}}}
        self.assertEqual(staleness.freshness_limit_hours("reddit", self.cfg, on), 30)
        off = {"sources": {"reddit_apify": {"enabled": False}}}
        self.assertEqual(staleness.freshness_limit_hours("reddit", self.cfg, off), 12)


class VerdictTests(unittest.TestCase):
    def test_fresh_arrivals_are_ok(self):
        v = staleness.verdict("reddit", row(), NOW, 30)
        self.assertEqual(v["status"], "ok")

    def test_an_old_newest_arrival_is_stale_and_says_how_old(self):
        v = staleness.verdict("reddit", row(arrival=ago(days=3), content=ago(days=3)), NOW, 12)
        self.assertEqual(v["status"], "STALE")
        self.assertIn("3.0 d ago", v["why"])
        self.assertIn("allowed 12 h", v["why"])

    def test_fresh_arrivals_of_old_content_are_a_different_problem(self):
        # a CSV re-import: rows keep arriving but the newest tweet is a week old
        v = staleness.verdict("reddit", row(arrival=ago(hours=1), content=ago(days=7)), NOW, 30)
        self.assertEqual(v["status"], "OLD-CONTENT")
        self.assertIn("source time", v["why"])

    def test_an_empty_source_is_reported_as_empty(self):
        self.assertEqual(staleness.verdict("twitter", None, NOW, 10)["status"], "EMPTY")
        self.assertEqual(staleness.verdict("twitter", {"total": 0}, NOW, 10)["status"], "EMPTY")

    def test_twitter_that_never_had_a_live_row_is_stale_even_if_the_csv_is_fresh(self):
        v = staleness.verdict("twitter", row(), NOW, 10, live_last=None)
        self.assertEqual(v["status"], "STALE")
        self.assertIn("never produced", v["why"])

    def test_twitter_whose_live_api_stopped_is_stale(self):
        v = staleness.verdict("twitter", row(), NOW, 10, live_last=ago(days=9))
        self.assertEqual(v["status"], "STALE")
        self.assertIn("live X API last delivered 9.0 d ago", v["why"])

    def test_twitter_with_a_recent_live_row_is_ok(self):
        self.assertEqual(staleness.verdict("twitter", row(), NOW, 10, live_last=ago(hours=2))["status"], "ok")


class FillDaysTests(unittest.TestCase):
    TODAY = date(2026, 10, 14)

    def test_every_day_in_the_window_appears_and_empty_days_are_zero(self):
        rows = [{"day": date(2026, 10, 14), "source": "reddit", "channel": "apify_reddit_pro",
                 "source_type": "post", "n": 5},
                {"day": date(2026, 10, 12), "source": "twitter", "channel": "live_api", "source_type": "tweet", "n": 3}]
        days = staleness.fill_days(rows, 3, self.TODAY)
        self.assertEqual([d["day"] for d in days], [date(2026, 10, 11), date(2026, 10, 12),
                                                    date(2026, 10, 13), date(2026, 10, 14)])
        self.assertEqual(days[0]["reddit_posts"] + days[0]["twitter_live"], 0)       # 11 Oct: nothing
        self.assertEqual(days[1]["twitter_live"], 3)
        self.assertEqual(days[3]["reddit_posts"], 5)

    def test_channels_and_types_are_split(self):
        rows = [{"day": self.TODAY, "source": "twitter", "channel": "csv_backfill", "source_type": "tweet", "n": 7},
                {"day": self.TODAY, "source": "twitter", "channel": "other", "source_type": "tweet", "n": 1},
                {"day": self.TODAY, "source": "reddit", "channel": "zanshash_scraper", "source_type": "comment", "n": 9}]
        d = staleness.fill_days(rows, 0, self.TODAY)[0]
        self.assertEqual((d["twitter_csv"], d["twitter_other"], d["reddit_comments"], d["reddit_posts"]), (7, 1, 9, 0))


class SilentSubredditTests(unittest.TestCase):
    WATCHED = [{"value": "Zerodha", "category": "brokers"}, {"value": "IndianStockMarket", "category": "market_trading"},
               {"value": "groww", "category": "brokers"}]
    SUBS = [{"sub": "indianstockmarket", "name": "IndianStockMarket", "category": "market_trading",
             "posts": 40, "comments": 200},
            {"sub": "somewhereelse", "name": "SomewhereElse", "category": "keyword", "posts": 2, "comments": 0}]

    def test_every_watched_subreddit_is_listed_silent_ones_first(self):
        out = staleness.silent_watched(self.WATCHED, self.SUBS, {"zerodha": ago(days=20)})
        self.assertEqual([r["sub"] for r in out], ["groww", "Zerodha", "IndianStockMarket"])
        self.assertEqual([r["posts"] for r in out], [0, 0, 40])

    def test_the_newest_post_ever_is_attached_case_insensitively(self):
        out = staleness.silent_watched(self.WATCHED, self.SUBS, {"zerodha": ago(days=20)})
        z = next(r for r in out if r["sub"] == "Zerodha")
        self.assertEqual(z["newest_post"], ago(days=20))
        self.assertIsNone(next(r for r in out if r["sub"] == "groww")["newest_post"])


def make_report(**over):
    summary = {"reddit": {"source": "reddit", "total": 5000, "last_24h": 300, "last_7d": 1500, "last_30d": 4000,
                          "newest_ingested": ago(hours=3), "oldest_ingested": ago(days=170),
                          "newest_created": ago(hours=5), "oldest_created": ago(days=171)}}
    rep = {"now": NOW, "days": 3, "errors": {}, "summary": summary,
           "channels": [{"source": "reddit", "channel": "apify_reddit_pro", "rows": 700, "first_ingested": ago(days=2),
                         "last_ingested": ago(hours=3), "newest_created": ago(hours=5)}],
           "verdicts": [staleness.verdict("reddit", summary["reddit"], NOW, 30),
                        staleness.verdict("twitter", None, NOW, 10)],
           "daily": staleness.fill_days([], 3, date(2026, 10, 14)),
           "lag": {"reddit": {"n": 100, "median_h": 12.5, "p90_h": 40.0}},
           "subreddits": staleness.silent_watched(SilentSubredditTests.WATCHED, SilentSubredditTests.SUBS, {}),
           "other_subreddits": [{"sub": "x", "posts": 3}], "watched_x": [{"kind": "x_handle", "n": 12}],
           "pipeline": [{"stage": "ingest", "source": "reddit", "watermark": None, "last_success_at": ago(hours=3),
                         "last_error": None, "last_error_at": None, "items_last_run": 699},
                        {"stage": "ingest", "source": "twitter", "watermark": None, "last_success_at": ago(days=9),
                         "last_error": "RuntimeError: 402 credits exhausted", "last_error_at": ago(hours=1),
                         "items_last_run": 0}],
           "enrichment": {"reddit": {"source": "reddit", "items": 1000, "enriched": 950,
                                     "oldest_unenriched": ago(hours=6), "newest_enriched": ago(hours=1)}},
           "conversations": {}, "opportunities": {}, "topics_newest_day": date(2026, 10, 14),
           "partitions": [{"parent": "social_items", "upper_bound": datetime(2026, 11, 1, tzinfo=timezone.utc)}]}
    rep.update(over)
    return rep


class RenderTests(unittest.TestCase):
    def test_the_report_has_every_section_and_the_headline_findings(self):
        text = staleness.render(make_report())
        for heading in ("1. VERDICT", "2. ARRIVAL vs SOURCE TIME", "3. WHERE THE ROWS COME FROM",
                        "4. ARRIVALS PER DAY", "5. WATCHED SUBREDDITS", "6. TWITTER WATCH LIST",
                        "7. PIPELINE STATE", "8. DOWNSTREAM", "9. HARD STOP AHEAD"):
            self.assertIn(heading, text)
        self.assertIn("twitter  EMPTY", text)
        self.assertIn("2 of 3 watched subreddits produced no posts", text)
        self.assertIn("LAST ERROR", text)                       # the twitter 402 shows up
        self.assertIn("402 credits exhausted", text)
        self.assertIn("days left", text)
        self.assertIn("apify_reddit_pro", text)
        self.assertIn("median 12.5 h, p90 40.0 h", text)

    def test_days_with_nothing_are_marked(self):
        self.assertIn("<- nothing from either source", staleness.render(make_report()))

    def test_it_survives_a_report_where_queries_failed_and_says_so(self):
        text = staleness.render(make_report(summary={}, verdicts=[], channels=[], pipeline=[], partitions=[],
                                            errors={"summary": "OperationalError: relation does not exist"}))
        self.assertIn("QUERIES THAT FAILED", text)
        self.assertIn("relation does not exist", text)
        self.assertIn("reddit: no rows", text)

    def test_the_text_is_plain_ascii_so_any_terminal_prints_it(self):
        staleness.render(make_report()).encode("ascii")


if __name__ == "__main__":
    unittest.main()
