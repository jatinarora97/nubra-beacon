# tests/test_health_schedule.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from community.config.log import IST
from community.health import schedule
from community.health.schedule import Run, slots_between, trailing_missed


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)  # 2026-10-05 is a Monday


RUN_LOCAL = {"hours": [0] + list(range(7, 24)), "minute": 0,
             "start_window_min": 10, "grace_min": 15}
MORNING = {"hours": [6], "minute": 0, "start_window_min": 10, "grace_min": 20}
WEEKLY = {"hours": [10], "minute": 0, "weekdays": [5],
          "start_window_min": 10, "grace_min": 15}


def local_runs(*hours, status="ok"):
    return [Run("run-local", status, ist(5, h), ist(5, h, 10)) for h in hours]


class SlotsTests(unittest.TestCase):
    def test_hourly_slots_for_one_day(self):
        slots = slots_between(RUN_LOCAL, ist(5, 0), ist(5, 23, 59))
        self.assertEqual([s.hour for s in slots], [0] + list(range(7, 24)))

    def test_weekday_filter_only_returns_saturday(self):
        slots = slots_between(WEEKLY, ist(5, 0), ist(11, 23))
        self.assertEqual(slots, [ist(10, 10)])  # Saturday 10 Oct

    def test_bounds_are_inclusive(self):
        self.assertEqual(slots_between(MORNING, ist(5, 6), ist(5, 6)), [ist(5, 6)])


class TrailingMissedTests(unittest.TestCase):
    def missed(self, runs, now, cfg=RUN_LOCAL, job="run-local", epoch=None, **kw):
        return trailing_missed(job, cfg, runs, now, epoch=epoch or ist(5, 0), **kw)

    def test_healthy_hourly_run_has_no_misses(self):
        self.assertEqual(self.missed(local_runs(7, 8, 9, 10, 11), ist(5, 12, 10)), [])

    def test_three_trailing_misses_are_reported(self):
        missed = self.missed(local_runs(7, 8), ist(5, 11, 30))
        self.assertEqual(missed, [ist(5, 9), ist(5, 10), ist(5, 11)])

    def test_a_later_run_resets_the_streak(self):
        self.assertEqual(self.missed(local_runs(7, 8, 10, 11), ist(5, 12, 10)), [])

    def test_a_run_at_the_next_slot_does_not_satisfy_the_previous_slot(self):
        runs = local_runs(10)
        window = timedelta(minutes=10)
        self.assertFalse(schedule._own_run_started(runs, "run-local", ist(5, 9), window))
        self.assertTrue(schedule._own_run_started(runs, "run-local", ist(5, 10), window))

    def test_slot_still_inside_its_grace_window_is_not_due(self):
        self.assertEqual(self.missed(local_runs(7, 8), ist(5, 9, 10)), [])

    def test_slots_before_the_epoch_are_ignored(self):
        self.assertEqual(self.missed([], ist(5, 12, 10), epoch=ist(5, 12)), [])

    def test_a_running_or_failed_run_still_counts_as_the_job_having_run(self):
        running = [Run("run-local", "running", ist(5, 7), None)]
        failed = [Run("run-local", "failed", ist(5, 7), ist(5, 7, 5))]
        self.assertEqual(self.missed(running, ist(5, 8, 10), epoch=ist(5, 7)), [])
        self.assertEqual(self.missed(failed, ist(5, 8, 10), epoch=ist(5, 7)), [])

    def test_hourly_slot_behind_the_morning_build_is_excused(self):
        # morning-build 06:00-07:25 holds the lock at 07:00, so 07:00 is excused
        # (slot 00:00 has no run and no holder: that earlier miss is reset by 07:00)
        runs = [Run("morning-build", "ok", ist(5, 6), ist(5, 7, 25))]
        self.assertEqual(self.missed(runs, ist(5, 8, 10)), [])

    def test_lock_busy_skip_alone_does_not_excuse_a_slot(self):
        runs = [Run("run-local", "skipped_locked", ist(5, 7), ist(5, 7))]
        self.assertEqual(self.missed(runs, ist(5, 8, 10), epoch=ist(5, 7)), [ist(5, 7)])

    def test_a_holder_stuck_for_hours_does_not_excuse_the_slot(self):
        runs = [Run("morning-build", "running", ist(5, 1), None)]  # 6 h old at 07:00
        missed = self.missed(runs, ist(5, 8, 10))
        self.assertIn(ist(5, 7), missed)

    def test_weekly_job_missed_on_saturday_only(self):
        self.assertEqual(self.missed([], ist(10, 11), cfg=WEEKLY, job="stage:compose"),
                         [ist(10, 10)])
        self.assertEqual(self.missed([], ist(9, 11), cfg=WEEKLY, job="stage:compose"), [])

    def test_morning_build_missed(self):
        self.assertEqual(self.missed([], ist(5, 8), cfg=MORNING, job="morning-build"),
                         [ist(5, 6)])
