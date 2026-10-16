# Reply drafting — how Reddit/X replies are written (context)

State of the code on 2026-10-15 (Twitter's own
prompt added; earlier sections written 2026-10-14). Line numbers drift; search for the names. Nothing here is committed policy
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
**`brand_reply IS NULL`** and not parked (see section 8), best priority first, at most `recommend.max_drafted`
(10) per run.

For each one the model is given:
- `NUBRA_FEATURES`: the current grounding catalog (`community/reference/features.py`, `catalog_for_prompt()`),
  edited on the UI's Grounding page. It decides which Nubra facts may be claimed, not the wording.
- `CONVERSATION`: `_thread_excerpt()`, up to 8 items / 1,500 characters of the thread (canonical items only).
- `MATCHED_INSIGHT`: why the opportunity was flagged.

## 4. The prompt

Prompts are chosen **per source** by `_system_for(source)` in `draft.py`:

- **Reddit** has its own plain-text file, `community/llm/prompts/reply_reddit.txt`. Editing it changes Reddit
  replies and nothing else. `{DISCLOSURE}` is the only placeholder (replaced by the `DISCLOSURE` sentence); the
  JSON shape at the end is what the parser reads, so keep it. The current file is the team's own prompt (style
  rules plus four example replies). A rules-based alternative, with no examples, is kept for comparison in
  `docs/reply-reddit-prompt-proposal-2026-10-14.txt`; it is not wired in.
- **Twitter (X)** has its own file, `community/llm/prompts/reply_twitter.txt`, added 2026-10-15 as a working
  template for the team to extend (voice rules, examples). It asks for one tweet (280 characters), the plain
  format, and the conditional affiliation line; it has no `{DISCLOSURE}` placeholder and asks for no fixed
  disclosure sentence. Add the team's own voice rules and example replies between VOICE and the JSON block.
- **Every other source** (Instagram, YouTube, forums, ...) uses `_DRAFT_SYSTEM` in `draft.py` (the constant
  `DISCLOSURE` is just above it), unchanged.
- `_SOURCE_PROMPTS` maps a source to its prompt file; add an entry and a file to give another source its own.
  A missing/unreadable file falls back to the default prompt and logs a warning.

It contains: hard rules (facts only from `NUBRA_FEATURES`, "coming soon" for upcoming features, no investment
advice, no competitor disparagement); the language line ("educational, factual, conversational", India
context, Hinglish if the thread is); the JSON output schema; and the two voices:
- **BRAND**: official Nubra voice, crisp, factual.
- **REP**: human persona, peer-to-peer, and it must include the disclosure sentence verbatim.

## 5. What happens after the model answers

Up to 3 attempts (initial + 2 regenerations, each told why the last one failed); then the drafts are dropped
(the opportunity is kept, undrafted, and the failed run is remembered: section 8).

