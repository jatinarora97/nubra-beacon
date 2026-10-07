# tests/test_health_runner.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import typer

import runner


class WithPipelineLockLedgerTests(unittest.TestCase):
    def test_lock_busy_records_a_skip_and_exits_zero(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=None), \
             patch("community.health.ledger.record_skipped") as skipped, \
             patch("community.health.ledger.start_job") as start:
            with self.assertRaises(typer.Exit) as ctx:
                runner._with_pipeline_lock("run-local", lambda: {"scrape": {}})
        self.assertEqual(ctx.exception.exit_code, 0)
        skipped.assert_called_once_with("run-local")
        start.assert_not_called()

    def test_clean_run_is_recorded_ok_and_lock_released(self):
        lock = MagicMock()
        with patch.object(runner, "_acquire_pipeline_lock", return_value=lock), \
             patch("community.health.ledger.start_job", return_value=7) as start, \
             patch("community.health.ledger.finish_job") as finish:
            runner._with_pipeline_lock("morning-build", lambda: {"scrape": {"inserted": 3}})
        start.assert_called_once_with("morning-build")
        self.assertEqual(finish.call_args.args, (7, "ok"))
        lock.close.assert_called_once()

    def test_failed_stage_marks_the_run_degraded(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.health.ledger.start_job", return_value=8), \
             patch("community.health.ledger.finish_job") as finish:
            runner._with_pipeline_lock("run-local", lambda: {"enrich": {"error": "x"}})
        self.assertEqual(finish.call_args.args, (8, "degraded"))
        self.assertEqual(finish.call_args.kwargs["failed_stages"], ["enrich"])

    def test_exception_is_recorded_failed_and_still_raised(self):
        lock = MagicMock()

        def boom():
            raise RuntimeError("pipeline exploded")

        with patch.object(runner, "_acquire_pipeline_lock", return_value=lock), \
             patch("community.health.ledger.start_job", return_value=9), \
             patch("community.health.ledger.finish_job") as finish:
            with self.assertRaises(RuntimeError):
                runner._with_pipeline_lock("run-local", boom)
        self.assertEqual(finish.call_args.args, (9, "failed"))
        self.assertIn("RuntimeError", finish.call_args.kwargs["error"])
        lock.close.assert_called_once()

    def test_explicit_job_name_overrides_the_label(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.health.ledger.start_job", return_value=1) as start, \
             patch("community.health.ledger.finish_job"):
            runner._with_pipeline_lock("source-instagram", lambda: {}, job="source:instagram")
        start.assert_called_once_with("source:instagram")

    def test_a_broken_ledger_never_breaks_a_run(self):
        ran = []
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.store.db.one", side_effect=RuntimeError("db down")), \
             patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            runner._with_pipeline_lock("run-local", lambda: ran.append(1) or {})
        self.assertEqual(ran, [1])


class AbandonedRunReapingTests(unittest.TestCase):
    def test_dead_runs_are_reaped_after_the_lock_is_won_and_before_the_new_run_starts(self):
        calls = []
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()),              patch("community.health.ledger.reap_pipeline_runs", side_effect=lambda: calls.append("reap")),              patch("community.health.ledger.start_job", side_effect=lambda j: calls.append("start") or 1),              patch("community.health.ledger.finish_job"):
            runner._with_pipeline_lock("run-local", lambda: {})
        self.assertEqual(calls, ["reap", "start"])

    def test_nothing_is_reaped_when_another_run_holds_the_lock(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=None),              patch("community.health.ledger.reap_pipeline_runs") as reap,              patch("community.health.ledger.record_skipped"):
            with self.assertRaises(typer.Exit):
                runner._with_pipeline_lock("run-local", lambda: {})
        reap.assert_not_called()

    def test_stage_command_reaps_only_its_own_stale_rows(self):
        with patch.object(runner, "_run_stage", return_value={}),              patch("community.health.ledger.reap_stale_stage") as reap,              patch("community.health.ledger.start_job", return_value=1),              patch("community.health.ledger.finish_job"):
            runner.stage("compose")
        reap.assert_called_once_with("stage:compose")


class StageAndSourceCommandTests(unittest.TestCase):
    def test_stage_success_is_recorded(self):
        with patch.object(runner, "_run_stage", return_value={}), \
             patch("community.health.ledger.start_job", return_value=3) as start, \
             patch("community.health.ledger.finish_job") as finish:
            runner.stage("compose")
        start.assert_called_once_with("stage:compose")
        self.assertEqual(finish.call_args.args, (3, "ok"))

    def test_stage_failure_is_recorded_and_exits_1(self):
        with patch.object(runner, "_run_stage", side_effect=RuntimeError("bad")), \
             patch("community.health.ledger.start_job", return_value=4), \
             patch("community.health.ledger.finish_job") as finish:
            with self.assertRaises(SystemExit) as ctx:
                runner.stage("dispatch")
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(finish.call_args.args, (4, "failed"))

    def test_source_command_passes_a_source_job_name_and_returns_stats(self):
        captured = {}

        def fake_lock(label, fn, job=None):
            captured["label"], captured["job"], captured["result"] = label, job, fn()

        with patch.object(runner, "_with_pipeline_lock", side_effect=fake_lock), \
             patch("community.scrape.extra_sources.run",
                   return_value={"instagram": {"inserted": 2}}):
            runner.source("instagram")
        self.assertEqual(captured["job"], "source:instagram")
        self.assertEqual(captured["result"], {"instagram": {"inserted": 2}})
