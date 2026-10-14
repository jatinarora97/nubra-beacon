"""Shared test setup: no test may reach the Apify API by accident."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_apify_account_lookup(monkeypatch):
    """reddit_apify asks Apify how much of the monthly limit is used before each run; tests that care
    about that patch it themselves, every other test must not touch the network."""
    from community.scrape import reddit_apify
    monkeypatch.setattr(reddit_apify, "_account_usage", lambda: None)
