# tests/test_health_checks_data.py
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_data, config
from community.health.model import CRIT, OK, WARN

CFG = {**config.load({}), "_prev": {}}
UTC = timezone.utc


def by_key(results):
    return {r.key: r for r in results}


class PartitionTests(unittest.TestCase):
    def rows(self, upper):
        return [{"parent": t, "upper_bound": upper} for t in CFG["partitions"]["tables"]]

    def run_check(self, upper, now):
        with patch.object(checks_data.db, "query", return_value=self.rows(upper)):
            return by_key(checks_data.check_partitions(CFG, now))

    def test_prod_today_is_a_warning_with_days_left(self):
        res = self.run_check(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC))
        self.assertEqual(res["partitions:social_items"].level, WARN)
        self.assertIn("27 days", res["partitions:social_items"].detail)

    def test_ten_days_before_the_cliff_is_critical(self):
        res = self.run_check(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC))
        self.assertEqual(res["partitions:item_enrichment"].level, CRIT)

    def test_plenty_of_future_partitions_is_ok(self):
        res = self.run_check(datetime(2027, 11, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC))
        self.assertTrue(all(r.level == OK for r in res.values()))

    def test_a_table_with_no_partitions_is_flagged_not_crashed(self):
        with patch.object(checks_data.db, "query", return_value=[]):
            res = by_key(checks_data.check_partitions(CFG, datetime(2026, 10, 5, tzinfo=UTC)))
        self.assertEqual(res["partitions:social_items"].level, WARN)


class FreshnessTests(unittest.TestCase):
    def run_check(self, now, topics=1, daily=True, weekly=True, backlog=0):
        def fake_one(sql, params=None):
            if "topic_daily" in sql:
                return {"n": topics}
            if "roundups" in sql:
                has = daily if "'daily'" in sql else weekly
                return {"x": 1} if has else None
            return {"n": backlog}
        with patch.object(checks_data.db, "one", side_effect=fake_one):
            return by_key(checks_data.check_freshness(CFG, now))

    def test_before_the_expected_times_only_the_backlog_is_checked(self):
        res = self.run_check(datetime(2026, 10, 7, 6, 0, tzinfo=IST))  # a Wednesday
        self.assertEqual(set(res), {"freshness:enrich_backlog"})

    def test_missing_topics_and_roundup_after_their_deadlines_warn(self):
        res = self.run_check(datetime(2026, 10, 7, 8, 5, tzinfo=IST), topics=0, daily=False)
        self.assertEqual(res["freshness:topics"].level, WARN)
        self.assertEqual(res["freshness:daily_roundup"].level, WARN)

    def test_the_08_05_digest_can_judge_both_morning_deadlines(self):
        # the digest runs at 08:05 IST; the roundup is due 07:45 and topics 08:00
        res = self.run_check(datetime(2026, 10, 7, 8, 5, tzinfo=IST))
        self.assertIn("freshness:topics", res)
        self.assertIn("freshness:daily_roundup", res)

    def test_topics_are_judged_over_today_and_yesterday_not_just_today(self):
        seen = {}

        def fake_one(sql, params=None):
            if "topic_daily" in sql:
                seen["params"] = params
                return {"n": 1}
            return {"n": 0} if "item_enrichment" in sql else {"x": 1}

        with patch.object(checks_data.db, "one", side_effect=fake_one):
            checks_data.check_freshness(CFG, datetime(2026, 10, 7, 8, 5, tzinfo=IST))
        self.assertEqual(seen["params"], (date(2026, 10, 6),))  # yesterday, UTC date

    def test_last_saturdays_weekly_roundup_is_checked_from_saturday_11_through_monday(self):
        before = self.run_check(datetime(2026, 10, 10, 10, 0, tzinfo=IST), weekly=False)
        self.assertNotIn("freshness:weekly_roundup", before)           # compose not due yet
        for when in (datetime(2026, 10, 10, 11, 30, tzinfo=IST),       # Saturday after 11:00
                     datetime(2026, 10, 11, 8, 5, tzinfo=IST),         # Sunday digest
                     datetime(2026, 10, 12, 8, 5, tzinfo=IST)):        # Monday digest
            res = self.run_check(when, weekly=False)
            self.assertEqual(res["freshness:weekly_roundup"].level, WARN, when)
        ok = self.run_check(datetime(2026, 10, 11, 8, 5, tzinfo=IST), weekly=True)
        self.assertEqual(ok["freshness:weekly_roundup"].level, OK)
        mid_week = self.run_check(datetime(2026, 10, 14, 8, 5, tzinfo=IST), weekly=False)
        self.assertNotIn("freshness:weekly_roundup", mid_week)

    def test_weekly_roundup_lookup_uses_the_saturday_date(self):
        seen = []

        def fake_one(sql, params=None):
            if "'weekly'" in sql:
                seen.append(params)
                return {"x": 1}
            return {"n": 1} if "topic_daily" in sql or "item_enrichment" in sql else {"x": 1}

        with patch.object(checks_data.db, "one", side_effect=fake_one):
            checks_data.check_freshness(CFG, datetime(2026, 10, 12, 8, 5, tzinfo=IST))  # Monday
        self.assertEqual(seen, [(date(2026, 10, 10),)])

    def test_enrichment_backlog_threshold(self):
        now = datetime(2026, 10, 7, 6, 0, tzinfo=IST)
        self.assertEqual(self.run_check(now, backlog=500)["freshness:enrich_backlog"].level, WARN)
        self.assertEqual(self.run_check(now, backlog=50)["freshness:enrich_backlog"].level, OK)


