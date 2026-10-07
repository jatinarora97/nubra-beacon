# tests/test_health_state.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from community.health import state
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Row, decide

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def row(level, *, since_h=1.0, alerted_h=None, ok=0, detail="d"):
    return Row("k", level, detail, NOW - timedelta(hours=since_h), NOW - timedelta(minutes=20),
               None if alerted_h is None else NOW - timedelta(hours=alerted_h), ok)


class DecideTests(unittest.TestCase):
    def test_new_critical_alerts(self):
        d = decide(None, Result("k", CRIT, "bad"), NOW)
        self.assertEqual(d.action, "alert")
        self.assertEqual((d.row.level, d.row.since, d.row.last_alerted_at), (CRIT, NOW, NOW))

    def test_critical_after_ok_or_warn_alerts(self):
        self.assertEqual(decide(row(OK), Result("k", CRIT, "x"), NOW).action, "alert")
        self.assertEqual(decide(row(WARN), Result("k", CRIT, "x"), NOW).action, "alert")

    def test_warn_and_ok_never_alert(self):
        self.assertEqual(decide(None, Result("k", WARN, "x"), NOW).action, "none")
        self.assertEqual(decide(row(OK), Result("k", WARN, "x"), NOW).action, "none")
        self.assertEqual(decide(row(WARN), Result("k", OK, "x"), NOW).action, "none")

    def test_warn_keeps_its_original_since(self):
        d = decide(row(WARN, since_h=30), Result("k", WARN, "still"), NOW)
        self.assertEqual(d.row.since, NOW - timedelta(hours=30))

    def test_level_change_resets_since(self):
        self.assertEqual(decide(row(OK, since_h=30), Result("k", WARN, "x"), NOW).row.since, NOW)

    def test_critical_inside_the_reminder_window_stays_quiet(self):
        prev = row(CRIT, alerted_h=2)
        d = decide(prev, Result("k", CRIT, "new detail"), NOW)
        self.assertEqual(d.action, "none")
        self.assertEqual(d.row.last_alerted_at, prev.last_alerted_at)
        self.assertEqual(d.row.detail, "new detail")

    def test_critical_past_the_reminder_window_reminds(self):
        prev = row(CRIT, since_h=10, alerted_h=6.5)
        d = decide(prev, Result("k", CRIT, "x"), NOW)
        self.assertEqual(d.action, "remind")
        self.assertEqual(d.row.last_alerted_at, NOW)
        self.assertEqual(d.crit_since, prev.since)

    def test_custom_remind_hours(self):
        prev = row(CRIT, alerted_h=2.5)
        self.assertEqual(decide(prev, Result("k", CRIT, "x"), NOW, remind_hours=2).action, "remind")

    def test_first_ok_after_critical_does_not_resolve_yet(self):
        d = decide(row(CRIT, alerted_h=1), Result("k", OK, "fine"), NOW)
        self.assertEqual(d.action, "none")
        self.assertEqual((d.row.level, d.row.consecutive_ok), (CRIT, 1))

    def test_second_consecutive_ok_resolves(self):
        prev = row(CRIT, since_h=3, alerted_h=1, ok=1)
        d = decide(prev, Result("k", OK, "fine"), NOW)
        self.assertEqual(d.action, "resolve")
        self.assertEqual(d.crit_since, prev.since)
        self.assertEqual((d.row.level, d.row.consecutive_ok), (OK, 0))

    def test_critical_again_resets_the_ok_streak(self):
        d = decide(row(CRIT, alerted_h=1, ok=1), Result("k", CRIT, "again"), NOW)
        self.assertEqual(d.row.consecutive_ok, 0)

    def test_drop_to_warn_after_critical_resolves_into_warn(self):
        prev = row(CRIT, alerted_h=1, ok=1)
        d = decide(prev, Result("k", WARN, "degraded"), NOW)
        self.assertEqual((d.action, d.row.level), ("resolve", WARN))


class PersistenceTests(unittest.TestCase):
    def test_load_states_maps_rows(self):
        db_rows = [{"check_key": "k", "level": "crit", "detail": None, "since": NOW,
                    "last_seen": NOW, "last_alerted_at": NOW, "consecutive_ok": 1}]
        with patch("community.store.db.query", return_value=db_rows):
            states = state.load_states()
        self.assertEqual(states["k"], Row("k", "crit", "", NOW, NOW, NOW, 1))

    def test_save_upserts_every_column(self):
        with patch("community.store.db.execute") as ex:
            state.save(Row("k", "warn", "d", NOW, NOW, None, 0))
        sql, params = ex.call_args[0]
        self.assertIn("ON CONFLICT (check_key) DO UPDATE", sql)
        self.assertEqual(params, ("k", "warn", "d", NOW, NOW, None, 0))

    def test_get_epoch_returns_existing_row(self):
        with patch("community.store.db.one", return_value={"since": NOW}), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW + timedelta(days=1)), NOW)
        ex.assert_not_called()

    def test_get_epoch_creates_it_on_first_run(self):
        with patch("community.store.db.one", return_value=None), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW), NOW)
        self.assertIn("_epoch", ex.call_args[0][0])

    def test_get_epoch_without_create_never_writes(self):
        with patch("community.store.db.one", return_value=None), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW, create=False), NOW)
        ex.assert_not_called()
