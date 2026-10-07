# tests/test_health_ledger.py
from __future__ import annotations

import unittest
from unittest.mock import patch

from community.health import ledger


class SummarizeTests(unittest.TestCase):
    def test_all_stages_ok(self):
        self.assertEqual(ledger.summarize({"scrape": {"inserted": 3}, "clean": {}}), ("ok", []))

    def test_failed_stage_degrades_the_run(self):
        status, failed = ledger.summarize({"scrape": {}, "enrich": {"error": "boom"}})
        self.assertEqual(status, "degraded")
        self.assertEqual(failed, ["enrich"])

    def test_non_dict_result_is_ok(self):
        self.assertEqual(ledger.summarize(None), ("ok", []))


class LedgerNeverRaisesTests(unittest.TestCase):
    def test_start_job_returns_none_when_db_is_down(self):
        with patch("community.store.db.one", side_effect=RuntimeError("db down")):
            self.assertIsNone(ledger.start_job("run-local"))

    def test_finish_job_swallows_db_errors(self):
        with patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            ledger.finish_job(5, "ok", seconds=1.2)  # must not raise

    def test_finish_job_with_no_id_is_a_noop(self):
        with patch("community.store.db.execute") as ex:
            ledger.finish_job(None, "ok")
        ex.assert_not_called()

    def test_record_skipped_swallows_db_errors(self):
        with patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            ledger.record_skipped("run-local")  # must not raise


class LedgerWritesTests(unittest.TestCase):
    def test_start_job_inserts_a_running_row(self):
        with patch("community.store.db.one", return_value={"id": 42}) as one:
            self.assertEqual(ledger.start_job("morning-build"), 42)
        sql, params = one.call_args[0]
        self.assertIn("INSERT INTO job_runs", sql)
        self.assertEqual(params, ("morning-build",))

    def test_finish_job_updates_status_and_failed_stages(self):
        with patch("community.store.db.execute") as ex:
            ledger.finish_job(7, "degraded", failed_stages=["enrich"], seconds=3.14)
        sql, params = ex.call_args[0]
        self.assertIn("UPDATE job_runs", sql)
        self.assertEqual(params[0], "degraded")
        self.assertEqual(params[1], ["enrich"])
        self.assertEqual(params[-1], 7)


class ReapAndLockTests(unittest.TestCase):
    def test_reap_pipeline_runs_fails_running_rows_but_leaves_stage_jobs_alone(self):
        with patch("community.store.db.execute", return_value=2) as ex:
            self.assertEqual(ledger.reap_pipeline_runs(), 2)
        sql = ex.call_args[0][0]
        self.assertIn("UPDATE job_runs", sql)
        self.assertIn("status = 'running'", sql)
        self.assertIn("NOT LIKE 'stage:%'", sql)
        self.assertIn("abandoned", sql)

    def test_reap_stale_stage_only_touches_that_stage_and_old_rows(self):
        with patch("community.store.db.execute", return_value=1) as ex:
            self.assertEqual(ledger.reap_stale_stage("stage:compose", 60), 1)
        sql, params = ex.call_args[0]
        self.assertIn("job = %s", sql)
        self.assertEqual(params, ("stage:compose", 60))

    def test_reapers_swallow_db_errors(self):
        with patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            self.assertEqual(ledger.reap_pipeline_runs(), 0)
            self.assertEqual(ledger.reap_stale_stage("stage:compose"), 0)

    def test_pipeline_lock_held_reads_pg_locks(self):
        with patch("community.store.db.one", return_value={"held": True}) as one:
            self.assertIs(ledger.pipeline_lock_held(), True)
        self.assertEqual(one.call_args[0][1], (0x6E756272,))
        with patch("community.store.db.one", return_value={"held": False}):
            self.assertIs(ledger.pipeline_lock_held(), False)

    def test_pipeline_lock_held_is_unknown_when_the_db_errors(self):
        with patch("community.store.db.one", side_effect=RuntimeError("db down")):
            self.assertIsNone(ledger.pipeline_lock_held())

    def test_lock_key_matches_the_runner(self):
        import runner
        self.assertEqual(ledger._PIPELINE_LOCK_KEY, runner._PIPELINE_LOCK_KEY)
