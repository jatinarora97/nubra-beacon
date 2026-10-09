# tests/test_health_resources.py
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from community.health import resources
from community.health.model import CRIT, OK, WARN

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
R = {
    "disk_warn_pct": 80, "disk_crit_pct": 90, "disk_eta_warn_days": 21, "disk_eta_crit_days": 7,
    "mem_warn_pct": 20, "mem_crit_pct": 10, "mem_crit_samples": 3,
    "load_warn_per_core": 2.0, "cron_log_warn_mb": 500,
    "swap_active_warn_pct": 50, "swap_idle_warn_pct": 75, "swap_crit_pct": 90,
    "swap_active_pages_per_min": 1000,
    "backup_warn_hours": 26, "backup_crit_hours": 36, "restart_crit_count": 2,
}


def free_series(start_gb, drop_per_day, days=3, step_h=1):
    n = int(days * 24 / step_h) + 1
    t0 = NOW - timedelta(days=days)
    return [(t0 + timedelta(hours=i * step_h), start_gb - drop_per_day * i * step_h / 24)
            for i in range(n)]


class ParseTests(unittest.TestCase):
    def test_meminfo_percentages(self):
        text = ("MemTotal:       16000000 kB\nMemFree:         1000 kB\n"
                "MemAvailable:    4000000 kB\nSwapTotal:       2000000 kB\n"
                "SwapFree:        1500000 kB\n")
        out = resources.parse_meminfo(text)
        self.assertAlmostEqual(out["mem_available_pct"], 25.0)
        self.assertAlmostEqual(out["swap_used_pct"], 25.0)

    def test_meminfo_without_swap_omits_the_swap_metric(self):
        out = resources.parse_meminfo("MemTotal: 100 kB\nMemAvailable: 50 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        self.assertNotIn("swap_used_pct", out)

    def test_process_start_epoch_from_proc_stat(self):
        line = "1 (cm run) S 0 1 1 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 5000 12345 678"
        self.assertEqual(resources.parse_proc_start_epoch(line, 1_700_000_000.0, 100),
                         1_700_000_050.0)

    def test_process_name_with_parentheses_does_not_break_parsing(self):
        line = "1 (a) b) S 0 1 1 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 5000 12345 678"
        self.assertEqual(resources.parse_proc_start_epoch(line, 0.0, 100), 50.0)

    def test_garbage_returns_none(self):
        self.assertIsNone(resources.parse_proc_start_epoch("nonsense", 0.0, 100))


class CollectHostTests(unittest.TestCase):
    def test_reads_proc_files_and_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            proc, out = base / "proc", base / "out"
            (proc / "1").mkdir(parents=True)
            out.mkdir()
            (proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n")
            (proc / "vmstat").write_text("pgfault 7\npswpin 10\npswpout 32\n")
            (proc / "loadavg").write_text("0.50 0.40 0.30 1/200 999\n")
            (proc / "stat").write_text("cpu 1 2 3\nbtime 1700000000\n")
            (proc / "1" / "stat").write_text("1 (cm) S 0 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 5000 0 0")
            (out / "cron.log").write_bytes(b"x" * 2_000_000)
            (out / ".backup_ok").write_text("")
            m = resources.collect_host(out_dir=out, proc=str(proc))
        self.assertAlmostEqual(m["mem_available_pct"], 25.0)
        self.assertAlmostEqual(m["load_per_core"], 0.5 / (os.cpu_count() or 1))
        self.assertAlmostEqual(m["cron_log_mb"], 2.0)
        self.assertEqual(m["swap_io_pages"], 42.0)
        self.assertLess(m["backup_age_h"], 0.1)
        if hasattr(os, "sysconf"):
            self.assertIn("api_start_epoch", m)
        if hasattr(os, "statvfs"):
            self.assertIn("disk_used_pct", m)

    def test_missing_proc_and_files_are_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = resources.collect_host(out_dir=pathlib.Path(tmp) / "nope",
                                       proc=str(pathlib.Path(tmp) / "noproc"))
        self.assertNotIn("mem_available_pct", m)
        self.assertNotIn("cron_log_mb", m)
        self.assertNotIn("backup_age_h", m)


class EtaTests(unittest.TestCase):
    def test_linear_fill_rate_gives_days_left(self):
        self.assertAlmostEqual(resources.eta_days(free_series(100, 20)), 2.0, places=1)

    def test_flat_or_growing_free_space_has_no_eta(self):
        self.assertIsNone(resources.eta_days(free_series(100, 0)))
        self.assertIsNone(resources.eta_days(free_series(100, -5)))

    def test_not_enough_history_has_no_eta(self):
        self.assertIsNone(resources.eta_days(free_series(100, 20, days=0.5)))
        self.assertIsNone(resources.eta_days(free_series(100, 20)[:5]))


class EvaluatorTests(unittest.TestCase):
    def test_disk_levels_from_percentage(self):
        flat = free_series(100, 0)
        self.assertEqual(resources.eval_disk(R, 95, flat).level, CRIT)
        self.assertEqual(resources.eval_disk(R, 85, flat).level, WARN)
        self.assertEqual(resources.eval_disk(R, 50, flat).level, OK)

    def test_disk_levels_from_eta(self):
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 20)).level, CRIT)  # ~2 d
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 5)).level, WARN)   # ~17 d
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 2)).level, OK)     # ~47 d

    def test_memory_needs_sustained_low_samples_to_go_critical(self):
        self.assertEqual(resources.eval_memory(R, [30, 5, 5, 5]).level, CRIT)
        self.assertEqual(resources.eval_memory(R, [30, 5, 5]).level, WARN)  # only 2 low samples
        self.assertEqual(resources.eval_memory(R, [15]).level, WARN)
        self.assertEqual(resources.eval_memory(R, [50]).level, OK)

    def test_load_and_cron_log_warn_only(self):
        self.assertEqual(resources.eval_load(R, [3, 3, 3]).level, WARN)
        self.assertEqual(resources.eval_load(R, [3, 1, 3]).level, OK)
        self.assertEqual(resources.eval_cron_log(R, 600).level, WARN)
        self.assertEqual(resources.eval_cron_log(R, 10).level, OK)

    def test_single_restart_is_a_warning_two_in_an_hour_is_critical(self):
        one = [(NOW - timedelta(hours=3), 1000.0), (NOW - timedelta(hours=2), 1000.0),
               (NOW - timedelta(hours=1), 2000.0)]
        res = resources.eval_restarts("api", one, NOW, R)
        self.assertEqual((res.key, res.level), ("restart:api", WARN))
        loop = [(NOW - timedelta(minutes=50), 1.0), (NOW - timedelta(minutes=40), 100.0),
                (NOW - timedelta(minutes=30), 200.0)]
        self.assertEqual(resources.eval_restarts("api", loop, NOW, R).level, CRIT)

    def test_no_restart_and_clock_jitter_are_ok(self):
        steady = [(NOW - timedelta(hours=2), 1000.0), (NOW - timedelta(hours=1), 1002.0)]
        self.assertEqual(resources.eval_restarts("postgres", steady, NOW, R).level, OK)

    def test_backup_heartbeat(self):
        self.assertEqual(resources.eval_backup(None, R).level, WARN)  # file not created yet
        self.assertEqual(resources.eval_backup(5.0, R).level, OK)
        self.assertEqual(resources.eval_backup(25.0, R).level, OK)    # nightly backup: up to ~24 h old is normal
        self.assertEqual(resources.eval_backup(27.0, R).level, WARN)  # one night missed
        self.assertEqual(resources.eval_backup(37.0, R).level, CRIT)  # two nights missed


