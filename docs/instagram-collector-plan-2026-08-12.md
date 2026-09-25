# Instagram collector — build plan (2026-08-12, POC DONE — build next)

_All §10 decision points answered by user 2026-08-12 (inlined below). POC ran
2026-08-12 on real posts (free account, $0.53) — verdicts in §11 and folded
into §2/§4/§6 below. Companion: `instagram-apify-vs-meta-2026-08-11.md`
(route decision), `out/instagram-test/` (extraction fixtures),
`out/instagram-poc/` (POC artifacts)._

## 0 · Accounts & environments

- **Prod Apify**: paid Starter $29/mo (user `euvGWlQ5a8MfB9zNe`), rate
  $0.0023/result, ~12,600 results/mo credits. Token in prod `.env` as
  `APIFY_TOKEN`.
- **Local Apify**: original free account ($5/mo credits) for build/testing;
  switch local `.env` to the paid token only when free credits run dry.
  Both tokens stored in local `.env` (active + commented alternate).
- Both tokens were shared in chat → rotate both at the next key-rotation pass
  (list also includes YouTube/GitHub keys).

## 1 · Watch targets (verified 2026-08-12, free-account probe)

FINAL LIST (11, user-confirmed): market.moves.matt · eliteoptionstrader2 ·
deepthinksfinance · stockswithmanveer · orderflowschool · stockburner_official ·
trademovesofficial · sjosephburns (kept despite weak sample — user call) ·
spudnick_trading · **tastyliveshow** · **spidersoftware**.
DROPPED: tycoontraders.in (unresolvable — user: let it be) ·
spidersoftwareindia (spidersoftware chosen).

- New `watch_sources` kind **`instagram_account`** (migration widens the CHECK,
  same as every other family); value = handle; Sources page add-form entry →
  **UI-managed additions like all other sources** (requirement 1).
- Seeded from registry like the rest; per-account `config` reserved for
  overrides (e.g. tier-bar multiplier, mute).

## 2 · Collection

- New `community/scrape/instagram.py` in the extra-sources pattern: registry
  `enabled`, exception-bounded, stats into scrape summary + pipeline_state.
- **Cadence: DAILY (POC-measured, 2026-08-12 — supersedes the hourly hope).**
  The hourly plan depended on empty polls being free; the POC disproved it:
  `onlyPostsNewerThan=<tomorrow>` on stockswithmanveer still returned that
  account's 3 PINNED posts (2024–2025 timestamps) and billed $0.0054. Pinned
  posts bypass the date filter, so every poll bills ~3 rows/account
  regardless: hourly ≈ 11 accts × ~3 pinned × 24 × 30 × $0.0023 ≈ **$55/mo of
  waste vs the $29 pool**. Daily ≈ $2.3/mo; every-4-hours ≈ $14/mo (upgrade
  knob if daily proves too slow). `cadence` stays a registry knob. Dedup by
  shortCode makes the re-returned pinned rows harmless data-wise.
  **Watermark guard**: advance the per-source watermark from NON-pinned posts
  only (pinned rows carry 2024-era timestamps; the existing GREATEST guard
  prevents regression, but never treat a pinned row as "newest").
- **Out of scope v1 (explicit)**: Stories and highlights (not returned by the
  posts route), hashtag discovery (proven dry), follower-count tracking.
- One actor run per cycle: all active handles as directUrls,
  `apify~instagram-scraper`, posts route (hashtags proven dry).
- **Backfill (requirement 3)**: an account with zero stored items fetches
  `resultsLimit: 20`; steady-state fetches use `onlyPostsNewerThan` (actor
  input) pinned to the source watermark so we are NOT billed for re-returned
  old posts — verify this param during build; fallback = resultsLimit 5.
- Mapping (fixtures in out/instagram-test/): shortCode→external_id,
  type→source_type reel|post|sidecar, caption+hashtags→text, permalink→url
  (requirement 9), likes+comments→unified_score with plays/views kept in raw,
  owner→author (→ Voices with instagram profile URLs); each latestComments
  entry → child comment item (parent_id = post).
