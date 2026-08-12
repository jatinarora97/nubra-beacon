# Instagram collector — build plan (2026-08-12, pre-build, awaiting polish)

_User-approved direction: Apify route, paid Starter plan active. Plan first →
polish → build. Companion: `instagram-apify-vs-meta-2026-08-11.md` (route
decision), `out/instagram-test/` (real extraction fixtures)._

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

Confirmed live: market.moves.matt · eliteoptionstrader2 · deepthinksfinance ·
stockswithmanveer · orderflowschool · stockburner_official · trademovesofficial ·
sjosephburns · spudnick_trading · **tastyliveshow** (user wrote "Tastylive" —
@tastylive is dead) · **spidersoftware** AND **spidersoftwareindia** both exist
(tiny engagement, 7–15 likes) — **user to pick one or both**.
**UNRESOLVED: `tycoontraders.in` — "Post does not exist"** (wrong handle,
private, or zero posts) — user to supply the correct handle.

- New `watch_sources` kind **`instagram_account`** (migration widens the CHECK,
  same as every other family); value = handle; Sources page add-form entry →
  **UI-managed additions like all other sources** (requirement 1).
- Seeded from registry like the rest; per-account `config` reserved for
  overrides (e.g. tier-bar multiplier, mute).

## 2 · Collection

- New `community/scrape/instagram.py` in the extra-sources pattern: registry
  `enabled` + `cadence: daily` (requirement 2 — runs in the 06:00 morning
  build; hourly runs log the skip), exception-bounded, stats into scrape
  summary + pipeline_state.
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
- Layout: `s3://<BUCKET>/nubra-beacon/instagram/<shortCode>/{video.mp4,
  display.jpg, slide-NN.jpg}`; S3 keys recorded in the item's `raw`.
- **OPEN: bucket name** — reuse the reports bucket from
  nubra-ai-personalization (same AWS account as ECR) with the
  `nubra-beacon/` prefix, or a dedicated bucket? User to confirm.
- Lifecycle rule: expire objects at **180 days** (retention-decision parity).
- Volume estimate: ~12 accts × ~3 posts/day × ~10MB ≈ 11GB/mo ≈ $0.25/mo.
- boto3 added to requirements; prod AWS creds already on the box (ECR).

## 4 · Tier 1 — reels → Hinglish transcript → Haiku parse (requirements 7)

- **Plan A**: Apify transcript actor (`crawlerbros/instagram-transcript-scraper`,
  ~$0.01/reel, same credit pool). **Hinglish validation is a build-step gate**:
  run it on 3 real Hindi-heavy reels (stockburner_official) and eyeball; if it
  garbles Hinglish → **Plan B**: local faster-whisper `small` (multilingual)
  reading video from S3 (ffmpeg + pinned model in the api image, $0/reel).
- Either way, one Haiku call parses the raw transcript into a compact
  structured summary (claims, tickers, brokers, stance) which is appended to
  the item text (`CAPTION: … | TRANSCRIPT: …`) → absence-based re-enrichment
  reprocesses it. Beacon features (trends/issues/feature-asks/Nubra mentions)
  see reel speech as ordinary text.
- **Gate**: per-account RELATIVE engagement (e.g. likes ≥ account's trailing
  median × 1.5 — sample spans 27→181k likes, one absolute bar cannot work) +
  `uses_original_audio: true` + not flagged noise at tier 0.

## 5 · Tier 2 — images/carousels → Haiku vision (requirement 6)

Gated image/carousel posts: up to 3 images from S3 → one Haiku vision call →
"ON-SCREEN:" summary appended (reads annotated charts/claims — interprets,
not OCR). ~$0.004/post.

## 6 · Comments depth (requirement 10 — answer)

`latestComments` is a **latest** sample (~10), NOT top-liked — that's what
comes free with each post result. Top-liked requires the separate
`apify~instagram-comment-scraper` actor (fetch ~30–50 comments incl. their
likesCount, sort ourselves, keep top 10; ~$2/1k comments). Plan: free latest
sample for every post; **top-liked comment expansion only for posts that pass
the tier gate or become opportunities** (same earn-the-expense principle).
Decision point: include in v1 or defer.

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
| Backfill 11–12 accts × 20 posts | ~$0.55 | — |
| Daily collection (onlyPostsNewerThan; ~30–50 genuinely new/day) | — | ~$2–4 |
| Transcripts (~3–5 gated reels/day @ $0.01) | — | ~$1–1.50 |
| Vision (~3–5 gated image posts/day) | — | ~$0.50 |
| Tier-0 enrichment (Haiku batch) | — | ~$1 |
| S3 storage (180d lifecycle) | — | ~$0.25 |
| **Total** | **<$1** | **≈ $5–7 of the $29 credits** |

## 9 · Build & test protocol

1. Build collector + migration + seeds + UI on `jatin/beacon-updates`.
2. Local testing on the FREE account (backfill a subset, ~$1 of its credits);
   full E2E: backfill → enrich → verify instagram items in Trends / Issues /
   Features / Voices / Explore (source filter + label) / heads-up.
3. Hinglish transcript validation gate (§4) before wiring tier 1.
4. Ship on the branch → prod release → prod `.env` gets paid APIFY_TOKEN →
   prod backfill runs in the next morning build.

## 10 · Decision points for polish (user input wanted)

1. `tycoontraders.in` correct handle? · spidersoftware vs spidersoftwareindia
   (or both)?
2. S3 bucket: reuse reports bucket + prefix, or dedicated?
3. Top-liked comment expansion in v1 or defer?
4. Backfill depth 20 ok? (15–20 asked; 20 ≈ $0.55 total)
5. Keep sjosephburns despite weak sample (0 videos, hashtag-spam captions)?
