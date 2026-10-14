"""Reply-draft preview: run a prompt on real threads and show the drafts and the checks, saving nothing."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from community.recommend import draft, preview

OPP = {"id": 7, "source": "reddit", "thread_id": "t3_x", "priority": 80, "matched_insight": {"kind": "complaint"},
       "url": "https://www.reddit.com/r/IndianStockMarket/comments/x/", "title": "Why is my order stuck?"}
CATALOG = [{"id": "f_1"}]


def answer(rep=None, brand="A plain factual reply.", skip=None, rep_cited=("f_1",)):
    rep = rep if rep is not None else "A peer reply. (I work at Nubra)"
    return json.dumps({"brand": {"text": brand, "features_cited": ["f_1"]},
                       "rep": {"text": rep, "features_cited": list(rep_cited), "disclosure_included": True},
                       "skip_reason": skip})


def run(raw, *, judge=False, system="SYSTEM"):
    with patch.object(preview, "complete", return_value=(raw, {})) as llm, \
         patch.object(draft, "_thread_excerpt", return_value="- a thread"), \
         patch.object(preview.compliance, "l2_check", return_value=(True, [])) as l2:
        result = preview.preview_one(OPP, CATALOG, system, judge=judge)
    return result, llm, l2


class UserMessageTests(unittest.TestCase):
    def test_the_message_has_the_catalog_the_thread_and_the_insight(self):
        with patch.object(draft, "_thread_excerpt", return_value="- first post"):
            text = draft._user_message(OPP, CATALOG)
        for needle in ("NUBRA_FEATURES", '"f_1"', "CONVERSATION", "- first post", "MATCHED_INSIGHT", "complaint", "TASK"):
            self.assertIn(needle, text)


class PreviewOneTests(unittest.TestCase):
    def test_it_sends_the_given_prompt_and_the_same_message_the_real_stage_builds(self):
        _, llm, _ = run(answer(), system="MY PROMPT")
        with patch.object(draft, "_thread_excerpt", return_value="- a thread"):
            expected = draft._user_message(OPP, CATALOG)
        self.assertEqual(llm.call_args.args[1], "MY PROMPT")
        self.assertEqual(llm.call_args.args[2], expected)

    def test_a_good_draft_comes_back_with_no_problems(self):
        r, _, _ = run(answer())
        self.assertEqual(r["drafts"]["brand"], "A plain factual reply.")
        self.assertEqual(r["problems"], [])
        self.assertEqual(r["l1"], {"brand": [], "rep": []})

    def test_the_real_validator_decides_what_counts_as_a_problem(self):
        r, _, _ = run(answer(rep="Nubra shows max loss before you place the order."))
        self.assertTrue(any("without a disclosure" in p for p in r["problems"]), r["problems"])

    def test_a_reddit_reply_with_no_nubra_mention_is_clean_without_a_disclosure(self):
        r, _, _ = run(answer(rep="A peer reply with no product mention at all.", rep_cited=()))
        self.assertEqual(r["problems"], [])

    def test_other_sources_are_judged_by_their_own_rule(self):
        with patch.object(preview, "complete", return_value=(answer(rep="A reply, no disclosure."), {})), \
             patch.object(draft, "_thread_excerpt", return_value="- a thread"):
            r = preview.preview_one({**OPP, "source": "twitter"}, CATALOG, "SYSTEM")
        self.assertIn("rep: disclosure line missing", r["problems"])

    def test_feature_citations_are_hidden_in_the_rendered_preview_like_in_production(self):
        r, _, _ = run(answer(brand="Nubra offers digital KYC (f_57) today."))
        self.assertNotIn("(f_57)", preview.render([r], "x"))

    def test_regex_rule_hits_are_shown_per_voice(self):
        r, _, _ = run(answer(brand="This one has guaranteed returns on every trade."))
        self.assertTrue(r["l1"]["brand"])
        self.assertEqual(r["l1"]["rep"], [])

    def test_the_llm_judge_runs_only_when_asked(self):
        _, _, l2 = run(answer(), judge=False)
        l2.assert_not_called()
        r, _, l2 = run(answer(), judge=True)
        self.assertEqual(l2.call_count, 2)
        self.assertEqual(r["l2"], {"brand": (True, []), "rep": (True, [])})

    def test_unparsable_output_and_skips_are_reported_not_raised(self):
        r, _, _ = run("sorry, I cannot do that")
        self.assertIn("not valid JSON", r["error"])
        r, _, _ = run(answer(skip="thread is a meme"))
        self.assertEqual(r["skipped"], "thread is a meme")

    def test_nothing_is_saved_and_no_audit_row_is_written(self):
        with patch("community.store.db.execute", side_effect=AssertionError("preview wrote to the DB")), \
             patch.object(preview.compliance, "check", side_effect=AssertionError("audited check was called")):
            r, _, _ = run(answer(), judge=True)
        self.assertEqual(r["problems"], [])


class PromptChoiceTests(unittest.TestCase):
    def test_by_default_it_uses_the_prompt_the_real_stage_would(self):
        self.assertEqual(preview.system_prompt("reddit"), draft._system_for("reddit"))
        self.assertEqual(preview.system_prompt("twitter"), draft._DRAFT_SYSTEM)

    def test_a_prompt_file_overrides_it_so_an_edit_can_be_tried_before_it_ships(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "try.txt"
            path.write_text("TRIAL PROMPT {DISCLOSURE}", encoding="utf-8")
            self.assertEqual(preview.system_prompt("reddit", str(path)), "TRIAL PROMPT " + draft.DISCLOSURE)


class PickTests(unittest.TestCase):
    def test_the_default_is_what_one_hourly_draft_run_handles(self):
        self.assertEqual(preview.DEFAULT_COUNT, 10)
        with patch.object(preview.db, "query", return_value=[]) as q:
            preview.pick("reddit")
        self.assertEqual(q.call_args.args[1], ("reddit", preview.DEFAULT_COUNT))

    def test_it_reads_recent_suggested_opportunities_of_one_source(self):
        with patch.object(preview.db, "query", return_value=[OPP]) as q:
            self.assertEqual(preview.pick("reddit", 3), [OPP])
        sql, params = q.call_args.args
        self.assertIn("o.source = %s", sql)
        self.assertIn("status = 'suggested'", sql)
        self.assertEqual(params, ("reddit", 3))

    def test_one_specific_opportunity_can_be_chosen(self):
        with patch.object(preview.db, "query", return_value=[OPP]) as q:
            preview.pick("reddit", 3, opp_id=7)
        sql, params = q.call_args.args
        self.assertIn("o.id = %s", sql)
        self.assertEqual(params, ("reddit", 7, 3))


class RenderTests(unittest.TestCase):
    def test_the_text_says_nothing_was_saved_and_shows_drafts_and_checks(self):
        r, _, _ = run(answer(rep="Nubra shows max loss before you place the order."), judge=True)
        text = preview.render([r], "reply_reddit.txt")
        for needle in ("PREVIEW ONLY", "nothing was saved", "reply_reddit.txt", OPP["url"], "BRAND", "REP",
                       "A plain factual reply.", "without a disclosure", "judge"):
            self.assertIn(needle, text)

    def test_errors_and_skips_render_too(self):
        err, _, _ = run("nope")
        skip, _, _ = run(answer(skip="meme"))
        text = preview.render([err, skip], "x")
        self.assertIn("not valid JSON", text)
        self.assertIn("skipped: meme", text)


if __name__ == "__main__":
    unittest.main()
