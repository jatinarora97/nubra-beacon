# tests/test_health_checks_jobs.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_jobs, config
from community.health.model import CRIT, OK, WARN
from community.health.state import Row


def ist(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)  # 2026-10-05 is a Monday


def row(job, status, start, finish=None, failed=(), error=None):
    return {"job": job, "status": status, "started_at": start, "finished_at": finish,
            "failed_stages": list(failed), "error": error}


def local(hour, status="ok", failed=()):
    return row("run-local", status, ist(5, hour), ist(5, hour, 8), failed)


def run_check(rows, now, epoch=ist(5, 0), cfg=None, lock_held=True):
    cfg = cfg or {**config.load({}), "_prev": {}}
    with patch.object(checks_jobs.ledger, "recent_runs", return_value=rows), \
         patch.object(checks_jobs.ledger, "pipeline_lock_held", return_value=lock_held), \
         patch.object(checks_jobs.state, "get_epoch", return_value=epoch):
        results = checks_jobs.check_jobs(cfg, now)
    return {r.key: r for r in results}


class OverdueTests(unittest.TestCase):
    def test_first_run_after_deploy_with_an_empty_ledger_raises_nothing(self):
        now = ist(5, 10, 30)
        res = run_check([], now, epoch=now)  # epoch == now: monitoring just began
        self.assertTrue(all(r.level == OK for r in res.values()), res)

    def test_three_missed_hourly_runs_is_critical(self):
        res = run_check([local(7), local(8)], ist(5, 11, 30))
        self.assertEqual(res["job_overdue:run-local"].level, CRIT)
        self.assertIn("3 scheduled run(s)", res["job_overdue:run-local"].detail)

    def test_one_missed_hourly_run_is_only_a_warning(self):
        res = run_check([local(7), local(8), local(9)], ist(5, 10, 30))
        self.assertEqual(res["job_overdue:run-local"].level, WARN)

    def test_healthy_hourly_runs_are_ok(self):
        res = run_check([local(h) for h in (7, 8, 9, 10, 11)], ist(5, 12, 10))
        self.assertEqual(res["job_overdue:run-local"].level, OK)

    def test_morning_build_that_never_started_is_critical(self):
        res = run_check([], ist(5, 7, 0))
        self.assertEqual(res["job_overdue:morning-build"].level, CRIT)


class SlowAndFailedTests(unittest.TestCase):
    def test_morning_build_still_running_after_90_minutes_is_critical(self):
        rows = [row("morning-build", "running", ist(5, 6))]
        self.assertEqual(run_check(rows, ist(5, 8, 0))["job_slow:morning-build"].level, CRIT)
        self.assertEqual(run_check(rows, ist(5, 7, 0))["job_slow:morning-build"].level, OK)

    def test_a_run_that_died_is_reported_as_died_not_as_still_running(self):
        rows = [row("morning-build", "running", ist(5, 6))]
        res = run_check(rows, ist(5, 8, 0), lock_held=False)["job_slow:morning-build"]
        self.assertEqual(res.level, CRIT)
        self.assertIn("died without finishing", res.detail)
        self.assertIn("next run clears this", res.hint)

    def test_a_hung_run_that_still_holds_the_lock_is_reported_as_still_running(self):
        rows = [row("morning-build", "running", ist(5, 6))]
        for held in (True, None):  # None = could not tell: assume it may be hung
            res = run_check(rows, ist(5, 8, 0), lock_held=held)["job_slow:morning-build"]
            self.assertIn("still running", res.detail)

    def test_stage_jobs_take_no_pipeline_lock_so_it_is_not_consulted(self):
        rows = [row("stage:compose", "running", ist(10, 10))]
        cfg = {**config.load({}), "_prev": {}}
        with patch.object(checks_jobs.ledger, "recent_runs", return_value=rows), \
             patch.object(checks_jobs.ledger, "pipeline_lock_held") as lock, \
             patch.object(checks_jobs.state, "get_epoch", return_value=ist(5, 0)):
            res = {r.key: r for r in checks_jobs.check_jobs(cfg, ist(10, 11, 30))}
        self.assertEqual(res["job_slow:stage:compose"].level, CRIT)
        self.assertIn("still running", res["job_slow:stage:compose"].detail)
        lock.assert_not_called()

    def test_two_crashed_runs_in_a_row_is_critical(self):
        rows = [local(8, "failed"), local(9, "failed")]
        rows[0]["error"] = rows[1]["error"] = "RuntimeError: boom"
        res = run_check(rows, ist(5, 9, 30))
        self.assertEqual(res["job_failed:run-local"].level, CRIT)
        self.assertIn("RuntimeError: boom", res["job_failed:run-local"].detail)

    def test_one_crash_between_successes_is_ok(self):
        rows = [local(8, "ok"), local(9, "failed")]
        self.assertEqual(run_check(rows, ist(5, 9, 30))["job_failed:run-local"].level, OK)


class StageFailingTests(unittest.TestCase):
    def test_stage_failing_in_each_of_the_last_three_runs_is_critical(self):
        rows = [local(8, "degraded", ["enrich"]),
                local(9, "degraded", ["enrich", "scrape"]),
                local(10, "degraded", ["enrich"])]
        res = run_check(rows, ist(5, 10, 30))
        self.assertEqual(res["stage_failing:enrich"].level, CRIT)
        self.assertNotIn("stage_failing:scrape", res)

    def test_a_clean_run_in_the_window_clears_it(self):
        rows = [local(8, "degraded", ["enrich"]), local(9, "ok"), local(10, "degraded", ["enrich"])]
        self.assertNotIn("stage_failing:enrich", run_check(rows, ist(5, 10, 30)))

    def test_fewer_than_three_runs_reports_nothing(self):
        rows = [local(9, "degraded", ["enrich"]), local(10, "degraded", ["enrich"])]
        self.assertNotIn("stage_failing:enrich", run_check(rows, ist(5, 10, 30)))


class DigestOnlyChecksTests(unittest.TestCase):
    def test_recent_stage_failures_are_warnings_with_counts(self):
        rows = [local(8, "degraded", ["enrich"]), local(9, "degraded", ["enrich"])]
        with patch.object(checks_jobs.ledger, "recent_runs", return_value=rows):
            results = checks_jobs.check_recent_stage_failures({}, ist(5, 10))
        self.assertEqual([(r.key, r.level) for r in results], [("stage_recent:enrich", WARN)])
        self.assertIn("2 failure(s)", results[0].detail)

    def test_heartbeat_missing_stale_and_fresh(self):
        now = ist(5, 12)
        missing = checks_jobs.check_watchdog_heartbeat({"_prev": {}}, now)[0]
        stale = checks_jobs.check_watchdog_heartbeat(
            {"_prev": {"watchdog_heartbeat": Row("watchdog_heartbeat", "ok", "", now, now - timedelta(hours=3))}}, now)[0]
        fresh = checks_jobs.check_watchdog_heartbeat(
            {"_prev": {"watchdog_heartbeat": Row("watchdog_heartbeat", "ok", "", now, now - timedelta(minutes=10))}}, now)[0]
        self.assertEqual((missing.level, stale.level, fresh.level), (WARN, WARN, OK))
