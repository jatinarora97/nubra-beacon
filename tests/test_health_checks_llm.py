# tests/test_health_checks_llm.py
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_llm, config
from community.health.model import CRIT, OK, WARN
from community.health.state import Row

CFG = {**config.load({}), "_prev": {}}
DUE = datetime(2026, 10, 5, 12, 5, tzinfo=IST)        # minute 5: the hourly probe slot
NOT_DUE = datetime(2026, 10, 5, 12, 40, tzinfo=IST)


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class BadRequestError(Exception):
    pass


def with_key(key="sk-test"):
    return patch.object(checks_llm, "settings", SimpleNamespace(anthropic_api_key=key, enrich_model="m"))


def crit_row(key):
    return Row(key, "crit", "x", DUE, DUE, DUE, 0)


class ProbeDueTests(unittest.TestCase):
    def test_gate(self):
        self.assertTrue(checks_llm.probe_due(CFG, DUE, None))
        self.assertFalse(checks_llm.probe_due(CFG, NOT_DUE, "ok"))
        self.assertTrue(checks_llm.probe_due(CFG, NOT_DUE, "crit"))      # re-check while failing
        self.assertTrue(checks_llm.probe_due({**CFG, "_force": True}, NOT_DUE, None))


class AnthropicKeyTests(unittest.TestCase):
    def test_skipped_outside_the_hourly_slot(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe") as probe:
            self.assertEqual(checks_llm.check_anthropic_key(CFG, NOT_DUE), [])
        probe.assert_not_called()

    def test_valid_key_is_ok(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe"):
            res = checks_llm.check_anthropic_key(CFG, DUE)
        self.assertEqual([(r.key, r.level) for r in res], [("anthropic_key", OK)])

    def test_missing_key_is_critical_without_calling_the_api(self):
        with with_key(""), patch.object(checks_llm, "_count_tokens_probe") as probe:
            res = checks_llm.check_anthropic_key(CFG, DUE)
        self.assertEqual(res[0].level, CRIT)
        probe.assert_not_called()

    def test_auth_error_and_exhausted_credit_are_critical(self):
        for exc in (AuthenticationError("invalid x-api-key"),
                    BadRequestError("Your credit balance is too low")):
            with with_key(), patch.object(checks_llm, "_count_tokens_probe", side_effect=exc):
                self.assertEqual(checks_llm.check_anthropic_key(CFG, DUE)[0].level, CRIT)

    def test_a_network_error_is_only_a_warning(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe",
                                      side_effect=APIConnectionError("timeout")):
            self.assertEqual(checks_llm.check_anthropic_key(CFG, DUE)[0].level, WARN)

    def test_runs_every_time_while_already_critical(self):
        cfg = {**CFG, "_prev": {"anthropic_key": crit_row("anthropic_key")}}
        with with_key(), patch.object(checks_llm, "_count_tokens_probe") as probe:
            checks_llm.check_anthropic_key(cfg, NOT_DUE)
        probe.assert_called_once()


    def test_probe_uses_a_short_timeout_and_no_retries(self):
        with with_key(), patch("community.llm.client.client") as factory:
            checks_llm._count_tokens_probe()
        factory.return_value.with_options.assert_called_once_with(timeout=15.0, max_retries=0)
        factory.return_value.with_options.return_value.messages.count_tokens.assert_called_once()

    def test_a_transient_error_while_critical_keeps_the_critical(self):
        prev = Row("anthropic_key", "crit", "AuthenticationError: invalid x-api-key", DUE, DUE, DUE, 0)
        cfg = {**CFG, "_prev": {"anthropic_key": prev}}
        with with_key(), patch.object(checks_llm, "_count_tokens_probe",
                                      side_effect=APIConnectionError("timeout")):
            res = checks_llm.check_anthropic_key(cfg, NOT_DUE)
        self.assertEqual([(r.key, r.level) for r in res], [("anthropic_key", CRIT)])
        self.assertIn("AuthenticationError", res[0].detail)


class CreditsTests(unittest.TestCase):
    """X exhaustion cannot be read from pipeline_state: ingest degrades every X failure
    (402 included) to a note and still stamps last_success_at. So the check is symptom
    based: no new twitter item for a long time while the scraper itself is running."""

    def x_row(self, ran_h_ago, newest_h_ago):
        return {"ran": None if ran_h_ago is None else DUE - timedelta(hours=ran_h_ago),
                "newest": None if newest_h_ago is None else DUE - timedelta(hours=newest_h_ago)}

    def run_check(self, row, apify, now=DUE, cfg=CFG):
        with patch.object(checks_llm.db, "one", return_value=row),              patch.object(checks_llm, "_apify_usage", return_value=apify):
            return {r.key: r for r in checks_llm.check_credits(cfg, now)}

    def test_no_new_x_items_while_the_scraper_runs_is_critical(self):
        res = self.run_check(self.x_row(1, 14), None)
        self.assertEqual(res["credits:x"].level, CRIT)
        self.assertIn("14 h", res["credits:x"].detail)

    def test_no_x_items_at_all_in_three_days_is_critical(self):
        self.assertEqual(self.run_check(self.x_row(1, None), None)["credits:x"].level, CRIT)

    def test_fresh_x_items_are_ok(self):
        self.assertEqual(self.run_check(self.x_row(1, 2), None)["credits:x"].level, OK)

    def test_a_stopped_scraper_is_left_to_the_job_checks(self):
        self.assertEqual(self.run_check(self.x_row(10, 20), None)["credits:x"].level, OK)
        self.assertEqual(self.run_check(self.x_row(None, None), None)["credits:x"].level, OK)
        self.assertEqual(self.run_check(None, None)["credits:x"].level, OK)

    def test_x_check_is_skipped_when_twitter_is_muted(self):
        cfg = {**CFG, "muted": ["reddit", "twitter"]}
        self.assertNotIn("credits:x", self.run_check(self.x_row(1, 30), None, cfg=cfg))

    def test_apify_usage_levels(self):
        self.assertEqual(self.run_check(None, (49.5, 50.0))["credits:apify"].level, CRIT)
        self.assertEqual(self.run_check(None, (40.0, 50.0))["credits:apify"].level, WARN)
        self.assertEqual(self.run_check(None, (10.0, 50.0))["credits:apify"].level, OK)

    def test_apify_not_probed_outside_the_hourly_slot_and_without_a_token(self):
        self.assertNotIn("credits:apify", self.run_check(None, (49.5, 50.0), now=NOT_DUE))
        self.assertNotIn("credits:apify", self.run_check(None, None))


class LlmUsageTests(unittest.TestCase):
    NOW = datetime(2026, 10, 5, 12, 0, tzinfo=IST)  # "yesterday" is 2026-10-04

    def run_check(self, calls=5, unpriced=0, yesterday=2.0, base=2.0):
        daily = [{"d": date(2026, 9, 27) + timedelta(days=i), "cost": base} for i in range(7)]
        daily += [{"d": date(2026, 10, 4), "cost": yesterday}, {"d": date(2026, 10, 5), "cost": 0.5}]

        def fake_one(sql, params=None):
            return {"n": unpriced if "cost_usd IS NULL" in sql else calls}

        with patch.object(checks_llm.db, "one", side_effect=fake_one), \
             patch.object(checks_llm.db, "query", return_value=daily):
            return {r.key: r for r in checks_llm.check_llm_usage(CFG, self.NOW)}

    def test_no_calls_in_24h_warns(self):
        self.assertEqual(self.run_check(calls=0)["llm:calls"].level, WARN)
        self.assertEqual(self.run_check(calls=3)["llm:calls"].level, OK)

    def test_spend_spike_over_three_times_the_median_warns(self):
        self.assertEqual(self.run_check(yesterday=9.0)["llm:spend"].level, WARN)
        self.assertEqual(self.run_check(yesterday=5.0)["llm:spend"].level, OK)

    def test_spend_floor_stops_tiny_baselines_from_alerting(self):
        self.assertEqual(self.run_check(yesterday=0.9, base=0.1)["llm:spend"].level, OK)
        self.assertEqual(self.run_check(yesterday=1.5, base=0.1)["llm:spend"].level, WARN)

    def test_unpriced_models_warn(self):
        self.assertEqual(self.run_check(unpriced=3)["llm:unpriced"].level, WARN)
        self.assertEqual(self.run_check(unpriced=0)["llm:unpriced"].level, OK)
