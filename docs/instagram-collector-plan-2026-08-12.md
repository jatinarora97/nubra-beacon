# Instagram collector — build plan (2026-08-12, POLISHED — decisions locked, build next)

_All §10 decision points answered by user 2026-08-12 (inlined below). Next
step: POC the two add-on actors locally, then build. Companion:
`instagram-apify-vs-meta-2026-08-11.md` (route decision),
`out/instagram-test/` (real extraction fixtures)._

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
- **Cadence: HOURLY (user decision, revised from daily)** with new-post
  detection so quiet hours cost (almost) nothing. Methodology: every run
  passes `onlyPostsNewerThan=<per-source watermark>` — accounts with nothing
  new return zero rows, and pay-per-result bills nothing for zero rows.
  **POC must verify empty-run billing** (our one empty hashtag run DID bill a
  single $0.0027 no-items row — if empty profile checks bill per-URL rows,
  hourly polling costs ~$20/mo for nothing and the registry `cadence` knob
  drops to e.g. every-4-hours or daily; decide on POC data, not hope).
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

`latestComments` is a **latest** sample (~10), NOT top-liked. **User decision:
IN v1** — the separate `apify~instagram-comment-scraper` actor fetches ~30-50
comments incl. likesCount per gated post; we sort and keep the **top 10 liked**
as child items (marked `raw.top_liked=true`; the free latest-sample still
covers ungated posts). POC locally on a few posts before wiring (user
requirement), same as the transcript actor.

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

## 9 · Build & test protocol (updated with user decisions)

0. **POC FIRST (user requirement)**: locally, free account, a few real posts —
   (a) transcript actor on 3 Hindi-heavy stockburner reels (Hinglish gate),
   (b) comment-scraper actor on 2 high-comment posts (top-10-liked check),
   (c) empty-run billing measurement for the hourly methodology (§2).
1. Build collector + migration + seeds + UI on `jatin/beacon-updates`.
2. Local E2E on the FREE account: backfill subset → enrich → verify instagram
   items in Trends / Issues / Features / Voices / Explore / heads-up.
3. Ship on the branch → prod release → prod `.env` gets the paid APIFY_TOKEN.
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
fallback). 7. Both add-on actors (transcriber + comment fetcher) POC'd
locally on real posts before wiring.
