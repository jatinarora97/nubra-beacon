# Nubra Beacon — Session Handover (written 2026-08-04)

_Read this INSTEAD of asking the user basics. Reading order for a new session:
`CLAUDE.md` → this file → `docs/nubra-beacon-tech-backlog-2026-07-08.md` →
`docs/beacon-updates-branch-notes-2026-07-18.md`. The status doc and workplan
(2026-07-05/07) are historical. The user moves fast, tests on prod personally,
and does NOT want basic details re-confirmed._

## What this is

Nubra Beacon: community radar + marketing copilot for Nubra (Indian NSE/BSE/MCX
broker). Listens to X, Reddit, YouTube, GitHub, broker forums, app-store
reviews; enriches with Haiku (Batch API); rolls up trends/issues/features/
voices; scores opportunities; writes compliance-gated drafts + content briefs +
ready-to-publish social recommendations; delivers hourly heads-ups, daily +
Sat→Sat weekly roundups (Slack/email config-gated, archive always); React
dashboard on :3000, read-API :8400. Humans post — Beacon only recommends.

## Where everything runs

- **Prod**: box `mcp-server`, user `zanskar`, `APP_DIR=/home/zanskar/nubra-beacon`,
  logs `/home/zanskar/logs/nubra-beacon/cron.log`. Docker compose profile
  `app` (postgres + migrate one-shot + api + webapp). Host crontab drives the
  pipeline (hourly 07-23+00 IST run-local, 06:00 morning-build, Sat 10:00
  weekly, 02:00 backup via `make dump`-style target). Prod checkout is the
  **branch `jatin/beacon-updates`** (Path-A trial deploy, 2026-07-18), NOT main.
- **Release flow** (mirrors nubra-ai-personalization): dev Mac
  `RELEASE_TAG=<tag> make push-prod` (buildx linux/amd64 → ECR
  `851725268918.dkr.ecr.ap-south-1.amazonaws.com/zs/nubra-ai`, images
  `nubra-beacon-{api,webapp}-<TAG>`); prod: set RELEASE_TAG in `.env`,
  `git pull`, `make pull-prod`. AWS profile for ECR: user has both `dev`/`prod`
  profiles — their Makefile currently says `dev` and works.
- **Local dev**: this Mac, repo `/Users/jatin/nubra/6.MarketPulse`, venv `.venv`,
  ALWAYS `./cm` (never bare python). Dev DB = docker postgres :5544. Normal dev
  workflow = restore prod dumps (`make restore-local DUMP=...`), local scraping
  only to test scraper changes. `./cm ui` serves webapp+api with respawn.
- **Repo**: github.com/jatinarora97/nubra-beacon (SSH push works from this Mac).
  Branches: `main` (prod-lineage), `jatin/beacon-updates` (current working
  branch, contains everything), `feature/deploy-extra-sources` (teammate's,
  merged into the branch).

## ⚠ URGENT check for the next session

The last images pushed to ECR are tag `2026-07-18-beacon-updates`, built
BEFORE three later fixes on the branch: (1) **per-source cadence** — without
it the four new collectors run HOURLY on prod and **YouTube burns 36k quota
units/day against a 10k free quota** (exhausts mid-day, collector errors);
(2) grouped freshness UI; (3) weekly-page null-safety (user reported the
weekly page erroring on prod). **First action: confirm with the user whether
they deployed a newer tag; if not, `RELEASE_TAG=<new> make push-prod` from the
branch + prod `git pull && make pull-prod`.**

## Credentials — names, locations, status (values live in .env files, NOT here)

Local `.env` (this Mac, gitignored) and prod `.env` (copied manually) carry:
- `ANTHROPIC_API_KEY` — active, funds everything (Haiku enrich, Sonnet drafts).
- `TWITTERAPI_IO_KEY` — **prod has the paid $29/mo Starter key (works)**;
  local still has an old 402 key. Caps: x_live_cap 300, $1/day budget.
- `LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST` — nubra-beacon project, EU cloud;
  ingestion WORKS (quota was suspended, later lifted).
- `YOUTUBE_API_KEY`, `GITHUB_TOKEN` — **were pasted in chat 2026-07-18;
  ROTATION STILL PENDING** (user said "noted"). Ask ONCE whether rotated;
  if yes drop the item, don't nag.
- `SLACK_WEBHOOK_URL`, `GMAIL_SENDER/GMAIL_APP_PASSWORD` — STILL NOT PROVIDED.
  Everything is config-gated and archive-only until they land. Senders are
  additionally hard-gated to MODE=prod (compose sets it) — a restored dump on
  a laptop can never message the team.