- **Skips (requirement 8)**: `paidPartnership`/`isSponsored` → skip with
  counter; small caption deny-list (giveaway/discount-code/link-in-bio-course
  patterns) in registry; everything else flows to the existing noise
  classifier (Haiku already tags off-topic as noise — that's the designed
  relevance filter, don't duplicate it).

## 3 · Media persistence — S3 (requirement 5, user decision: S3 over VM disk)

Agreed: S3. Reasons: CDN URLs expire in hours (must download at fetch), VM
disk stays small, **pre-signed URLs** later power both the transcribe layer
and possible dashboard playback.

- Download at fetch time: video (reels) + displayUrl + carousel child images.
- Layout (user decision — creator-first, media-type folders):
  `s3://<REPORTS_BUCKET>/nubra_beacon/instagram/<creator>/reels/<shortCode>.mp4`
  and `.../<creator>/images/<shortCode>[-NN].jpg`; S3 keys in the item `raw`.
- Bucket: **same reports bucket as nubra-ai-personalization** (user decision;
  same AWS account as ECR — get exact bucket name from that repo's config
  during build).
- Lifecycle rule: expire objects at **180 days** (retention-decision parity).
- Volume estimate: ~12 accts × ~3 posts/day × ~10MB ≈ 11GB/mo ≈ $0.25/mo.
- boto3 added to requirements; prod AWS creds already on the box (ECR).

## 4 · Tier 1 — reels → Hinglish transcript → Haiku parse (requirements 7)

- **Plan A REJECTED, Plan B ADOPTED (POC, 2026-08-12).** The Apify transcript
  actor failed on a real 80.5s stockburner reel three ways: whisper mode OOM'd
  at 1GB; at 4GB it downloaded+loaded in 20s then spent 9+ min transcribing
  and hit the 600s timeout (compute-billed ~$0.23/attempt, ~$0.55 total, zero
  output — nothing like the advertised ~$0.01/reel); `native` captions mode
  returned an empty string.
- **Local whisper settings (completeness experiments, 2026-08-12 round 2 —
  user flagged the first transcript as incomplete):** `vad_filter=True` DROPS
  real speech (539 chars with gaps) — always use `vad_filter=False,
  condition_on_previous_text=False`. Model/task matrix on the same reel:
  `small` hi = garbled (reject) · `large-v3-turbo` hi no-VAD = 63s, 723 chars,
  full 0–80.3s coverage but compressed · **`large-v3` int8 `task=translate`
  (direct English) = 97s, 1,448 chars, full coverage, RICHEST detail**
  (deepfake-AI ads, the Dinesh Kirola disclaimer, "we take no money / give no
  financial advice", report-to-cyber-crime — details every Hindi variant
  missed). Whisper's English translate path is more robust on Hinglish than
  its Devanagari transcription, and enrichment consumes English natively.
  **LOCKED (user, 2026-08-12): faster-whisper `large-v3` int8,
  task=translate, `language=None` (auto-detect), `vad_filter=False`,
  `condition_on_previous_text=False`** (~1.6GB model + ffmpeg in the api
  image — its own docker layer, so it re-downloads only when the model
  changes, not every release; ~1.5–4 min/reel on CPU, $0/reel; turbo-hi +
  Haiku English rendering ($0.002/reel) is the fallback if prod CPU is too
  slow). Reads video from S3.
  **Mixed-language handling VERIFIED (2026-08-12)**: `language=None` +
  `task=translate` is one code path for everything — English tastyliveshow
  reel detected `en` p=1.00 and produced a clean 2,187-char English transcript
  (translate degenerates to plain transcription, no quality loss, 135s for a
  117s reel); Hindi stockburner reel detected `hi` p=0.94 and produced the
  same 1,448-char English translation as the forced-hi run. Store
  `info.language` + `language_probability` in item `raw` for observability.
- **Lightweight alternatives benchmarked (2026-08-12, user ask):**
  whisper.cpp v1.9.2 large-v3 q5_0, CPU-only (`-ng`), translate, same reel =
  **192s vs faster-whisper's 97s** at equal quality/completeness (all key
  details present; slightly smaller model file, 1.08 vs ~1.5GB). CTranslate2
  int8 is simply the faster CPU engine, and pip-install beats compiling C++
  into the image. WhisperX rejected without testing: it wraps faster-whisper
  and ADDS VAD chunking (proven to drop speech on these reels) + diarization
  we don't need; its speedups are GPU-batching. Scriberr rejected: a web app
  wrapping these same engines — wrong shape for a pipeline stage. Verdict:
  faster-whisper stands; whisper.cpp is the named fallback if the Python dep
  ever becomes a problem.