class SourceTests(unittest.TestCase):
    NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    REGISTRY = {"sources": {"twitter": {"enabled": True}, "reddit": {"enabled": True},
                            "youtube": {"enabled": True}, "github": {"enabled": False},
                            "app_reviews": {"enabled": True}}}

    def run_check(self, state_rows, newest_rows):
        def fake_query(sql, params=None):
            return state_rows if "pipeline_state" in sql else newest_rows
        with patch.object(checks_data, "settings", SimpleNamespace(registry=self.REGISTRY)), \
             patch.object(checks_data.db, "query", side_effect=fake_query):
            return by_key(checks_data.check_sources(CFG, self.NOW))

    def st(self, source, ok_h_ago=1.0, err=None, err_h_ago=None):
        return {"source": source, "last_success_at": self.NOW - timedelta(hours=ok_h_ago),
                "last_error": err,
                "last_error_at": None if err_h_ago is None else self.NOW - timedelta(hours=err_h_ago)}

    def test_healthy_sources_are_ok(self):
        res = self.run_check([self.st("twitter"), self.st("youtube", 5), self.st("app_review", 5)],
                             [{"source": "twitter", "newest": self.NOW - timedelta(hours=1)}])
        self.assertEqual(res["source:twitter"].level, OK)
        self.assertEqual(res["source:youtube"].level, OK)
        self.assertEqual(res["source_items:twitter"].level, OK)

    def test_muted_and_disabled_sources_produce_no_results(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertNotIn("source:reddit", res)   # muted by default
        self.assertNotIn("source:github", res)   # disabled in the registry

    def test_stale_daily_collector_warns(self):
        res = self.run_check([self.st("twitter"), self.st("youtube", ok_h_ago=40)], [])
        self.assertEqual(res["source:youtube"].level, WARN)
        self.assertIn("40 h", res["source:youtube"].detail)

    def test_a_failed_latest_run_warns_with_the_error(self):
        res = self.run_check([self.st("twitter"),
                              self.st("youtube", 2, err="HTTPError: 403 quota", err_h_ago=1)], [])
        self.assertEqual(res["source:youtube"].level, WARN)
        self.assertIn("403 quota", res["source:youtube"].detail)

    def test_enabled_source_with_no_state_row_does_not_crash(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertEqual(res["source:app_reviews"].level, WARN)
        self.assertIn("not recorded", res["source:app_reviews"].detail)

    def test_volume_source_with_no_recent_items_warns(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertEqual(res["source_items:twitter"].level, WARN)
        res = self.run_check([self.st("twitter")],
                             [{"source": "twitter", "newest": self.NOW - timedelta(hours=30)}])
        self.assertEqual(res["source_items:twitter"].level, WARN)
