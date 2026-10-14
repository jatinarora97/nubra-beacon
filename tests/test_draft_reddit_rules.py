"""Reddit reply rules: plain human voice, disclosure only when Nubra is actually mentioned, and the checks for both.

Reddit has its own prompt (community/llm/prompts/reply_reddit.txt) and, because of that, its own validator rules.
Every other source keeps the exact-sentence disclosure rule it always had.

The acceptance fixtures are the team's own example replies: the ones that never mention Nubra must pass untouched;
the ones that name Nubra must need a disclosure.
"""
from __future__ import annotations

import pathlib
import unittest

import pytest

from community.recommend import compliance, draft

VALID = {"f_1"}
ROOT = pathlib.Path(__file__).resolve().parent.parent
# the proposed Reddit prompt (docs/): the content checks below are about it; the ACTIVE prompt file is the team's own
# and only has to keep the parser's contract
PROPOSAL = ROOT / "docs" / "reply-reddit-prompt-proposal-2026-10-14.txt"
TRUE_DISCLOSURE = "Full disclosure \u2014 I'm part of the team at Nubra."    # the original wording, spelled out here


def data(rep, brand="Short, factual answer.", rep_cited=(), brand_cited=()):
    return {"brand": {"text": brand, "features_cited": list(brand_cited)},
            "rep": {"text": rep, "features_cited": list(rep_cited)}, "skip_reason": None}


def problems(rep, source="reddit", **kw):
    return draft._validate_drafts(data(rep, **kw), VALID, source)


EX_SIP = (
    "It's genuinely encouraging to see this. Markets dipped, and instead of stopping, people kept their SIPs "
    "running and many added more. That's the whole point of the habit: you buy more units when prices are "
    "lower, without having to be brave about it.\n\nOne thing worth noticing, though. Small-cap funds have been "
    "the top category for three months straight. Buying the dip is good discipline; piling into the most "
    "volatile corner of the market because it's what everyone else is doing is something else. If small caps "
    "are a large share of your portfolio, it may be worth checking whether that's a choice you made or a drift "
    "that happened.\n\nAnd if you're new and this was your first real fall, notice what you did. If you stayed "
    "put, that matters more than any return you'll see this year. Ten years from now, nobody will remember "
    "September. They'll remember whether they kept going.")
EX_LOSS = (
    "not gonna joke on this one bro.\n\nthe 8L -> loss part hurts the most, i get it. but trying to win 5L back "
    "with the last 1L is exactly how that 1L goes too. that's not a trade anymore, that's the loss talking.\n\n"
    "honest advice from someone who's watched a lot of these threads: close the app today. don't add money, "
    "don't borrow, don't \"one last trade.\" give it a few weeks before you even look at a chart again. the "
    "market will literally still be there.\n\nthe 5L is gone either way. keeping the 1L is the win available to "
    "you right now, and it's a real one.\n\nand if this is messing with your head more than a normal bad week, "
    "talk to someone. a friend, family, or Tele MANAS (14416, free) if you'd rather talk to a stranger. no "
    "shame in it, this stuff gets heavy")
EX_CIRCUIT = (
    "Hard truth first: if it's hitting the 5% lower circuit every day, there are no buyers. Nobody can sell at "
    "that point. You're in a queue.\n\nWhat you can do is get to the front of the queue.\n\nFind out which "
    "surveillance stage it's in. Your broker app shows a tag when you place an order. Or check NSE's "
    "surveillance list.\nPlace a limit sell at the lower circuit price, either as an after-market order the "
    "night before or in the pre-open session from 9:00 AM. Orders are filled price first, then time. Earlier is "
    "better.\nOpen market depth. If you see only sellers and zero buyers, your order is waiting, not broken. "
    "Leave it.\nIf it's in a periodic call auction, it only trades in set windows. Your order waits for the next "
    "one.\n\nExpect it to take days, not minutes. Each day the circuit hits, re-place the order early.")
