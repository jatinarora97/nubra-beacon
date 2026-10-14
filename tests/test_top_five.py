"""Five recommendations where there used to be three: the numbers, and the places that must agree on them."""
from __future__ import annotations

import json
import pathlib
import unittest

import pytest

from community.compose import render
from community.recommend import draft
from community.social_recommend import models, service

ROOT = pathlib.Path(__file__).resolve().parent.parent


class DashboardAndHeadsUpTests(unittest.TestCase):
    def test_the_dashboard_api_sends_five_top_actions(self):
        read_api = pytest.importorskip("community.api.read_api")
        self.assertEqual(read_api.TOP_ACTIONS, 5)

    def test_the_web_page_shows_as_many_as_the_api_sends(self):
        # the page trimmed the list itself (slice(0, 3)), so the API limit alone changed nothing visible
        read_api = pytest.importorskip("community.api.read_api")
        tsx = (ROOT / "webapp" / "app" / "page.tsx").read_text(encoding="utf-8")
        self.assertIn(f"top_actions!.slice(0, {read_api.TOP_ACTIONS})", tsx)

    def test_the_heads_up_summary_lists_five(self):
        self.assertEqual(render.TOP_STANDING, 5)


class ContentBriefTests(unittest.TestCase):
    def test_five_briefs_a_day(self):
        self.assertEqual(draft.MAX_PROPOSALS, 5)

    def test_the_model_is_asked_for_more_candidates_than_survive_the_filters(self):
        # taxonomy, per-family cap, repeat-judge and the compliance gate all drop candidates
        self.assertGreater(draft.CANDIDATES_ASKED, draft.MAX_PROPOSALS)
        system = draft._content_system(["carousel"], ["x_post"])
        self.assertIn(f"(exactly {draft.CANDIDATES_ASKED} candidates)", system)
        self.assertNotIn("exactly 5 candidates", system)

    def test_the_output_budget_grows_with_the_candidates(self):
        self.assertGreaterEqual(draft.CONTENT_MAX_TOKENS, 1500 * draft.CANDIDATES_ASKED)

    def test_the_prompt_still_carries_the_taxonomy_and_the_json_contract(self):
        system = draft._content_system(["carousel", "thread"], ["x_post"])
        for needle in ("['carousel', 'thread']", "['x_post']", '"candidates"', "NO EMOJIS", "ANTI-REPETITION"):
            self.assertIn(needle, system)


def _rec(i: int) -> dict:
    return {"recommendation_key": f"k{i}", "segment": "retail" if i % 2 else "api", "platform": "x",
            "format": "text_post", "title": "t", "hook": "h", "body": "b", "cta": "c", "hashtags": [],
            "feature_ids": ["f"], "evidence_item_ids": [1], "rationale": "r", "visual_brief": "v",
            "priority_score": 50}


class SocialQueueTests(unittest.TestCase):
    def test_a_response_of_ten_recommendations_is_accepted(self):
        env = models.GenerationEnvelope.model_validate({"recommendations": [_rec(i) for i in range(10)]})
        self.assertEqual(len(env.recommendations), 10)

    def test_more_than_ten_is_still_rejected(self):
        with self.assertRaises(Exception):
            models.GenerationEnvelope.model_validate({"recommendations": [_rec(i) for i in range(11)]})

    def test_the_prompt_asks_for_five_and_five(self):
        text = " ".join(service.SYSTEM_PROMPT.split())
        self.assertIn("Create at most ten recommendations", text)
        self.assertIn("Prefer five retail and five API", text)

    def test_the_output_budget_fits_ten_recommendations(self):
        self.assertGreaterEqual(service.MAX_TOKENS, 16000)


if __name__ == "__main__":
    unittest.main()