1. `_validate_drafts(data, valid_ids, source)`: both texts non-empty and `features_cited` ids exist, then by source:
   - **Sources without their own prompt** (Instagram, YouTube, forums, ...): the rep text must contain the exact
     `DISCLOSURE` sentence.
   - **Sources with their own prompt (Reddit, Twitter)**: a short natural disclosure ("I work at Nubra", "I'm part of the
     team at Nubra", "I'm on the Nubra team", a Hinglish form) is **required whenever the rep reply names Nubra or
     cites a feature**, and a reply that never mentions Nubra needs none. A disclosure that says the opposite or is
     garbled ("part not of the team", "not affiliated with Nubra") is rejected as contradicting itself. Plain-voice
     rules apply to both voices: no bold markdown, links, emoji or hashtags, no marketing phrases ("check out",
     "seamless", ...). **Length is per source**: Reddit at most 200 words (rep) / 100 (brand); Twitter at most 280
     characters for both voices (one tweet), measured on the text the reader sees, so the hidden `(f_12)` grounding
     refs do not count. The tables are `REPLY_MAX_WORDS`, `REPLY_MAX_CHARS` and `_PLAIN_BANS` in `draft.py`; to let
     one source use something the plain voice bans (an emoji on X), remove that name from its `_PLAIN_BANS` entry.
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
  social-recommendation queues, not to `opportunities`. These are the cards on the **What to Make > Content**
  pages; a card whose brief is a `seed_reply` with a `seed_url` shows **"Target thread - post this reply there"**.
  - **X is a seed venue too (2026-10-15).** Fresh X posts (at most `X_SEED_MAX_AGE_DAYS` = 3 days old, a question
    or friction kind, with a url, not mentioning Nubra) are marked seedable, up to `X_SEED_EXTRA` = 8 of them, added
    on top of the normal evidence window so busy Reddit/forum threads cannot crowd them out. The model may then
    write a `seed_reply` into one of them; it is filed under platform `x`, must be one tweet (at most
    `X_REPLY_MAX_CHARS` = 280 characters in total) and carries no hashtags. Standalone X posts are unchanged.
  - A queue only generates the **shortfall** for the IST day (minimum 2 per platform, counted from briefs created
    today), so new X seed replies appear when X is below its minimum, normally from the first hourly compose after
    midnight IST.
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
- Prompt changes for Reddit and Twitter are isolated (`reply_reddit.txt`, `reply_twitter.txt`), but the
  **compliance judge is shared by every source** (and the plain-voice validator by every source that has its own
  prompt), so a style they reject still gets regenerated twice and dropped.
- **A run that ends without a draft is remembered** (migration 0025, `draft_attempts` / `draft_last_outcome` /
  `draft_attempted_at` on `opportunities`). Before it, a thread the model skipped, or whose three attempts all
  failed, kept `brand_reply` NULL and was selected again by every run (best priority first, 10 per run), so a few
  such threads could fill every slot each hour and starve better ones. Now:
  - **skipped** (the model returned `skip_reason`): parked, never retried automatically;
  - **dropped** (all attempts failed validation or compliance): retried no sooner than `RETRY_AFTER_HOURS` (24)
    later, and parked after `MAX_DRAFT_ATTEMPTS` (3) failed runs;
  - a transient error (the model API down) raises before anything is recorded and never counts against a thread;
  - a successful draft clears the outcome; re-scoring never touches these columns.
  A prompt that tells the model to skip some threads is therefore safe to use (the Twitter template has no such
  rule yet; add one if you want it). To reopen parked threads, for example after a prompt change:
  `UPDATE opportunities SET draft_attempts=0, draft_last_outcome=NULL, draft_attempted_at=NULL WHERE source='twitter'
  AND brand_reply IS NULL;`
  To see what is parked: `SELECT source, draft_last_outcome, count(*) FROM opportunities WHERE draft_last_outcome IS
  NOT NULL AND brand_reply IS NULL GROUP BY 1, 2;`
- Which source a card or draft belongs to is shown on the Opportunities page (badge, plus a source filter:
  `GET /opportunities?source=twitter`) and on the Overview's top actions.

## 9. Changing voice or tone

For Reddit edit `community/llm/prompts/reply_reddit.txt`; for Twitter `community/llm/prompts/reply_twitter.txt`;
for other sources edit `_DRAFT_SYSTEM` or give them a file via `_SOURCE_PROMPTS`. Keep three things consistent: the prompt, `_validate_drafts`, and the
`_L2_SYSTEM` tone line. Tests in `tests/test_draft_prompts.py` pin the isolation and the JSON contract.

Check a candidate text against the offline layer before spending any LLM calls:

```python
from community.recommend import compliance
compliance.l1_check(text)    # [] means it passes the regex layer
```

**Preview a prompt on real threads, saving nothing** (`scripts/preview_reddit_drafts.py`, logic in
`community/recommend/preview.py`; despite the file name it takes `--source`, Twitter below). It drafts a few real suggested opportunities of one source with the prompt the real
stage would use and shows the drafts plus the validator, regex-rule and (optionally) LLM-judge results. Nothing
is written to `opportunities` or `compliance_audit`; the only write is the normal LLM-usage meter row.

```bash
docker compose exec -T api python scripts/preview_reddit_drafts.py                 # 10 newest Reddit opportunities
docker compose exec -T api python scripts/preview_reddit_drafts.py --n 20 --judge  # more, + the LLM judge
docker compose exec -T api python scripts/preview_reddit_drafts.py --opp 12345     # one opportunity

# the same for Twitter / X (tweet prompt, 280-character rule):
docker compose exec -T api python scripts/preview_reddit_drafts.py --source twitter
docker compose cp reply_twitter.txt api:/tmp/reply_twitter.txt
docker compose exec -T api python scripts/preview_reddit_drafts.py --source twitter --prompt-file /tmp/reply_twitter.txt

# try an edited prompt BEFORE it ships (no image push):
docker compose cp reply_reddit.txt api:/tmp/reply_reddit.txt
docker compose exec -T api python scripts/preview_reddit_drafts.py --prompt-file /tmp/reply_reddit.txt
```

It costs one model call per thread (two more per thread with `--judge`).

## 10. Disclosure, as currently designed

A rep reply that mentions Nubra, its products or a comparison involving it carries a plain statement of the
connection. It is enforced in three places: the prompt, `_validate_drafts` and the L2 judge checklist ("a reply
that mentions Nubra ... must say in plain words that the writer is connected to Nubra; a reply that never
mentions Nubra needs no such line; a disclosure that contradicts itself or denies the connection is a
violation"). This is part of the compliance design for a SEBI-regulated broker (and of Reddit's and X's rules on
brand accounts); any change to it needs Nubra's compliance owner to sign off first. A reply that never mentions
Nubra has nothing to disclose; that is the route to "generic person" replies that stays consistent with the rule.

The `DISCLOSURE` constant in `draft.py` is the sentence the model is told to write verbatim (and, for sources
without their own prompt, the one the validator requires). It must be a true statement of the connection.
`tests/test_draft_reddit_rules.py::HouseDisclosureTests` fails if it ever denies it. The Twitter prompt does not
use the sentence at all.

## 11. Target voice (from the team's own examples)

Plain and direct; answer first; short paragraphs; empathy before advice; mirrors the thread's register
(English, Hinglish, lowercase and abbreviations when the thread uses them); no marketing words, calls to action
or links; competitors named neutrally and factually; no invented personal stories. Reference replies the team
supplied: the SIP / small-cap reply, the "lost 8L" reply (supportive, helpline, no product mention) and the
5% lower-circuit reply. All pass the L1 layer today. The replies that name Nubra (the phone-number reply and the
scalper reply) would need a disclosure or to drop the name.

## 12. Open decisions (from the proposal, not built)

- What the two drafts become on Reddit (the UI needs both filled).
- ~~Reddit only first, or X as well.~~ Decided 2026-10-15: X gets its own prompt too (template shipped).
- Whether to clear recent still-suggested Reddit drafts so they are redone in the new voice.
- Compliance owner's decision on the disclosure rule for replies that do not mention Nubra.
- **L2 judge wording vs the validator (found 2026-10-15).** The judge's affiliation line as committed in `45f2fa3`
  tells it that a rep reply which mentions Nubra "must never associate yourself with Nubra (for example there should
  not be 'I work at Nubra')". The validator for Reddit and Twitter requires the opposite (a disclosure whenever Nubra
  is named or a feature is cited). A rep reply that names Nubra cannot satisfy both, so it is regenerated twice and
  dropped; only replies that never mention Nubra get through. `tests/test_draft_reddit_rules.py::JudgeTests::
  test_the_judge_treats_a_contradicting_disclosure_as_a_violation` fails against that wording. Decision needed from
  the team and the compliance owner; nothing was changed.