EX_PHONE = (
    "Short answer: no broker can promise this :)\nZerodha, Nubra, Upstox - all of them have to send ur number "
    "to the exchange, depository and KYC agency. Same rule, same pipeline. Switching moves your number into the "
    "same system again.\nIf U want fewer calls tho - change the variables you control.")
EX_SCALPER = (
    "not a scalper myself, i'm more the guy who learned what a stop-loss is the expensive way \U0001F62D so no "
    "flex book from me lol\n\nafaik zerodha console has verified P&L, and sensibull does it for upstox, angel and "
    "a few others - and real talk, scalping vs gambling comes down to rules, not the name. if you actually "
    "scalp, use tools that bake the rules in. nubra's scalper mode lets you set SL and target right on the "
    "chart order, and zerodha has a kill switch...")


class DisclosureOnlyWhenNubraIsMentionedTests(unittest.TestCase):
    def test_a_reply_that_never_mentions_nubra_needs_no_disclosure(self):
        self.assertEqual(problems("Honest answer: stay out of it for a few weeks."), [])

    def test_the_teams_own_replies_that_never_mention_nubra_pass_untouched(self):
        for name, text in (("sip", EX_SIP), ("loss", EX_LOSS), ("circuit", EX_CIRCUIT)):
            self.assertEqual(problems(text), [], name)

    def test_mentioning_nubra_without_a_disclosure_is_flagged(self):
        out = problems("Nubra shows max loss and breakeven before you place an options strategy.")
        self.assertTrue(any("without a disclosure" in p for p in out), out)

    def test_the_teams_replies_that_name_nubra_need_one(self):
        self.assertTrue(any("without a disclosure" in p for p in problems(EX_PHONE)))
        self.assertTrue(any("without a disclosure" in p for p in problems(EX_SCALPER)))

    def test_natural_wordings_of_the_disclosure_are_accepted(self):
        for form in ("(I work at Nubra)", "Disclosure: I work at Nubra.", "I work for Nubra, so salt as needed.",
                     "Full disclosure — I'm part of the team at Nubra, a SEBI-regulated broker.",
                     "full disclosure — i'm part of the team at nubra", "I'm on the Nubra team btw.",
                     "(I'm with Nubra, fwiw)", "I am part of the team at Nubra.",
                     "(main Nubra mein kaam karta hoon)"):
            self.assertEqual(problems(f"Nubra has a scalper mode with SL on the chart order. {form}"), [], form)

    def test_the_original_house_sentence_is_still_accepted(self):
        self.assertEqual(problems(f"Nubra has a scalper mode. {TRUE_DISCLOSURE}"), [])

    def test_a_garbled_or_denying_disclosure_is_not_a_disclosure(self):
        for bad in ("Full disclosure — I'm part not of the team at Nubra.", "I'm not affiliated with Nubra.",
                    "I don't work at Nubra.", "I'm not part of Nubra.", "I have no connection to Nubra."):
            out = problems(f"Nubra has a scalper mode. {bad}")
            self.assertTrue(out, bad)

    def test_a_denial_is_called_out_as_contradictory(self):
        out = problems("Nubra has a scalper mode. Full disclosure — I'm part not of the team at Nubra.")
        self.assertTrue(any("contradict" in p for p in out), out)

    def test_citing_a_feature_counts_as_a_nubra_claim_even_without_the_name(self):
        text = "The platform shows max loss before you place the order."
        self.assertTrue(any("without a disclosure" in p for p in problems(text, rep_cited=["f_1"])))
        self.assertEqual(problems(text + " (I work at Nubra)", rep_cited=["f_1"]), [])

    def test_the_official_brand_voice_needs_no_disclosure_line(self):
        self.assertEqual(problems("Honest answer.", brand="We at Nubra show max loss before you place the order.",
                                  brand_cited=["f_1"]), [])

    def test_the_older_checks_still_apply(self):
        self.assertIn("rep: empty", problems(""))
        out = draft._validate_drafts({"brand": {"text": "b", "features_cited": ["zzz"]},
                                      "rep": {"text": "r", "features_cited": []}}, VALID, "reddit")
        self.assertTrue(any("unknown features_cited" in p for p in out))


