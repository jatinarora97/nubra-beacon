# Reply drafting — how Reddit/X replies are written (context)

State of the code on 2026-10-14. Line numbers drift; search for the names. Nothing here is committed policy
beyond what the code does today.

## 1. What it is

An LLM writes a suggested **reply for a thread worth engaging in** (an *opportunity*): one `brand` draft and one
`rep` draft per opportunity. **Humans post them; the system never posts.** The drafts are stored on the
opportunity and shown in the dashboard, the daily roundup and the heads-ups.

## 2. Where it sits

`./cm run-local` runs the stages in this order (`STAGE_MODULES` in `runner.py`):
scrape -> clean -> enrich -> aggregate -> **score** (creates/prioritises opportunities) -> **draft** (this) ->
social -> compose -> dispatch. Run it alone with `./cm stage draft`.

- Code: `community/recommend/draft.py` (`run()` at the bottom).
- Models: `settings.draft_model`, Sonnet by default (env `DRAFT_MODEL`, `community/config/settings.py`). The
  compliance judge uses the same model.

## 3. What goes in

`run()` selects opportunities with `status='suggested'`, `priority >= recommend.thresholds.secondary` (40),
**`brand_reply IS NULL`**, best priority first, at most `recommend.max_drafted` (10) per run.

For each one the model is given:
- `NUBRA_FEATURES`: the current grounding catalog (`community/reference/features.py`, `catalog_for_prompt()`),
  edited on the UI's Grounding page. It decides which Nubra facts may be claimed, not the wording.
- `CONVERSATION`: `_thread_excerpt()`, up to 8 items / 1,500 characters of the thread (canonical items only).
- `MATCHED_INSIGHT`: why the opportunity was flagged.

## 4. The prompt

Prompts are chosen **per source** by `_system_for(source)` in `draft.py`:

- **Reddit** has its own plain-text file, `community/llm/prompts/reply_reddit.txt`. Editing it changes Reddit
  replies and nothing else. `{DISCLOSURE}` is the only placeholder (replaced by the `DISCLOSURE` sentence); the
  JSON shape at the end is what the parser reads, so keep it. Today its text is identical to the default below.
- **Every other source** (X included) uses `_DRAFT_SYSTEM` in `draft.py` (the constant `DISCLOSURE` is just above
  it), unchanged.
- `_SOURCE_PROMPTS` maps a source to its prompt file; add an entry and a file to give another source its own.
  A missing/unreadable file falls back to the default prompt and logs a warning.

It contains: hard rules (facts only from `NUBRA_FEATURES`, "coming soon" for upcoming features, no investment
advice, no competitor disparagement); the language line ("educational, factual, conversational", India
context, Hinglish if the thread is); the JSON output schema; and the two voices:
- **BRAND**: official Nubra voice, crisp, factual.
- **REP**: human persona, peer-to-peer, and it must include the disclosure sentence verbatim.

## 5. What happens after the model answers

Up to 3 attempts (initial + 2 regenerations, each told why the last one failed); then the drafts are dropped
(the opportunity is kept, undrafted).

1. `_validate_drafts()`: both texts non-empty, `features_cited` ids exist, and the **rep text contains
   the `DISCLOSURE` sentence**.
2. `compliance.check()` (`community/recommend/compliance.py`), per voice:
   - **L1 regex** (`_L1_RULES`: guaranteed returns, tips, targets/stop-loss numbers, "sure shot", PII, shaming a
     named broker) plus the vendored `community/lib/comms_guardrails/*` (fear phrases, buy/sell call patterns,
     crypto). Deterministic, offline.
   - **L2 LLM judge** (`_L2_SYSTEM`): checklist of no advice, no inducement, no unsubstantiated claims, fair
     comparisons, **representative replies must disclose Nubra affiliation**, and the tone line.
   - Every draft x layer is written to the `compliance_audit` table.
3. Pass -> `UPDATE opportunities SET brand_reply, rep_reply, recommended_timing`.

Cost per opportunity: up to 3 attempts x (1 draft call + 2 judge calls) on Sonnet.

## 6. Where drafts show up

`opportunities.brand_reply`, `.rep_reply`, `.recommended_timing`. Read by `community/compose/roundup.py` and
`render.py` (templates `roundup_daily_md.j2`, `headsup_md.j2`), `community/api/read_api.py` (dashboard) and
`community/api/beacon_api.py`. Several queries filter on `brand_reply IS NOT NULL`, so **both fields must be
filled** for a draft to count.