- `RELEASE_TAG` — in prod .env, currently `2026-07-18-beacon-updates`.
- `APIFY_TOKEN` — TWO accounts (both tokens in local `.env`, strategy comment
  there): FREE account (fxFNqC51Fso21DqSF) = local build/testing; PAID Starter
  $29/mo (euvGWlQ5a8MfB9zNe) = prod + local-after-free-exhausted. Both pasted
  in chat → on the rotation list with YouTube/GitHub keys.

## Architecture facts a new session must not re-derive

- Pipeline: scrape → clean → enrich → aggregate → score → draft → social →
  compose → dispatch (`runner.py STAGE_MODULES`); per-stage isolation; pg
  advisory run-lock + flock in crontab; watermarks are arrival-clock and
  GREATEST-guarded; every rollup is replay-proof (feature_item_map ledger for
  features). Reddit = vendored zanshash scraper via Playwright (ONLY transport;
  preflight block-detection; upstream checkout auto-cloned to `.vendor/`).
  Keyword search fetches across all Reddit (market-term gate vs Nubra-Valley
  homonym). Engagement refresh re-polls suggested-opportunity threads.
- New sources (YouTube/GitHub/forums/app-reviews): SocialItem contract,
  exception-bounded, watch_sources kinds `youtube_query/github_query/forum/app`
  (+config jsonb), **cadence: daily (morning build) by default** — registry
  overridable. Instagram: PLANNED ONLY (see below).
- Grounding: `nubra_features` table, version **context-v2, 31 features** (real
  product doc + 3 user-authorized adds). Grounding page publishes v3+.
  Social engine reads THIS (its private YAML was deleted). OMS V3 / News API /
  flexible-brokerage-as-live / retail basket orders are deliberately EXCLUDED
  (product doc says internal/unverified/upcoming).
