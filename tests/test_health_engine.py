# tests/test_health_engine.py
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import runner
from community.health import engine
from community.health.model import CRIT, OK, WARN, Result, owns
from community.health.state import Row

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CFG = engine.config.load({})


def crit_prev(key="fake:x", ok=0, alerted_h=1.0):
    return Row(key, CRIT, "old", NOW - timedelta(hours=3), NOW - timedelta(minutes=20),
               NOW - timedelta(hours=alerted_h), ok)


@owns("fake:")
def check_fake_crit(cfg, now):
    return [Result("fake:x", CRIT, "boom", "look here")]


@owns("fake:")
def check_fake_ok(cfg, now):
    return [Result("fake:x", OK, "fine")]


@owns("fake:")
def check_fake_crashes(cfg, now):
    raise RuntimeError("kaput")


@owns("other:")
def check_other_warn(cfg, now):
    return [Result("other:y", WARN, "meh")]


class RunChecksTests(unittest.TestCase):
    def test_a_crashing_check_becomes_a_warning_and_the_rest_still_run(self):
        results, failed = engine.run_checks([check_fake_crashes, check_other_warn], CFG, NOW)
        keys = {r.key: r for r in results}
        self.assertEqual(keys["check_error:check_fake_crashes"].level, WARN)
        self.assertIn("kaput", keys["check_error:check_fake_crashes"].detail)
        self.assertIn("other:y", keys)
        self.assertEqual(failed, ["fake:"])


class BuildPlanTests(unittest.TestCase):
    def plan(self, results, prev=None, failed=()):
        return engine.build_plan(results, prev or {}, list(failed), CFG, NOW)

    def test_new_critical_produces_an_alert_line(self):
        plan = self.plan([Result("fake:x", CRIT, "boom", "look here")])
        self.assertEqual([d.action for d in plan.decisions], ["alert"])
        self.assertTrue(plan.message.startswith("[CRITICAL] fake:x: boom"))

    def test_warnings_never_produce_a_message(self):
        self.assertEqual(self.plan([Result("other:y", WARN, "meh")]).message, "")

    def test_a_vanished_critical_resolves_after_two_clean_evaluations(self):
        self.assertEqual(self.plan([], {"fake:x": crit_prev(ok=0)}).message, "")  # first clean pass
        plan = self.plan([], {"fake:x": crit_prev(ok=1)})                          # second
        self.assertIn("[RESOLVED] fake:x", plan.message)

    def test_a_check_that_crashed_does_not_resolve_its_open_critical(self):
        plan = self.plan([], {"fake:x": crit_prev(ok=1)}, failed=["fake:"])
        self.assertEqual(plan.decisions, [])
        self.assertEqual(plan.message, "")

    def test_alerts_are_listed_before_resolves(self):
        plan = self.plan([Result("fake:new", CRIT, "bad")], {"fake:old": crit_prev("fake:old", ok=1)})
        lines = plan.message.splitlines()
        self.assertTrue(lines[0].startswith("[CRITICAL] fake:new"))
        self.assertTrue(lines[-1].startswith("[RESOLVED] fake:old"))


class WatchdogRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.flag = pathlib.Path(tmp.name) / ".watchdog_db_down"
        self.saved: list[Row] = []
        for p in (patch.object(engine, "DB_DOWN_FLAG", self.flag),
                  patch.object(engine, "_db_up", return_value=True),
                  patch.object(engine.resources, "collect_and_record", return_value={}),
                  patch.object(engine.state, "load_states", return_value={}),
                  patch.object(engine.state, "save", side_effect=self.saved.append)):
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, checks, post="sent", **kw):
        with patch.object(engine, "CRITICAL_CHECKS", checks), \
             patch.object(engine.notify, "post", return_value=post) as post_mock:
            summary = engine.run_watchdog(now=NOW, **kw)
        return summary, post_mock

    def saved_keys(self):
        return [r.key for r in self.saved]

    def test_new_critical_is_posted_and_its_state_saved(self):
        summary, post = self.run_with([check_fake_crit])
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].startswith("[CRITICAL] fake:x"))
        self.assertEqual(summary["posted"], "sent")
        self.assertEqual(summary["critical"], ["fake:x"])
        self.assertEqual(summary["actions"], {"fake:x": "alert"})
        self.assertIn("fake:x", self.saved_keys())
        self.assertIn("watchdog_heartbeat", self.saved_keys())

    def test_a_failed_slack_post_leaves_the_alert_unsaved_so_it_retries(self):
        summary, _ = self.run_with([check_fake_crit], post="error: HTTPStatusError: 500")
        self.assertTrue(summary["posted"].startswith("error"))
        self.assertNotIn("fake:x", self.saved_keys())
        self.assertIn("watchdog_heartbeat", self.saved_keys())

    def test_nothing_to_report_posts_nothing(self):
        summary, post = self.run_with([check_fake_ok])
        post.assert_not_called()
        self.assertIsNone(summary["posted"])
        self.assertIn("fake:x", self.saved_keys())

    def test_a_crashed_check_does_not_resolve_an_open_critical(self):
        engine.state.load_states.return_value = {"fake:x": crit_prev(ok=1)}
        summary, post = self.run_with([check_fake_crashes])
        post.assert_not_called()
        self.assertNotIn("fake:x", self.saved_keys())

    def test_a_failing_resource_sample_insert_must_not_stop_critical_alerts(self):
        # exactly when the DB is struggling (statement timeout on the insert) alerts matter most
        engine.resources.collect_and_record.side_effect = RuntimeError("canceling statement due to statement timeout")
        summary, post = self.run_with([check_fake_crit])
        post.assert_called_once()
        self.assertEqual(summary["posted"], "sent")
        self.assertIn("fake:x", self.saved_keys())

    def test_dry_run_writes_and_posts_nothing(self):
        with patch.object(engine, "CRITICAL_CHECKS", [check_fake_crit]):
            summary = engine.run_watchdog(dry_run=True, now=NOW)
        self.assertEqual(summary["posted"], "dry-run")
        self.assertEqual(self.saved, [])
        engine.resources.collect_and_record.assert_not_called()

    def test_test_message_posts_without_touching_the_database(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_watchdog(test_message=True, now=NOW)
        self.assertEqual(summary, {"test_message": "sent"})
        self.assertTrue(post.call_args.args[0].startswith("[TEST]"))
        engine._db_up.assert_not_called()

    def test_database_down_posts_once_then_stays_quiet_inside_the_reminder_window(self):
        engine._db_up.return_value = False
        with patch.object(engine.notify, "post", return_value="sent") as post:
            first = engine.run_watchdog(now=NOW)
            second = engine.run_watchdog(now=NOW)
            old = time.time() - 7 * 3600
            os.utime(self.flag, (old, old))
            third = engine.run_watchdog(now=NOW)
        self.assertTrue(first["db_unreachable"])
        self.assertEqual(post.call_count, 2)  # first + after the 6 h reminder window
        self.assertIsNone(second["posted"])
        self.assertEqual(third["posted"], "sent")
        self.assertIn("[CRITICAL] db_unreachable", post.call_args_list[0].args[0])

    def test_database_back_up_posts_resolved_and_clears_the_flag(self):
        self.flag.touch()
        summary, post = self.run_with([check_fake_ok])
        self.assertTrue(summary["db_recovered"])
        self.assertIn("[RESOLVED] db_unreachable", post.call_args_list[0].args[0])
        self.assertFalse(self.flag.exists())


class WatchdogCommandTests(unittest.TestCase):
    def call(self, summary, **kw):
        with patch("community.health.engine.run_watchdog", return_value=summary), \
             patch.object(runner.typer, "echo") as echo:
            runner.watchdog(**{"dry_run": False, "test_message": False, "verbose": False, **kw})
        return echo

    def test_silent_when_nothing_happened(self):
        self.call({"posted": None, "actions": {}}).assert_not_called()

    def test_prints_when_something_was_posted_or_verbose(self):
        self.call({"posted": "sent", "actions": {"a": "alert"}}).assert_called_once()
        self.call({"posted": None, "actions": {}}, verbose=True).assert_called_once()

    def test_unexpected_exception_exits_one(self):
        with patch("community.health.engine.run_watchdog", side_effect=RuntimeError("x")):
            with self.assertRaises(SystemExit) as ctx:
                runner.watchdog(dry_run=False, test_message=False, verbose=False)
        self.assertEqual(ctx.exception.code, 1)