## 7. Two other things write reply-like copy

- **API lens** (`community/social_recommend/api_lens.py`, `_SYSTEM`): ready-to-post content for API/algo traders,
  including `seed_reply` into Reddit/forum threads. It already has Reddit-specific norms (plain text, no
  hashtags, no marketing tone) and its own disclosure wording ("I work at Nubra"). Output goes to the
  social-recommendation queues, not to `opportunities`.
- `community/social_recommend/service.py` (`SYSTEM_PROMPT`): general marketing queue, not replies.
- Content briefs (`draft.py:_content_proposals`, `community/recommend/revise.py`) are creator briefs, a different
  product from replies.

## 8. Things that surprise people

- **Existing drafts never change.** A draft is written once (`brand_reply IS NULL` is the "not drafted" test).
  Editing the prompt only affects opportunities drafted afterwards. Re-drafting old ones means clearing their
  stored replies first, and each one costs Sonnet calls.
- **Prompt, validator and judge must agree.** A style the prompt asks for but the validator or judge rejects is
  regenerated twice and then dropped, so the failure shows up as missing drafts, not as odd text.
- **Prompts are code**, baked into the image: a change needs a push. There is no `.env` switch for them.
- `community/lib/comms_guardrails/*` is vendored: never hand-edit, refresh with `scripts/sync_*.py`.
- Prompt changes for Reddit are isolated (`reply_reddit.txt`), but the **validator and the compliance judge are
  shared by every source**, so a Reddit style they reject still gets regenerated twice and dropped.

## 9. Changing voice or tone

For Reddit edit `community/llm/prompts/reply_reddit.txt`; for other sources edit `_DRAFT_SYSTEM` or give them
a file via `_SOURCE_PROMPTS`. Keep three things consistent: the prompt, `_validate_drafts`, and the
`_L2_SYSTEM` tone line. Tests in `tests/test_draft_prompts.py` pin the isolation and the JSON contract.

Check a candidate text against the offline layer before spending any LLM calls:

```python
from community.recommend import compliance
compliance.l1_check(text)    # [] means it passes the regex layer
```

**Preview a prompt on real threads, saving nothing** (`scripts/preview_reddit_drafts.py`, logic in
`community/recommend/preview.py`). It drafts a few real suggested Reddit opportunities with the prompt the real
stage would use and shows the drafts plus the validator, regex-rule and (optionally) LLM-judge results. Nothing
is written to `opportunities` or `compliance_audit`; the only write is the normal LLM-usage meter row.

```bash
docker compose exec -T api python scripts/preview_reddit_drafts.py                 # 10 newest Reddit opportunities
docker compose exec -T api python scripts/preview_reddit_drafts.py --n 20 --judge  # more, + the LLM judge
docker compose exec -T api python scripts/preview_reddit_drafts.py --opp 12345     # one opportunity

# try an edited prompt BEFORE it ships (no image push):
docker compose cp reply_reddit.txt api:/tmp/reply_reddit.txt
docker compose exec -T api python scripts/preview_reddit_drafts.py --prompt-file /tmp/reply_reddit.txt
```

It costs one model call per thread (two more per thread with `--judge`).

## 10. Disclosure, as currently designed

Rep replies carry an affiliation disclosure. It is enforced in three places: the prompt, `_validate_drafts`, and
the L2 judge checklist. This is part of the compliance design for a SEBI-regulated broker (and of Reddit's and
X's rules on brand accounts), so any change to it needs Nubra's compliance owner to sign off first. A reply
that does not mention Nubra, its products or comparisons involving it has nothing to disclose; that is the
route to "generic person" replies that stays consistent with the rule.

## 11. Target voice (from the team's own examples)

Plain and direct; answer first; short paragraphs; empathy before advice; mirrors the thread's register
(English, Hinglish, lowercase and abbreviations when the thread uses them); no marketing words, calls to action
or links; competitors named neutrally and factually; no invented personal stories. Reference replies the team
supplied: the SIP / small-cap reply, the "lost 8L" reply (supportive, helpline, no product mention) and the
5% lower-circuit reply. All pass the L1 layer today. The replies that name Nubra (the phone-number reply and the
scalper reply) would need a disclosure or to drop the name.

## 12. Open decisions (from the proposal, not built)

- What the two drafts become on Reddit (the UI needs both filled).
- Reddit only first, or X as well.
- Whether to clear recent still-suggested Reddit drafts so they are redone in the new voice.
- Compliance owner's decision on the disclosure rule for replies that do not mention Nubra.
