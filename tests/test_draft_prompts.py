"""Per-source reply prompts: Reddit has its own prompt file, every other source keeps the default.

The point is isolation: editing community/llm/prompts/reply_reddit.txt must change Reddit replies and nothing else.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from community.recommend import draft

OPP = {"id": 1, "thread_id": "t3_x", "matched_insight": {}}
CATALOG = [{"id": "f_1"}]


def valid_answer(source="reddit"):
    # Reddit is judged by the conditional rule (a short natural disclosure when Nubra is cited); every other source by
    # the exact house sentence
    line = "(I work at Nubra)" if source == "reddit" else draft.DISCLOSURE
    return json.dumps({
        "brand": {"text": "A factual reply.", "features_cited": ["f_1"]},
        "rep": {"text": f"A peer reply. {line}", "features_cited": ["f_1"],
                "disclosure_included": True},
        "skip_reason": None})


class PromptSelectionTests(unittest.TestCase):
    def test_reddit_uses_its_own_prompt_file(self):
        self.assertEqual(draft._system_for("reddit"), draft._load_prompt("reply_reddit"))

    def test_every_other_source_keeps_the_default_prompt(self):
        for source in ("twitter", "youtube", "github", "community_forum", "app_review", "linkedin", "instagram"):
            self.assertEqual(draft._system_for(source), draft._DRAFT_SYSTEM, source)

    def test_no_disclosure_placeholder_is_left_unfilled(self):
        self.assertNotIn("{DISCLOSURE}", draft._system_for("reddit"))
        self.assertIn(draft.DISCLOSURE, draft._DRAFT_SYSTEM)       # the default prompt still carries the sentence

    def test_the_reddit_prompt_keeps_the_json_contract_the_parser_needs(self):
        # a functional contract, not a style rule: lose these and every draft becomes unparsable
        text = draft._system_for("reddit")
        for needle in ('"brand"', '"rep"', "features_cited", "skip_reason", "ONLY JSON"):
            self.assertIn(needle, text)


class IsolationTests(unittest.TestCase):
    def with_reddit_prompt(self, body: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        (Path(tmp.name) / "reply_reddit.txt").write_text(body, encoding="utf-8")
        return patch.object(draft, "_PROMPTS_DIR", Path(tmp.name))

    def test_editing_the_reddit_prompt_changes_reddit_only(self):
        with self.with_reddit_prompt("EDITED REDDIT PROMPT {DISCLOSURE}"):
            self.assertEqual(draft._system_for("reddit"), "EDITED REDDIT PROMPT " + draft.DISCLOSURE)
            self.assertEqual(draft._system_for("twitter"), draft._DRAFT_SYSTEM)
            self.assertNotIn("EDITED", draft._system_for("youtube"))

    def test_the_edit_is_picked_up_without_a_code_change(self):
        with self.with_reddit_prompt("first"):
            self.assertEqual(draft._system_for("reddit"), "first")
        with self.with_reddit_prompt("second"):
            self.assertEqual(draft._system_for("reddit"), "second")

    def test_a_missing_prompt_file_falls_back_to_the_default_and_says_so(self):
        with patch.object(draft, "_PROMPTS_DIR", Path(tempfile.gettempdir()) / "no_such_prompt_dir"):
            with self.assertLogs("beacon.draft", level="WARNING") as logs:
                system = draft._system_for("reddit")
        self.assertEqual(system, draft._DRAFT_SYSTEM)
        self.assertIn("reply_reddit", " ".join(logs.output))


class DraftOneUsesTheRightPromptTests(unittest.TestCase):
    def run_draft(self, source: str):
        with patch.object(draft, "complete", return_value=(valid_answer(source), {})) as llm, \
             patch.object(draft, "_thread_excerpt", return_value="- a thread"), \
             patch.object(draft.compliance, "check", return_value=(True, [])):
            drafts, gate = draft._draft_one({**OPP, "source": source}, CATALOG)
        return drafts, gate, llm

    def test_a_reddit_opportunity_is_drafted_with_the_reddit_prompt(self):
        drafts, gate, llm = self.run_draft("reddit")
        self.assertIsNotNone(drafts)
        self.assertEqual(llm.call_args.args[1], draft._system_for("reddit"))

    def test_a_twitter_opportunity_is_drafted_with_the_default_prompt(self):
        drafts, _, llm = self.run_draft("twitter")
        self.assertIsNotNone(drafts)
        self.assertEqual(llm.call_args.args[1], draft._DRAFT_SYSTEM)

    def test_the_two_prompts_are_independent_objects_in_the_call(self):
        _, _, reddit_llm = self.run_draft("reddit")
        _, _, twitter_llm = self.run_draft("twitter")
        self.assertIs(reddit_llm.call_args.args[0], twitter_llm.call_args.args[0])   # same model setting


if __name__ == "__main__":
    unittest.main()
