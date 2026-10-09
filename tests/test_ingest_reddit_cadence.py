"""Regression: the scrape stage must not crash when Reddit is skipped by its cadence gate.

Since the 2026-08-19 cadence commit (fetch_every_hours: 3), two of every three hourly
runs skip the Reddit fetch. `sorts` was only assigned inside the fetch branch, so the
stage's final `return {... "reddit_sorts": sorts ...}` raised UnboundLocalError AFTER all
collection had finished: the stage was reported FAILED and its stats were lost.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from community.scrape import ingest

NOW = datetime(2026, 10, 8, 5, 30, tzinfo=timezone.utc)
REGISTRY = {"sources": {
    "twitter": {"csv_backfill": None},
    "reddit": {"fetch_every_hours": 3, "sort_types_hourly": ["new"],
               "sort_types_daily_extra": ["top"]},
}}


def run_ingest(last_reddit_success, daily=False):
    fake_repo = MagicMock()
    fake_repo.now_utc.return_value = NOW
    fake_repo.get_state.return_value = ({"last_success_at": last_reddit_success}
                                        if last_reddit_success else None)
    with patch.object(ingest, "settings", SimpleNamespace(registry=REGISTRY)), \
         patch.object(ingest, "repo", fake_repo), \
         patch.object(ingest.twitter, "fetch_live_capped", return_value=([], "note")), \
         patch.object(ingest.reddit, "fetch_live", return_value=([], ["ok"])) as fetch, \
         patch("community.scrape.refresh.run", return_value={}), \
         patch("community.scrape.keyword_search.run", return_value={}), \
         patch("community.scrape.extra_sources.run", return_value={}):
        stats = ingest.run(daily=daily)
    return stats, fetch


class RedditCadenceTests(unittest.TestCase):
    def test_a_cadence_skipped_run_returns_stats_instead_of_crashing(self):
        stats, fetch = run_ingest(NOW - timedelta(hours=1))  # last ran 1h ago: not due (3h cadence)
        fetch.assert_not_called()
        self.assertEqual(stats["reddit_sorts"], [])
        self.assertEqual(stats["reddit_health"], ["cadence skip (every 3h)"])

    def test_a_due_run_still_reports_the_sorts_it_fetched(self):
        stats, fetch = run_ingest(NOW - timedelta(hours=4))  # due
        fetch.assert_called_once_with(sorts=["new"])
        self.assertEqual(stats["reddit_sorts"], ["new"])

    def test_the_morning_build_fetches_even_inside_the_cadence_window(self):
        stats, fetch = run_ingest(NOW - timedelta(hours=1), daily=True)
        fetch.assert_called_once_with(sorts=["new", "top"])
        self.assertEqual(stats["reddit_sorts"], ["new", "top"])