class SwapTests(unittest.TestCase):
    """Swap percentage alone misleads: Linux parks cold pages in swap and a box can sit at
    69% forever without swapping. Judge it together with swap-in/out activity."""

    def test_vmstat_swap_counters_are_summed(self):
        text = "nr_free_pages 100\npswpin 40\npswpout 60\npgfault 9\n"
        self.assertEqual(resources.parse_vmstat_swap(text), 100.0)
        self.assertIsNone(resources.parse_vmstat_swap("nr_free_pages 100\n"))

    def test_rate_is_pages_per_minute_between_the_first_and_last_sample(self):
        hist = [(NOW - timedelta(minutes=40), 1000.0), (NOW - timedelta(minutes=20), 3000.0),
                (NOW, 5000.0)]
        self.assertAlmostEqual(resources.swap_rate_pages_per_min(hist), 100.0)

    def test_rate_is_unknown_without_enough_history_or_after_a_counter_reset(self):
        self.assertIsNone(resources.swap_rate_pages_per_min([(NOW, 5.0)]))
        self.assertIsNone(resources.swap_rate_pages_per_min(
            [(NOW - timedelta(minutes=3), 1.0), (NOW, 9.0)]))            # under 10 minutes
        self.assertIsNone(resources.swap_rate_pages_per_min(
            [(NOW - timedelta(minutes=30), 9000.0), (NOW, 10.0)]))       # a reboot reset the counter

    def test_high_but_idle_swap_is_not_alarming_in_the_middle_range(self):
        res = resources.eval_swap(R, 69.0, rate=0.0)
        self.assertEqual(res.level, OK)
        self.assertIn("no swapping activity", res.detail)

    def test_swap_in_the_middle_range_warns_only_when_pages_are_moving(self):
        self.assertEqual(resources.eval_swap(R, 69.0, rate=5000.0).level, WARN)
        self.assertEqual(resources.eval_swap(R, 40.0, rate=5000.0).level, OK)

    def test_swap_over_75_percent_warns_even_when_idle(self):
        self.assertEqual(resources.eval_swap(R, 80.0, rate=0.0).level, WARN)
        self.assertEqual(resources.eval_swap(R, 80.0, rate=None).level, WARN)

    def test_swap_over_90_percent_is_critical_only_while_actively_swapping(self):
        self.assertEqual(resources.eval_swap(R, 95.0, rate=5000.0).level, CRIT)
        self.assertEqual(resources.eval_swap(R, 95.0, rate=0.0).level, WARN)
        self.assertEqual(resources.eval_swap(R, 95.0, rate=None).level, WARN)


