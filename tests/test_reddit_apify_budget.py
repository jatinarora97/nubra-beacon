"""Reddit shares one Apify account (and its monthly usage limit) with Instagram and LinkedIn.

Found on 2026-10-11: `./cm doctor` showed $21.27 of $29 already used in the cycle, so Reddit's ~$2/night
would have used the rest in about four nights and then broken the collectors that already work. Reddit must
stop on its own before that, and must say so.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from community.scrape import extra_sources, reddit_apify
from tests.test_reddit_apify_pro import ACTOR, CATS, COMMENT, POST


def costed_run(cost, rows=()):
    """A stand-in for _run_actor that bills `cost` per run like the real one does."""
    calls = []

    def fake(actor, payload, **kw):
        calls.append(payload)
        reddit_apify.run_costs_usd += cost
        return list(rows)
    return fake, calls


def collect(fake, *, usage=None, subs=CATS, reg_extra=None, keywords=()):
    reddit_apify.run_costs_usd = 0.0
    reg = {"enabled": True, "actor": ACTOR, **(reg_extra or {})}
    with patch.object(reddit_apify, "_run_actor", side_effect=fake), \
         patch.object(reddit_apify, "_token", return_value="tok"), \
         patch.object(reddit_apify, "_account_usage", return_value=usage), \
         patch.object(reddit_apify, "_subreddits", return_value=subs), \
         patch.object(reddit_apify, "_active_keywords", return_value=list(keywords)):
        return reddit_apify.collect(reg)


MANY = {f"sub{i}": "x" for i in range(10)}


class AccountGuardTests(unittest.TestCase):
    def test_the_defaults_leave_room_for_instagram_and_linkedin(self):
        self.assertEqual(reddit_apify.DEFAULT_ACCOUNT_STOP_PCT, 85)
        self.assertEqual(reddit_apify.DEFAULT_NIGHTLY_BUDGET_USD, 2.5)

    def test_an_account_already_past_the_line_runs_nothing_and_says_why(self):
        fake, calls = costed_run(0.5)
        with self.assertRaises(RuntimeError) as ctx:
            collect(fake, usage=(26.0, 29.0))                 # 90% used
        self.assertEqual(calls, [])
        self.assertIn("not run", str(ctx.exception))
        self.assertIn("monthly limit", str(ctx.exception))

    def test_it_stops_mid_job_when_its_own_spend_crosses_the_line_and_keeps_what_it_has(self):
        # 20.0 used of 29 (69%); each run bills 2.5; the line is 85% = 24.65
        fake, calls = costed_run(2.5, rows=[POST, COMMENT])
        subs = {"IndianStockMarket": "x", **{f"sub{i}": "x" for i in range(9)}}   # the sample post's sub is watched
        items, stats = collect(fake, usage=(20.0, 29.0), subs=subs,
                               reg_extra={"nightly_budget_usd": None})           # isolate the account line
        self.assertEqual(len(calls), 2)                       # 22.5 -> 25.0 (crossed) -> stop
        self.assertEqual(len(items), 2)                       # the same post/comment from both runs, kept once
        self.assertIn("monthly limit", stats["budget_stopped"])
        self.assertAlmostEqual(stats["budget"]["spent_usd"], 5.0)

    def test_below_the_line_everything_runs(self):
        fake, calls = costed_run(0.1)
        _, stats = collect(fake, usage=(10.0, 29.0), subs=MANY)
        self.assertEqual(len(calls), 10)
        self.assertNotIn("budget_stopped", stats)

    def test_the_line_is_configurable(self):
        fake, calls = costed_run(0.1)
        with self.assertRaises(RuntimeError):
            collect(fake, usage=(15.0, 29.0), reg_extra={"account_stop_pct": 50})   # 52% >= 50
        self.assertEqual(calls, [])

    def test_an_unreadable_account_does_not_block_the_run(self):
        fake, calls = costed_run(0.1)
        collect(fake, usage=None, subs=MANY)
        self.assertEqual(len(calls), 10)                      # the per-run cap and nightly budget still apply

    def test_null_switches_the_account_guard_off_without_even_asking_apify(self):
        fake, calls = costed_run(0.1)
        with patch.object(reddit_apify, "_account_usage") as usage:
            reddit_apify.run_costs_usd = 0.0
            with patch.object(reddit_apify, "_run_actor", side_effect=fake), \
                 patch.object(reddit_apify, "_token", return_value="tok"), \
                 patch.object(reddit_apify, "_subreddits", return_value=MANY), \
                 patch.object(reddit_apify, "_active_keywords", return_value=[]):
                reddit_apify.collect({"enabled": True, "actor": ACTOR, "account_stop_pct": None,
                                      "nightly_budget_usd": None})
        usage.assert_not_called()
        self.assertEqual(len(calls), 10)


class NightlyBudgetTests(unittest.TestCase):
    def test_a_job_stops_launching_runs_once_its_own_budget_is_spent(self):
        fake, calls = costed_run(0.6, rows=[POST])
        _, stats = collect(fake, subs=MANY, reg_extra={"nightly_budget_usd": 1.0})
        self.assertEqual(len(calls), 2)                       # 0.6 -> 1.2 (>= 1.0) -> stop
        self.assertIn("budget", stats["budget_stopped"])

    def test_the_default_budget_applies_when_the_registry_is_silent(self):
        fake, calls = costed_run(1.3)
        collect(fake, subs=MANY)
        self.assertEqual(len(calls), 2)                       # 1.3 -> 2.6 (>= 2.5)

    def test_a_realistic_full_night_fits_under_the_default_budget(self):
        # measured 2026-10-14: ~$0.0015 per row, ~1,000 billed rows + 24 x $0.01 start fees = about $1.9 for
        # 24 runs. The old $1.50 budget cut every night short; the default must let all of them run.
        fake, calls = costed_run(0.08)
        subs = {f"sub{i}": "x" for i in range(24)}
        _, stats = collect(fake, subs=subs)
        self.assertEqual(len(calls), 24)
        self.assertNotIn("budget_stopped", stats)

    def test_null_removes_the_nightly_budget(self):
        fake, calls = costed_run(0.8)
        collect(fake, subs=MANY, reg_extra={"nightly_budget_usd": None})
        self.assertEqual(len(calls), 10)

    def test_a_cheap_job_reports_what_it_spent(self):
        fake, _ = costed_run(0.05, rows=[POST])
        _, stats = collect(fake, usage=(10.0, 29.0), subs={"a": "x", "b": "x"})
        self.assertAlmostEqual(stats["budget"]["spent_usd"], 0.1)
        self.assertAlmostEqual(stats["budget"]["account_used_pct"], (10.1 / 29.0) * 100, places=1)


class FetchSurfacesAPartialRunTests(unittest.TestCase):
    def test_items_are_yielded_first_then_the_early_stop_is_raised_so_health_sees_it(self):
        stats = {"budget_stopped": "the Apify account is at 86% of its $29 monthly limit"}
        with patch.object(reddit_apify, "collect", return_value=(["a", "b"], stats)):
            seen = []
            gen = reddit_apify.fetch({"enabled": True})
            seen.append(next(gen))
            seen.append(next(gen))
            with self.assertRaises(RuntimeError) as ctx:
                next(gen)
        self.assertEqual(seen, ["a", "b"])
        self.assertIn("stopped early", str(ctx.exception))

    def test_a_complete_run_raises_nothing(self):
        with patch.object(reddit_apify, "collect", return_value=(["a"], {})):
            self.assertEqual(list(reddit_apify.fetch({"enabled": True})), ["a"])

    def test_the_stored_run_is_recorded_as_an_error_but_keeps_its_items(self):
        from unittest.mock import MagicMock
        fake_repo = MagicMock()
        item = SimpleNamespace(author="u", author_meta=SimpleNamespace(followers=None, verified=None,
                                                                       model_dump=lambda **k: {}),
                               source="reddit", source_type="post", external_id="t3_x", parent_id=None,
                               thread_id="t3_x", text="hello", lang=None, url="u", created_at=None,
                               engagement=SimpleNamespace(model_dump=lambda **k: {}), raw={})
        with patch.object(reddit_apify, "collect", return_value=([item], {"budget_stopped": "budget spent"})), \
             patch.object(extra_sources, "repo", fake_repo), \
             patch.object(extra_sources, "norm", lambda t: t):
            counters = extra_sources._run_source("reddit_apify", reddit_apify.fetch, {"enabled": True})
        self.assertEqual(fake_repo.insert_item_if_absent.call_count, 1)      # the item was stored
        self.assertIn("stopped early", counters["error"])
        self.assertIn("error", fake_repo.advance_state.call_args.kwargs)     # last_success_at is not advanced


class AccountUsageLookupTests(unittest.TestCase):
    def lookup(self, response=None, exc=None):
        with patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify.httpx, "get", side_effect=exc, return_value=response) as get:
            return reddit_apify.__dict__["_account_usage_real"](), get

    def test_it_reads_the_same_fields_the_doctor_check_shows(self):
        body = {"data": {"current": {"monthlyUsageUsd": 21.27}, "limits": {"maxMonthlyUsageUsd": 29}}}
        out, get = self.lookup(SimpleNamespace(status_code=200, json=lambda: body))
        self.assertEqual(out, (21.27, 29.0))
        self.assertTrue(get.call_args.args[0].endswith("/users/me/limits"))
        self.assertEqual(get.call_args.kwargs["headers"]["Authorization"], "Bearer tok")

    def test_anything_unreadable_is_none_never_an_exception(self):
        self.assertIsNone(self.lookup(SimpleNamespace(status_code=500, json=lambda: {}))[0])
        self.assertIsNone(self.lookup(exc=RuntimeError("dns"))[0])
        self.assertIsNone(self.lookup(SimpleNamespace(status_code=200, json=lambda: {"data": {}}))[0])
        body = {"data": {"current": {"monthlyUsageUsd": 5}, "limits": {}}}
        self.assertIsNone(self.lookup(SimpleNamespace(status_code=200, json=lambda: body))[0])


class RefreshHonoursTheGuardTests(unittest.TestCase):
    def test_the_engagement_refresh_does_not_run_when_the_account_is_past_the_line(self):
        from community.scrape import refresh
        reg = {"sources": {"reddit": {}, "reddit_apify": {"enabled": True, "actor": ACTOR}}}
        rows = [{"item_id": 1, "url": "https://www.reddit.com/r/a/comments/abc/x/", "engagement": None, "priority": 1}]
        with patch.object(refresh, "settings", SimpleNamespace(registry=reg)), \
             patch.object(refresh, "_candidates", return_value=rows), \
             patch.object(reddit_apify, "_account_usage", return_value=(27.0, 29.0)), \
             patch.object(reddit_apify, "_run_actor") as actor:
            out = refresh.run(daily=True)
        actor.assert_not_called()
        self.assertIn("monthly limit", out["note"])


class LiveUsageTests(unittest.TestCase):
    """The per-run `usageTotalUsd` can read $0.00 for a run that returned 119 results (2026-10-11), so the
    guard re-reads the account's real usage before every run and trusts whichever number is higher."""

    def live_collect(self, usages, *, local_cost=0.0, subs=MANY, reg_extra=None):
        fake, calls = costed_run(local_cost, rows=[POST])
        reddit_apify.run_costs_usd = 0.0
        seq = iter(usages)
        last = [usages[-1]]

        def usage():
            try:
                last[0] = next(seq)
            except StopIteration:
                pass
            return last[0]

        reg = {"enabled": True, "actor": ACTOR, "nightly_budget_usd": None, **(reg_extra or {})}
        with patch.object(reddit_apify, "_run_actor", side_effect=fake), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_account_usage", side_effect=usage), \
             patch.object(reddit_apify, "_subreddits", return_value=subs), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]):
            items, stats = reddit_apify.collect(reg)
        return calls, stats

    def test_it_stops_when_the_real_account_usage_crosses_the_line_even_if_runs_report_zero_cost(self):
        # runs "cost" nothing locally, but the account climbs 3.0 per run: 20 (start), 20, 23, 26 -> 90% -> stop
        calls, stats = self.live_collect([(20.0, 29.0), (20.0, 29.0), (23.0, 29.0), (26.0, 29.0)])
        self.assertEqual(len(calls), 2)
        self.assertIn("monthly limit", stats["budget_stopped"])
        self.assertAlmostEqual(stats["budget"]["spent_usd"], 6.0)          # the account's own delta

    def test_the_higher_of_the_local_and_the_live_figure_wins(self):
        # live says nothing moved, but the runs billed 2.5 each: the local count still protects the account
        calls, _ = self.live_collect([(20.0, 29.0)], local_cost=2.5)
        self.assertEqual(len(calls), 2)                                    # 22.5 -> 25.0 (>= 24.65) -> stop

    def test_an_account_lookup_that_fails_midway_falls_back_to_the_local_count(self):
        calls, _ = self.live_collect([(20.0, 29.0), None], local_cost=0.1, subs={"a": "x", "b": "x", "c": "x"})
        self.assertEqual(len(calls), 3)


