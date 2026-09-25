from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from community.scrape import extra_sources, github_public, youtube
from community.scrape.base import SocialItem


class ExtraSourceContractTests(unittest.TestCase):
    def test_new_source_values_are_accepted(self):
        for source, source_type in (
            ("youtube", "comment"),
            ("github", "issue"),
            ("community_forum", "post"),
            ("app_review", "review"),
        ):
            item = SocialItem(
                source=source,
                source_type=source_type,
                external_id=f"{source}-1",
                thread_id=f"{source}-1",
                author="tester",
                text="A relevant public product discussion",
                url="https://example.com/item",
                created_at=datetime.now(timezone.utc),
            )
            self.assertEqual(item.source, source)

    def test_youtube_without_key_is_a_safe_empty_source(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("YOUTUBE_API_KEY", None)
            self.assertEqual(list(youtube.fetch({"queries": {"retail": ["test"]}})), [])

    def test_disabled_source_does_not_call_fetcher(self):
        fetcher_called = False

        def fetcher(_):
            nonlocal fetcher_called
            fetcher_called = True
            return []

        result = extra_sources._run_source("youtube", fetcher, {"enabled": False})
        self.assertFalse(fetcher_called)
        self.assertFalse(result["enabled"])

    def test_source_failure_is_returned_not_raised(self):
        def failing_fetcher(_):
            raise RuntimeError("source unavailable")

        with patch.object(extra_sources.repo, "advance_state"):
            result = extra_sources._run_source(
                "github", failing_fetcher, {"enabled": True}
            )
        self.assertIn("RuntimeError", result["error"])
        self.assertEqual(result["inserted"], 0)

    def test_github_relevance_rejects_obvious_noise(self):
        row = {
            "title": "Casino NFT airdrop",
            "body": "Spam betting promotion",
            "repository_url": "https://api.github.com/repos/noise/repo",
            "labels": [],
        }
        score, _, deny_hits = github_public._relevance(
            row, "generic query", {"relevance": {"min_score": 2}}
        )
        self.assertLess(score, 2)
        self.assertTrue(deny_hits)


if __name__ == "__main__":
    unittest.main()