class OtherSourcesKeepTheExactSentenceTests(unittest.TestCase):
    def test_twitter_still_requires_the_exact_disclosure_sentence(self):
        self.assertIn("rep: disclosure line missing", problems("A reply with no disclosure.", source="twitter"))
        self.assertIn("rep: disclosure line missing",
                      problems("Nubra has X. (I work at Nubra)", source="twitter"))      # natural form: not enough here
        self.assertEqual(problems(f"A reply. {draft.DISCLOSURE}", source="twitter"), [])

    def test_no_source_given_means_the_original_behaviour(self):
        self.assertIn("rep: disclosure line missing", problems("A reply with no disclosure.", source=""))
        self.assertEqual(draft._validate_drafts(data(f"A reply. {draft.DISCLOSURE}"), VALID), [])


class RedditStyleTests(unittest.TestCase):
    def test_the_teams_own_replies_pass_the_style_rules(self):
        for text in (EX_SIP, EX_LOSS, EX_CIRCUIT):
            self.assertLess(len(text.split()), draft.REPLY_MAX_WORDS["rep"])
            self.assertEqual([p for p in problems(text) if "rep:" in p], [])

    def test_each_style_rule_is_flagged_for_reddit(self):
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

    def test_a_reply_that_is_too_long_is_flagged(self):
        out = problems(" ".join(["word"] * (draft.REPLY_MAX_WORDS["rep"] + 1)))
        self.assertTrue(any("too long" in p for p in out), out)
        out = problems("Fine.", brand=" ".join(["word"] * (draft.REPLY_MAX_WORDS["brand"] + 1)))
        self.assertTrue(any("brand: too long" in p for p in out), out)

    def test_the_brand_reply_is_held_to_the_same_plain_style(self):
        out = problems("Fine.", brand="We have a seamless way to open an account \U0001F642")
        self.assertTrue(any(p.startswith("brand:") and "emoji" in p for p in out), out)
        self.assertTrue(any(p.startswith("brand:") and "marketing" in p for p in out), out)

    def test_the_original_scalper_reply_trips_both_the_emoji_and_the_disclosure_rules(self):
        out = problems(EX_SCALPER)
        self.assertTrue(any("emoji" in p for p in out))
        self.assertTrue(any("without a disclosure" in p for p in out))
        fixed = EX_SCALPER.replace(" \U0001F62D", "") + " (I work at Nubra)"
        self.assertEqual(problems(fixed), [])

    def test_real_preview_drafts_with_these_habits_are_caught(self):
        # shapes taken from the 2026-10-14 preview: bold lead-ins, emojis, a Hinglish reply with emojis
        self.assertTrue(any("bold" in p for p in problems("**The apparent hits are mostly hindsight selection.** Fine.")))
        self.assertTrue(any("emoji" in p for p in problems("keep going, capital bachaana sahi soch hai \U0001F91D")))

    def test_other_sources_are_not_held_to_the_reddit_style(self):
        text = f"**Bold** \U0001F642 #tag https://x.com {draft.DISCLOSURE}"
        self.assertEqual(problems(text, source="twitter"), [])

    def test_rupee_sign_and_ordinary_symbols_are_not_emoji(self):
        self.assertEqual(problems("Brokerage is ₹20 a trade, STT extra → check the contract note."), [])


class ActiveRedditPromptTests(unittest.TestCase):
    """Whatever the team writes in reply_reddit.txt, the parser's contract must survive."""

    def test_the_prompt_keeps_the_json_contract(self):
        text = draft._system_for("reddit")
        for needle in ('"brand"', '"rep"', "features_cited", "skip_reason", "ONLY JSON"):
            self.assertIn(needle, text)

    def test_no_placeholder_is_left_unfilled(self):
        self.assertNotIn("{DISCLOSURE}", draft._system_for("reddit"))