- Either way, one Haiku call parses the raw transcript into a compact
  structured summary (claims, tickers, brokers, stance) which is appended to
  the item text (`CAPTION: … | TRANSCRIPT: …`) → absence-based re-enrichment
  reprocesses it. Beacon features (trends/issues/feature-asks/Nubra mentions)
  see reel speech as ordinary text.
- **Gate**: per-account RELATIVE engagement (e.g. likes ≥ account's trailing
  median × 1.5 — sample spans 27→181k likes, one absolute bar cannot work) +
  `uses_original_audio: true` + not flagged noise at tier 0 + **duration cap:
  skip (or transcribe only the first N minutes of) videos > 5 min** — CPU
  time scales with duration and long IGTV-style videos would stall the run.
- **Run-safety details (build requirements, added at finalization)**:
  (a) mark each item `raw.transcript_attempted=true` even on failure so
  absence-based re-enrichment never loops retrying a broken video;
  (b) empty/whitespace transcript (music-only reels) → skip the append, don't
  feed enrichment an empty TRANSCRIPT block; (c) whisper hallucinates short
  junk on music-only tails ("See you", repeats) — drop trailing segments with
  high `no_speech_prob`; (d) transcribe gated reels SEQUENTIALLY (one model
  instance, ~2–3GB RAM while active) — never parallel-load whisper on the
  prod box; (e) all timings above are from the dev Mac — **step 3 of §9
  includes a one-reel timing + RAM check on the prod box** before declaring
  tier 1 live (fallback knob: registry `whisper_model: large-v3-turbo`).

## 5 · Tier 2 — images/carousels → Haiku vision (requirement 6)

Gated image/carousel posts: images from S3 → one Haiku vision call →
"ON-SCREEN:" summary appended (reads annotated charts/claims — interprets,
not OCR). Measured $0.004/post at 2 slides.
**PROPOSED at finalization (was "up to 3 images")**: send ALL slides up to
10 — finance educational carousels routinely run 6–10 slides and the content
IS the later slides; marginal cost ~$0.0015/extra slide (~$0.015 worst case).
Cap 10 = Instagram's own carousel limit.

## 6 · Comments depth (requirement 10 — answer)

`latestComments` is a **latest** sample (~10), NOT top-liked. **User decision:
IN v1** — the separate `apify~instagram-comment-scraper` actor fetches
comments incl. likesCount per gated post; we sort and keep the **top 10 liked**
as child items (marked `raw.top_liked=true`; the free latest-sample still
covers ungated posts). **POC verdict (2026-08-12): works** — likesCount
present and sortable; top comment on the test reel was literally "which app
should I use for trading in India" (the opportunity signal in person). Caveat:
it returned 15 comments despite `resultsLimit: 50` on a 2,161-comment post —
during build, probe pagination params (includeNestedComments etc.); if 15ish
is the practical page, top-10-of-15-recent is still acceptable for v1.

## 7 · Health & observability (requirement 4)

- Source-health page: `instagram` row (config/cadence/last-run/stored counts)
  + live probe = Apify `/users/me/limits` with the token → shows **credits
  used vs plan** live (the user's earlier billing-visibility ask, answered
  in-product).