class SilentSubredditTests(unittest.TestCase):
    """2026-10-11: 7 of 24 runs came back with zero rows and the log did not say which subreddits."""

    def test_watched_subreddits_with_no_posts_are_named_in_the_stats(self):
        fake, _ = costed_run(0.0, rows=[POST, COMMENT])
        _, stats = collect(fake, subs={"IndianStockMarket": "x", "Zerodha": "brokers"})
        self.assertEqual(stats["silent_subs"], ["Zerodha"])

    def test_and_in_the_log_so_cron_log_answers_which_ones(self):
        fake, _ = costed_run(0.0, rows=[POST, COMMENT])
        with self.assertLogs("beacon.scrape.reddit_apify", level="WARNING") as logs:
            collect(fake, subs={"IndianStockMarket": "x", "Zerodha": "brokers"})
        self.assertIn("Zerodha", " ".join(logs.output))

    def test_nothing_is_reported_when_every_subreddit_returned_posts(self):
        fake, _ = costed_run(0.0, rows=[POST, COMMENT])
        _, stats = collect(fake, subs={"IndianStockMarket": "x"})
        self.assertNotIn("silent_subs", stats)

    def test_a_run_log_entry_says_which_subreddits_it_covered(self):
        reddit_apify.run_costs_usd = 0.0
        del reddit_apify.run_log[:]

        def fake(actor, payload, **kw):
            reddit_apify.run_log.append({"run_id": "r", "status": "SUCCEEDED", "items": 0, "cost_usd": 0.0})
            return []

        with patch.object(reddit_apify, "_run_actor", side_effect=fake), \
             patch.object(reddit_apify, "_token", return_value="tok"), \
             patch.object(reddit_apify, "_subreddits", return_value={"Zerodha": "brokers"}), \
             patch.object(reddit_apify, "_active_keywords", return_value=[]):
            try:
                reddit_apify.collect({"enabled": True, "actor": ACTOR})
            except RuntimeError:
                pass
        self.assertEqual(reddit_apify.run_log[-1]["subs"], ["Zerodha"])


class StopMessageTests(unittest.TestCase):
    """The health digest shows `last_error[:120]`, and `_run_source` prefixes 'RuntimeError: ': the old wording
    ('... (Reddit stops at 85%: Instagram and LinkedIn share it)') was cut off before the part that says what to do."""

    def account_message(self, used, limit):
        b = reddit_apify.Budget({"nightly_budget_usd": None})
        b.used0, b.live_used, b.limit = used, used, limit
        return b.why_stop()

    def test_the_account_stop_says_what_to_do_and_fits_the_digest_line(self):
        for used, limit in ((24.7, 29.0), (62.0, 65.0), (95.0, 100.0)):
            msg = self.account_message(used, limit)
            shown = "RuntimeError: reddit apify stopped early: " + msg
            self.assertLessEqual(len(shown), 120, shown)
            self.assertIn("monthly limit", msg)
            self.assertIn("Billing", msg)              # where to raise it
            self.assertIn("Limits", msg)
        self.assertTrue(self.account_message(24.7, 29.0).startswith("account at 85%"))