class CheckResourcesTests(unittest.TestCase):
    def test_emits_one_result_per_metric_family(self):
        data = {
            "disk_used_pct": [(NOW, 40.0)], "disk_free_gb": free_series(100, 0),
            "mem_available_pct": [(NOW, 60.0)], "load_per_core": [(NOW, 0.2)],
            "swap_used_pct": [(NOW, 1.0)], "swap_io_pages": [], "cron_log_mb": [(NOW, 3.0)],
            "api_start_epoch": [(NOW - timedelta(hours=2), 1.0), (NOW, 1.0)],
            "pg_start_epoch": [(NOW - timedelta(hours=2), 1.0), (NOW, 1.0)],
            "backup_age_h": [(NOW, 3.0)],
        }
        with patch.object(resources, "history", side_effect=lambda m, h: data.get(m, [])):
            results = resources.check_resources({"resources": R}, NOW)
        keys = {r.key for r in results}
        self.assertEqual(keys, {"disk", "memory", "load", "swap", "cron_log",
                                "restart:api", "restart:postgres", "backup"})
        self.assertTrue(all(r.level == OK for r in results))

    def test_no_samples_at_all_only_flags_the_missing_backup_heartbeat(self):
        with patch.object(resources, "history", return_value=[]):
            results = resources.check_resources({"resources": R}, NOW)
        self.assertEqual([(r.key, r.level) for r in results], [("backup", WARN)])


class SampleIoTests(unittest.TestCase):
    def test_record_samples_inserts_one_row_per_metric(self):
        with patch("community.store.db.executemany") as many:
            resources.record_samples({"a": 1.0, "b": 2.0})
        sql, rows = many.call_args[0]
        self.assertIn("INSERT INTO resource_samples", sql)
        self.assertEqual(sorted(rows), [("a", 1.0), ("b", 2.0)])

    def test_history_returns_ts_value_pairs(self):
        with patch("community.store.db.query", return_value=[{"ts": NOW, "value": 3.5}]):
            self.assertEqual(resources.history("disk_used_pct", 2), [(NOW, 3.5)])