- Content briefs: morning-only generation, same-day guard (hourly can't wipe
  human edits), full-length titles, Haiku repeat-judge vs last-7d briefs
  (embeddings were PROVEN unable to separate repeats — 0.871 vs 0.869 on real
  July examples; don't retry that idea). Ask-Beacon revision: manual edits
  direct, instruction/platform via Haiku (Sonnet retry), L1 re-check,
  outline.revisions history.
- Social recommendations (teammate-built, adjusted): finished copy-first posts,
  evidence-grounded, same-day guarded, own tables (0011), page below Content
  briefs. Compliance gates shared.
- Dashboard: window filter everywhere (default Last hour; `?window=Nh/Nd`
  generalized; Opportunities defaults All-open), day-picker + calendar on
  briefs, exports (items+sources CSV/XLSX), source-health page with LIVE
  probes, `./cm doctor` (15+ checks incl. collector probes), AI-usage page
  (llm_usage priced at call time; Langfuse config-gated).
- Migrations: 0001–0012, runner = user's version+dirty scheme + my self-heal
  for legacy DBs (dirty column, nullable sha256). Migrate = one-shot compose
  service gating api.
- Registry (`community/config/registry.yaml`) is bind-mounted ro on prod —
  config edits apply without a release; CODE needs a new image. This mismatch
  (branch image + main checkout or stale image + new code) has bitten twice —
  always check both sides.

## Timeline (why things are the way they are)

Jul 3-5: design→v1 build→React UI→status doc. Jul 7: six-phase workplan
executed via parallel agents (visibility, correctness, LLM observability,
content controls, discovery, docs). Jul 8: prod prep (Docker split images +
compose profile, ECR flow, crontab, seeds), 4-segment adversarial review found
22 real bugs (incl. dead broker_issue scoring, morning-build crash, brief-wipe)
— all fixed; structured IST logging added; repo pushed. Jul 9: prod live
(fresh DB, cron initially dead → APP_DIR missing leading slash), doctor built,
Reddit keyword search, prod dump analysis workflow. Jul 15-17: GitHub-source
explainer; real grounding swap (context-v1→v2); brief repetition judge; brief
day-picker + full titles. Jul 18: teammate branch merged with adjustments
(sources UI for new kinds, live health probes, cadence, dual-grounding kill),
prod trial-deployed from branch. Aug 4: Instagram ingestion plan (decided, not
built) + content-render prototype (round 1 built, round 2 in flight).

## Active workstream RIGHT NOW (Aug 4)

**Brief→assets generator** (`community/render/`, outputs `out/render/`,
NOT committed): round 1 produced a real 8-slide carousel (user verdict:
"bland") + a real 49.8s reel MP4 with macOS-say placeholder voice (user:
"not engaging, bad pronunciation") — the reel FORMAT (screen info + commentary
voiceover that doesn't read the screen) is user-approved. Round 2 agent was
launched to: design-system v2 (Lucide icons, gradient panels, Mechanic
callouts, varied compositions, self-hosted Inter, Nubra logo), Kokoro-82M
real voice samples + reel regen, and 2026 image-gen model research (for spot
illustrations only — full-slide image-gen rejected: that's why the user's
NotebookLM reference looks AI). **Check `out/render/v2-*` and
`out/render/voice-samples/` for its artifacts**; its conclusions may not have
been reviewed by anyone yet. Architecture direction locked: HTML/Playwright
rendering (crisp text, brand control) + curated vector assets + selective
image-gen; TTS = Kokoro-82M primary (Apache), MeloTTS fallback; XTTS/F5
disqualified (non-commercial).

**Instagram — APPROVED FOR BUILD, plan awaiting user polish** (2026-08-12):
route = Apify `apify/instagram-scraper` profile-watching (LIVE-TESTED: 8/8
accounts, real fixtures in `out/instagram-test/`; hashtag route proven DRY;
Meta Graph API demoted to optional add-on — no app review needed). Full plan:
`docs/instagram-collector-plan-2026-08-12.md`; route economics:
`docs/instagram-apify-vs-meta-2026-08-11.md`. Key facts: 11 verified handles
(tastyliveshow not tastylive; tycoontraders.in UNRESOLVED; spidersoftware vs
spidersoftwareindia undecided); kind `instagram_account`, daily cadence,
backfill 20/account (~$0.55); media downloaded AT FETCH (CDN URLs expire in
hours) to S3 `nubra-beacon/instagram/<shortCode>/` (bucket TBD — reuse reports
bucket?), 180d lifecycle; tier 1 = Apify transcript actor ~$0.01/reel with a
MANDATORY Hinglish validation gate (fallback: local faster-whisper); tier 2 =
Haiku vision on images; tier gates RELATIVE to each account's engagement
baseline (27→181k likes spread); paidPartnership/isSponsored posts skipped;
latestComments = latest-not-top (top-liked needs comment-scraper actor —
deferred decision); source-health live probe = Apify credits endpoint.
~$5-7/mo of the $29 credits. **ALL decisions locked 2026-08-12** (plan §10): 11 accounts final (tycoontraders dropped, spidersoftware+tastyliveshow in, sjosephburns kept); S3 = SAME reports bucket as nubra-ai-personalization, layout nubra_beacon/instagram/<creator>/{reels,images}/; top-10-LIKED comments IN v1 via apify~instagram-comment-scraper; cadence HOURLY with onlyPostsNewerThan new-post detection (POC must verify empty-run billing — fallback registry cadence knob); backfill 20/account via scripts/backfill_instagram.py that the user runs once on prod. NEXT STEP: POC the transcript + comment actors locally (free account) on real posts, then build on jatin/beacon-updates.

## Pending items (complete list — do not invent others, do not re-ask)

1. URGENT check above (cadence image on prod).
2. Branch → main merge decision: blocked ONLY on the user's product call:
   briefs-vs-social-recs (extend repeat-judge cross-surface OR retire briefs).
   These two are ONE workstream by user decision.
3. Key rotation (YouTube/GitHub) — ask once.
4. Slack webhook + Gmail app password — user still owes; everything ready.
5. Content generator round 2 review → then integration (`./cm stage render`,
   download buttons on content page, Kokoro+Inter into the api image).
6. Instagram build (after user's Meta app registration).
7. Backlog P1s (docs/nubra-beacon-tech-backlog-2026-07-08.md): rolling
   partition job + 180d purge **before October** (hard deadline — partitions
   end 2026-10); auth (OIDC proxy; README mandates LAN-only meanwhile);
   health alerting; scoring re-tune from prod feedback (no shadow run — user
   decision); enrichment prompt tightening (invented intent labels);
   LOCAL_MAX_ITEMS=600 → registry-configurable.

## Working-style contract with this user (follow, don't re-learn)

Prod-grade only, no local/prod forks; verify on REAL data before claiming
done ("no complacency"); explain BEFORE merging/big changes — they want to
understand everything they ship; latest instruction wins, note-and-defer
conflicts rather than block; minimal literal changes when they say "keep as
is"; emoji-free UI; plain-English UI copy (no ./cm, credits, watermark talk on
pages); they paste logs/errors and expect pinpoint diagnosis; commit style =
detailed why-bodies + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`;
they rename/restructure Makefiles themselves — reconcile, don't revert; locked
decisions in CLAUDE.md are CLOSED (τ=0.86, bar 60, 180d retention, Gmail SMTP,
vendored scraper only, React UI, no shadow run). Parallel agents with strict
file ownership + my own review/commit pass is the established build pattern;
four-segment adversarial review before big deploys proved its worth.

## Fast diagnostics

`docker compose exec api ./cm doctor` (prod) / `./cm doctor` (local) — 15+
PASS/FAIL lines answer most "is it broken" questions. `out/cron.log` has
IST-timestamped stage-boundary logs with full tracebacks. Source-health page
has live API probes. `make restore-local DUMP=...` to analyze prod data here.
