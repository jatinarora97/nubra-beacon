"""The prod VM runs the registry baked into the image (its compose file has no registry mount), so the only
host-side switch it has is .env. REDDIT_APIFY_ENABLED flips the dormant Reddit-via-Apify source from there."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from community.config import settings as settings_module
from community.scrape import reddit_apify


def registry(**env):
    with patch.dict(os.environ, env, clear=False):
        if "REDDIT_APIFY_ENABLED" not in env:
            os.environ.pop("REDDIT_APIFY_ENABLED", None)
        return settings_module._registry()


class RedditApifyFlagTests(unittest.TestCase):
    def test_unset_leaves_the_shipped_default_off(self):
        self.assertIs(registry()["sources"]["reddit_apify"]["enabled"], False)

    def test_true_turns_it_on_and_keeps_the_rest_of_the_block(self):
        block = registry(REDDIT_APIFY_ENABLED="true")["sources"]["reddit_apify"]
        self.assertIs(block["enabled"], True)
        self.assertEqual(block["actor"], "harshmaur~reddit-scraper-pro")      # the baked-in settings still apply
        self.assertEqual(block["post_overrides"]["IndianStockMarket"], 25)

    def test_the_usual_spellings_are_understood(self):
        for value in ("1", "True", "YES", " on "):
            self.assertIs(registry(REDDIT_APIFY_ENABLED=value)["sources"]["reddit_apify"]["enabled"], True, value)
        for value in ("0", "False", "no", "OFF"):
            self.assertIs(registry(REDDIT_APIFY_ENABLED=value)["sources"]["reddit_apify"]["enabled"], False, value)

    def test_an_empty_or_unrecognised_value_changes_nothing(self):
        for value in ("", "maybe", "enabled-ish"):
            self.assertIs(registry(REDDIT_APIFY_ENABLED=value)["sources"]["reddit_apify"]["enabled"], False, value)

    def test_other_sources_are_untouched(self):
        plain, flagged = registry(), registry(REDDIT_APIFY_ENABLED="true")
        for name in ("youtube", "instagram", "reddit", "twitter"):
            self.assertEqual(plain["sources"][name], flagged["sources"][name], name)


class DefaultActorTests(unittest.TestCase):
    def test_a_block_without_an_actor_gets_the_recommended_one_not_the_expensive_one(self):
        self.assertEqual(reddit_apify._actor({}), "harshmaur~reddit-scraper-pro")
        self.assertEqual(reddit_apify._actor({"actor": "trudax/reddit-scraper-lite"}), "trudax~reddit-scraper-lite")