- `./cm doctor`: instagram check (token valid + credits remaining).
- Apify per-run cost (`usageTotalUsd` from the runs API) recorded into scrape
  stats → visible in ops summary alongside llm_usage.

## 8 · Costs (paid tier, $0.0023/result)

| Item | One-time | Monthly |
|---|---|---|
| Backfill 11 accts × 20 posts | ~$0.51 | — |
| Daily collection (incl. re-billed pinned rows) | — | ~$2.5–4.5 |
| Transcripts (local faster-whisper large-v3 int8, translate) | — | **$0** |
| Vision (~3–5 gated image posts/day, measured $0.004/post) | — | ~$0.50 |
| Tier-0 enrichment (Haiku batch, measured ~$0.002/item) | — | ~$1 |
| Top-10 comments actor (gated posts) | — | ~$0.50 |
| S3 storage (180d lifecycle) | — | ~$0.25 |
| **Total** | **<$1** | **≈ $5–7 of the $29 credits** |

## 9 · Build & test protocol (updated with user decisions)

0. **POC — DONE 2026-08-12** (free account, $0.53 + round-2 experiments
   ~$0.05; artifacts in `out/instagram-poc/`; verdicts in §11): transcript
   actor rejected → local faster-whisper large-v3 translate LOCKED (whisper.cpp
   benchmarked 2× slower, WhisperX/Scriberr rejected on architecture); comment
   scraper works; hourly cadence killed by pinned-post billing → daily.
1. Build collector + migration + seeds + UI on `jatin/beacon-updates`.
   **DONE 2026-08-12**: migration 0013 · `community/scrape/instagram.py`
   (collector + tiers) + `instagram_av.py` (S3/whisper/vision) · extra_sources
   wiring (tiers run after storage, isolated) · registry `sources.instagram` ·
   seed_sources · doctor + live probe (Apify credits in-product) ·
   source-health/read-API rows · Sources UI kind · env.example ·
   `scripts/backfill_instagram.py` · Dockerfile model layer.
   E2E findings folded back: `raw || %s::jsonb` casts;
   **uses_original_audio demoted from gate to signal** (stockburner speaks
   over a licensed track and carries `false` — whisper's empty-transcript
   path is the arbiter for music-only reels).
