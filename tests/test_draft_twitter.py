"""Twitter reply drafts: their own prompt file, one-tweet length, the plain voice, and a disclosure only when Nubra
is actually mentioned (the same conditional rule as Reddit, never the exact house sentence).

Twitter measures length in characters (a reply is one tweet, 280 max); Reddit measures it in words.
"""
from __future__ import annotations

import json
import pathlib
import unittest
from unittest.mock import patch

from community.recommend import draft

VALID = {"f_1"}
PROMPT_FILE = pathlib.Path(__file__).resolve().parent.parent / "community" / "llm" / "prompts" / "reply_twitter.txt"


def data(rep, brand="Short, factual answer.", rep_cited=(), brand_cited=()):
    return {"brand": {"text": brand, "features_cited": list(brand_cited)},
            "rep": {"text": rep, "features_cited": list(rep_cited)}, "skip_reason": None}


def problems(rep, source="twitter", **kw):
    return draft._validate_drafts(data(rep, **kw), VALID, source)


class TwitterPromptFileTests(unittest.TestCase):
    def setUp(self):
        self.text = draft._system_for("twitter")

    def test_the_template_ships_and_is_the_prompt_twitter_uses(self):
        self.assertTrue(PROMPT_FILE.is_file())
        self.assertEqual(draft._SOURCE_PROMPTS["twitter"], "reply_twitter")
        self.assertEqual(self.text, PROMPT_FILE.read_text(encoding="utf-8"))      # nothing to substitute

    def test_it_keeps_the_json_contract_the_parser_needs(self):
        for needle in ('"brand"', '"rep"', "features_cited", "skip_reason", "ONLY JSON"):
            self.assertIn(needle, self.text)

    def test_it_asks_for_no_disclosure_sentence_and_has_no_placeholder(self):
        self.assertNotIn("{DISCLOSURE}", self.text)
        self.assertNotIn(draft.DISCLOSURE, self.text)
        self.assertNotIn("verbatim", self.text.lower())

    def test_it_asks_for_a_disclosure_only_when_nubra_is_mentioned_and_never_for_a_denial(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("names nubra or cites a nubra feature", low)
        self.assertIn("never mentions nubra needs no such line", low)
        self.assertIn("never write a line that denies the connection", low)

    def test_it_tells_the_model_the_one_tweet_limit_and_the_plain_format(self):
        low = " ".join(self.text.lower().split())
        self.assertIn(f"{draft.REPLY_MAX_CHARS['twitter']} characters", low)
        for needle in ("no hashtags", "no links", "no emoji"):
            self.assertIn(needle, low)

    def test_it_keeps_the_compliance_hard_rules(self):
        for needle in ("ONLY facts present in NUBRA_FEATURES", "No investment advice", "Never disparage a competitor",
                       "coming soon"):
            self.assertIn(needle, self.text)


class TwitterDisclosureTests(unittest.TestCase):
    def test_a_reply_that_never_mentions_nubra_needs_no_disclosure(self):
        self.assertEqual(problems("charges are the part to read line by line, brokerage is the small bit"), [])

    def test_the_exact_house_sentence_is_not_required(self):
        self.assertNotIn("rep: disclosure line missing", problems("depends on what you trade honestly"))

    def test_mentioning_nubra_without_a_disclosure_is_flagged(self):
        out = problems("Nubra shows max loss before you place the order")
        self.assertTrue(any("without a disclosure" in p for p in out), out)

    def test_citing_a_feature_counts_even_without_the_name(self):
        text = "the platform shows max loss before you place the order"
        self.assertTrue(any("without a disclosure" in p for p in problems(text, rep_cited=["f_1"])))
        self.assertEqual(problems(text + " (I work at Nubra)", rep_cited=["f_1"]), [])

    def test_a_short_natural_disclosure_is_accepted(self):
        self.assertEqual(problems("Nubra shows max loss up front. I work at Nubra."), [])
        self.assertEqual(problems("Nubra has a scalper mode (I'm on the Nubra team)"), [])

    def test_a_garbled_or_denying_disclosure_is_rejected(self):
        for bad in ("Full disclosure — I'm part not of the team at Nubra.", "I'm not affiliated with Nubra.",
                    "I don't work at Nubra."):
            self.assertTrue(problems(f"Nubra has a scalper mode. {bad}"), bad)

    def test_the_official_brand_voice_needs_no_disclosure_line(self):
        self.assertEqual(problems("fine", brand="Nubra shows max loss up front", brand_cited=["f_1"]), [])

    def test_the_older_checks_still_apply(self):
        self.assertIn("rep: empty", problems(""))
        out = draft._validate_drafts({"brand": {"text": "b", "features_cited": ["zzz"]},
                                      "rep": {"text": "r", "features_cited": []}}, VALID, "twitter")
        self.assertTrue(any("unknown features_cited" in p for p in out))


class OneTweetLengthTests(unittest.TestCase):
    LIMIT = draft.REPLY_MAX_CHARS["twitter"]

    def test_the_limit_is_one_tweet(self):
        self.assertEqual(self.LIMIT, 280)

    def test_exactly_one_tweet_passes_and_one_character_more_is_flagged(self):
        self.assertEqual(problems("x" * self.LIMIT), [])
        out = problems("x" * (self.LIMIT + 1))
        self.assertTrue(any("rep: too long (281 characters, max 280)" == p for p in out), out)

    def test_the_brand_reply_is_one_tweet_too(self):
        self.assertEqual(problems("fine", brand="y" * self.LIMIT), [])
        out = problems("fine", brand="y" * (self.LIMIT + 1))
        self.assertTrue(any("brand: too long (281 characters, max 280)" == p for p in out), out)

    def test_grounding_citations_do_not_count_because_the_reader_never_sees_them(self):
        text = ("x" * (self.LIMIT - 10)) + " (f_12, f_7)"
        self.assertGreater(len(text), self.LIMIT)
        self.assertFalse(any("too long" in p for p in problems(text)))

    def test_the_cap_is_in_characters_not_words(self):
        many_short_words = " ".join(["a"] * 140)          # 140 words, 279 characters: fine for a tweet
        self.assertEqual(len(many_short_words), 279)
        self.assertEqual(problems(many_short_words), [])

    def test_reddit_is_still_measured_in_words_not_characters(self):
        long_but_few_words = " ".join(["incomprehensibilities"] * 40)       # 40 words, 880 characters
        self.assertEqual(problems(long_but_few_words, source="reddit"), [])
        out = problems(" ".join(["word"] * (draft.REPLY_MAX_WORDS["rep"] + 1)), source="reddit")
        self.assertTrue(any("words, max" in p for p in out), out)

    def test_twitter_is_not_measured_in_words(self):
        out = problems("word " * 150)                      # 750 characters: too long, and reported in characters
        self.assertTrue(any("characters, max 280" in p for p in out), out)
        self.assertFalse(any("words, max" in p for p in out), out)


class TwitterPlainVoiceTests(unittest.TestCase):
    def test_each_plain_voice_rule_is_flagged_for_twitter_too(self):
        cases = {
            "**The theory wasn't about stocks.** Benner was a farmer.": "bold",
            "Read this: https://example.com/guide": "link",
            "sahi bola bhai \U0001F602 keep going": "emoji",
            "Good discipline #investing": "hashtag",
            "You should check out the app, it is a game-changer.": "marketing",
        }
        for text, label in cases.items():
            out = problems(text)
            self.assertTrue(any(label in p for p in out), (label, out))

    def test_rupee_sign_and_ordinary_symbols_are_not_emoji(self):
        self.assertEqual(problems("Brokerage is ₹20 a trade, STT extra → check the contract note"), [])

    def test_a_source_without_its_own_prompt_is_still_not_held_to_these_rules(self):
        text = f"**Bold** \U0001F642 #tag https://x.com {draft.DISCLOSURE}"
        self.assertEqual(problems(text, source="instagram"), [])
        self.assertIn("rep: disclosure line missing", problems("no line at all", source="instagram"))


class DraftOneForTwitterTests(unittest.TestCase):
    OPP = {"id": 1, "source": "twitter", "thread_id": "170", "matched_insight": {}}
    CATALOG = [{"id": "f_1"}]

    def answer(self, rep, brand="A plain factual reply."):
        return json.dumps({"brand": {"text": brand, "features_cited": []},
                           "rep": {"text": rep, "features_cited": []}, "skip_reason": None})

    def run_draft(self, *answers):
        with patch.object(draft, "complete", side_effect=[(a, {}) for a in answers]) as llm, \
             patch.object(draft, "_thread_excerpt", return_value="- a tweet"), \
             patch.object(draft.compliance, "check", return_value=(True, [])):
            drafts, gate = draft._draft_one(self.OPP, self.CATALOG)
        return drafts, gate, llm

    def test_a_good_tweet_reply_is_accepted_first_time_without_any_disclosure(self):
        drafts, gate, llm = self.run_draft(self.answer("read the charges line by line before you pick"))
        self.assertIsNotNone(drafts)
        self.assertEqual(gate, {"passed": 1, "regenerated": 0, "dropped": 0})
        self.assertEqual(llm.call_args.args[1], draft._system_for("twitter"))

    def test_a_reply_too_long_for_one_tweet_is_regenerated_and_the_model_is_told_why(self):
        drafts, gate, llm = self.run_draft(self.answer("x" * 400), self.answer("short enough now"))
        self.assertIsNotNone(drafts)
        self.assertEqual(gate["regenerated"], 1)
        self.assertIn("too long (400 characters, max 280)", llm.call_args.args[2])

    def test_a_model_that_never_fits_the_tweet_is_dropped_after_two_regenerations(self):
        drafts, gate, llm = self.run_draft(*[self.answer("x" * 400)] * 3)
        self.assertIsNone(drafts)
        self.assertEqual(gate["dropped"], 1)
        self.assertEqual(llm.call_count, 3)


if __name__ == "__main__":
    unittest.main()