class HouseDisclosureTests(unittest.TestCase):
    def test_the_house_sentence_is_a_real_disclosure_and_does_not_deny_the_connection(self):
        # it is what the model is told to write verbatim: it must say the writer IS part of the team
        self.assertIsNone(draft._DENIAL.search(draft.DISCLOSURE), draft.DISCLOSURE)
        self.assertIsNotNone(draft._DISCLOSURE_FORMS.search(draft.DISCLOSURE), draft.DISCLOSURE)


class ProposedRedditPromptTests(unittest.TestCase):
    def setUp(self):
        self.text = PROPOSAL.read_text(encoding="utf-8")

    def test_the_proposal_keeps_the_json_contract(self):
        for needle in ('"brand"', '"rep"', "features_cited", "skip_reason", "ONLY JSON"):
            self.assertIn(needle, self.text)

    def test_it_asks_for_the_plain_human_voice(self):
        low = self.text.lower()
        for needle in ("no emojis", "no headings, no bold", "answer first", "mirror the thread", "never invent a personal"):
            self.assertIn(needle, low)

    def test_nubra_is_mentioned_only_when_a_feature_answers_the_question(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("do not mention nubra unless a feature", low)
        self.assertIn("most replies should not mention nubra at all", low)
        self.assertIn("never as the headline", low)

    def test_the_disclosure_is_described_as_a_short_natural_line_when_nubra_is_mentioned(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("(i work at nubra)", low)
        self.assertIn("has nothing to disclose", low)

    def test_it_tells_the_model_to_skip_crypto_off_topic_and_regulated_advice_threads(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("set skip_reason", low)
        self.assertIn("crypto", low)
        self.assertIn("not about markets", low)

    def test_distress_threads_get_support_and_no_product(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("tele manas (14416", low)
        self.assertIn("never mention nubra or any product", low)

    def test_general_facts_are_not_to_be_asserted_without_certainty(self):
        low = " ".join(self.text.lower().split())
        self.assertIn("no section numbers", low)

    def test_the_proposal_does_not_ask_for_a_disclosure_when_nubra_is_not_mentioned(self):
        self.assertNotIn("must include the disclosure line verbatim", self.text)


class JudgeTests(unittest.TestCase):
    def test_the_judge_asks_for_disclosure_only_when_nubra_is_mentioned(self):
        text = " ".join(compliance._L2_SYSTEM.split())
        self.assertNotIn("Representative replies must disclose Nubra affiliation.", text)
        self.assertIn("mentions Nubra", text)
        self.assertIn("never mentions Nubra needs no such line", text)

    def test_the_judge_treats_a_contradicting_disclosure_as_a_violation(self):
        self.assertIn("contradicts itself", " ".join(compliance._L2_SYSTEM.split()))

    def test_the_judge_tone_line_is_plain_and_human(self):
        text = " ".join(compliance._L2_SYSTEM.split())
        self.assertIn("plain, human and conversational", text)
        self.assertIn("calls to action", text)

    def test_the_other_safety_rules_are_untouched(self):
        text = compliance._L2_SYSTEM
        for needle in ("No investment advice", "No inducement", "never disparage a competitor", "SEBI/ASCI"):
            self.assertIn(needle, text)


class DashboardCitationTests(unittest.TestCase):
    def test_the_dashboard_hides_grounding_citations_like_slack_and_email_do(self):
        read_api = pytest.importorskip("community.api.read_api")
        row = {"id": 1, "insight": {}, "brand_reply": "Nubra offers digital KYC (f_57) today.",
               "rep_reply": "Margin shown upfront (f_65, f_71). (I work at Nubra)"}
        out = read_api._decorate_opportunity(row, {}, [])
        self.assertEqual(out["brand_reply"], "Nubra offers digital KYC today.")
        self.assertEqual(out["rep_reply"], "Margin shown upfront. (I work at Nubra)")

    def test_a_row_without_drafts_is_left_alone(self):
        read_api = pytest.importorskip("community.api.read_api")
        out = read_api._decorate_opportunity({"id": 2, "insight": {}, "brand_reply": None, "rep_reply": None}, {}, [])
        self.assertIsNone(out["brand_reply"])


if __name__ == "__main__":
    unittest.main()