2. Local E2E on the FREE account: backfill subset → enrich → verify instagram
   items in Trends / Issues / Features / Voices / Explore / heads-up.
   **DONE 2026-08-12** (2 accounts × 3 posts, 53 items + 18 top-liked
   comments, ~$0.11): transcript appended + re-enriched (detected hi p=0.94),
   vision ON-SCREEN appended, gates verified live, doctor PASS with credits
   detail, docker double-build proof — model layer `CACHED` after a
   code-only change (user's layer-cache requirement).
3. Ship on the branch → prod release → prod `.env` gets the paid APIFY_TOKEN.
   **Prod acceptance gate**: one-reel whisper timing + RAM check on the prod
   box (all POC timings are dev-Mac; registry `whisper_model` knob drops to
   `large-v3-turbo` if the box is too slow) + doctor green + first daily
   cycle observed end-to-end in the cron log.
4. **Prod backfill = explicit script (user requirement)**:
   `scripts/backfill_instagram.py` — runs the collector in backfill mode
   (20/account) + optional gated transcript/comment expansion; user runs
   `docker compose exec api python scripts/backfill_instagram.py` once after
   release; idempotent (insert-if-absent), safe to re-run.

## 10 · Decisions — ALL RESOLVED (user, 2026-08-12)

1. tycoontraders.in dropped; spidersoftware + tastyliveshow in. 2. Same
reports bucket, creator-first layout with reels/ images/ folders. 3. Top-liked
comments IN v1 via the comment-scraper actor (top 10 kept), POC first.
4. Backfill 20 confirmed. 5. sjosephburns kept. 6. Cadence: hourly with
new-post detection (POC verifies empty-run economics; registry knob as the
fallback) — **superseded by POC measurement → DAILY (§2)**. 7. Both add-on
actors (transcriber + comment fetcher) POC'd locally on real posts before
wiring. 8. **Transcriber LOCKED (user, 2026-08-12 round 2): faster-whisper
`large-v3` int8, task=translate, language auto-detect, no VAD** (§4 —
verified on Hindi and English reels; whisper.cpp/WhisperX/Scriberr evaluated
and rejected).

### Final confirmations — ALL RESOLVED (user, 2026-08-12 round 2). PLAN CLOSED.

A. **Cadence = daily** — confirmed ("since we couldn't resolve the pinned
   posts"). Daily also removes the prod-CPU worry: a full day to process
   reels sequentially, updating Beacon as each finishes.
B. **Comments v1 = top 10** — confirmed.
C. **Carousel slides = ALL (≤10)** — confirmed.
D. **Long videos**: cap at 5–6 min — confirmed ("reels aren't generally more
   than 5 minutes").
E. **Transcription retry (user-specified)**: 3 attempts; persist the last
   completed segment END TIMESTAMP + partial text in `raw`, and resume from
   that offset (ffmpeg `-ss <offset>`) instead of restarting from zero.
F. **Music-only/no-audio reels = DOCUMENTED LIMITATION** (user): nothing to
   transcribe — caption + vision on the keyframe still flow; tier 1 skips.
   Trailing-hallucination fix (drop high `no_speech_prob` tail segments) =
   delegated, implemented.
G. **Pinned posts (delegated)**: actor marks them `isPinned: true`
   (verified on real output) → steady-state runs skip already-stored pinned
   rows and NEVER advance the watermark from an `isPinned` row; backfill
   ingests them once like any post.
H. **Docker model layer (user: HIGHLY IMPORTANT)**: the whisper model must
   live in an image layer BEFORE the code COPY so `RELEASE_TAG=… make
   push-prod` for code changes never re-downloads/re-uploads/re-pulls the
   ~1.6GB model layer. Verify buildx layer-cache behavior in OUR Makefile
   flow as a build step (docker-container driver may need explicit
   cache-from/cache-to).

## 11 · POC results (2026-08-12, free account, $0.53 — artifacts `out/instagram-poc/`)

End-to-end on two real specimens: reel `DJJFNA-BV7f` (stockburner_official,
91,676 likes, 2.9M plays, Hindi scam-warning) and carousel `DBwcUqUoH4f`
(stockswithmanveer, 2 slides, 6,247 likes).

1. **Reel pipeline PROVEN, with a route change.** Apify transcript actor
   rejected (3 failure modes, §4); local whisper adopted — round-2
   experiments settled the final config on **`large-v3` int8 translate**
   (§4 matrix; `small` garbled, turbo compressed, VAD dropped speech).
   Transcript → real `enrich_batch` produced
   `topic_key: trading_scams`, sentiment -0.8, correct summary — Instagram
   speech behaves exactly like a tweet in the pipeline, zero new machinery.
2. **Carousel pipeline PROVEN**: fresh-fetch (fixture CDN URLs were expired —
   confirms download-at-fetch) → 2 slides → one Haiku vision call ($0.004,
   3,109 in/174 out) → honest ON-SCREEN summary (correctly reported "no
   financial claims" on a personal-story carousel — the noise filter working)
   → `enrich_batch` tagged influencer/news_opinion/`other:` topic, not noise.
3. **Top-10 comments PROVEN** with a pagination caveat (§6). The top comment
   was a user asking which trading app to use in India.
4. **Hourly cadence KILLED by measurement**: pinned posts bypass
   `onlyPostsNewerThan` and re-bill every poll (§2) → **daily** cadence.
5. Measured unit costs: scraper $0.0018–0.0027/result · vision $0.004/post ·
   enrichment ~$0.002/item · transcript $0 local.
