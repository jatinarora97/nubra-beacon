# Session handoff — 2026-08-25 (read with ~/.claude/skills/nubra-beacon + docs/HANDOVER.md)

Next session: read this, the nubra-beacon skill, and HANDOVER.md — then start
WITHOUT asking the user for basics. Everything below is committed on
`jatin/beacon-updates` (prod deploys from it).

## The active workstream: API-trader segment → "API Trading" dashboard section

Build progress vs docs/api-trading-section-plan-2026-08-25.md (steps 1-6):

1. **DONE — migration 0017** (api_trader_items + landscape_features; NO FK
   on item_id — social_items has a composite PK; stage CHECK includes
   'irrelevant' marker rows so judged-irrelevant items are never re-spent).
2. **DONE — pipeline lens**: community/enrich/api_trader.py (GATE_PG regex
   gate → Haiku classify in 20s, irrelevant markers, first_api_type
   broker/any/unclear, theme bucketers shared with the seed loader). Wired
   into tagger.run() isolated. Live-tested on the local prod mirror.
   Historical seed: data/api_trader_seed.json.gz + scripts/
   load_api_trader_seed.py (4,733 rows loaded locally, $0). (86400c1)
3. **DONE — endpoints**: community/api/api_trading_api.py, 7 routes under
   /api/v1/api-trading/* (funnel w/ first_api_split, themes, candidates,
   landscape GET/POST/DELETE, items). Registry api_trading block holds the
   5 candidate defs + 10-player landscape roster. All tested green on real
   data. (bbb1d03)
4. **DONE — landscape weekly monitor**: community/enrich/
   landscape_monitor.py — fetches roster urls, Haiku-extracts shipped/
   upcoming features (existing names fed back = canonical dedupe), upserts
   added_by='auto' (never clobbers manual rows' status), 6-day
   pipeline_state gate, rides extra_sources.run(daily). Verified: 8/8
   fetchable players, 89 features. AlgoTest + Angel One are JS/bot-gated →
   urls: [] = manual-only by design. (c7ed566)
5. **DONE — UI**: sidebar group "API trading" (Overview / Landscape /
   Data) + webapp/app/api-trading/* (lens.ts vocabulary, days-filter,
   funnel + theme boards + candidate cards; landscape coverage strip +
   feature catalog + manual add/delete; filterable data explorer with
   ?theme= deep links). lib/api.ts gained del(). Verified: npm run build
   clean + SSR curl checks on all 3 pages + POST/DELETE round-trip clean.
   Notes: candidates window capped at 90d (previous-window comparison must
   stay inside 180d retention); unknown kinds render as "other" segment.
6. **ON HOLD — user decision 2026-08-27: do NOT release the section yet.**
   The whole section sits behind one switch: `API_TRADING_ENABLED` env
   (overrides registry api_trading.enabled; off/false/0/no = dark). Dark =
   endpoints 404, sidebar group hides (client probe), classifier spends
   nothing, landscape monitor skips. Prod launch day: set
   API_TRADING_ENABLED=on in prod .env (or just leave it unset — registry
   default is on... so ON PROD SET API_TRADING_ENABLED=off BEFORE the next
   release, since the branch ships the section), recreate api container,
   `./cm migrate` (0017), `docker compose exec -T api python
   scripts/load_api_trader_seed.py` ($0), landscape runs next morning
   build. ~1k historical gated-irrelevant items classify naturally
   (~$0.40, bounded 200/run).

Market research (2026-08-27, user request): docs/
api-trader-market-research-2026-08-27.md — competitor S/W vs Nubra
(ground-up, docs-first), venue/targeting map, 3 segments (G1 explore /
G2 first-API / G3 active) with plays. Built from the lens corpus + 4 web
research agents; every claim URL'd. Flags found: Nubra API pricing
undisclosed, AlgoTest/Tradetron listing discrepancy, NubraOSS not public
(grounding doc says live — wording review), PyPI missing project URLs,
r/algorading doesn't exist (source-list cleanup).

Ads workstream (2026-08-29, user request), split after feedback into:
- docs/api-trader-ads-strategy-2026-08-29.md — actionable playbook:
  3 audiences (plain names, not G1/G2/G3), 5 evidence-backed hooks
  (UAT/paper-trading 256 corpus items = validated top hook), Search
  campaigns w/ per-keyword evidence tables, YouTube keywords + channel
  placements backed by Beacon lens-channel counts, Meta 3-play table,
  GEO priority table, cross-doc consistency table.
- docs/api-trader-ads-compliance-ops-2026-08-29.md — verification
  chains (G2RS/Meta SEBI), NSE ad code incl. §5.7
  no-algo-past-performance, DPDP/email rules (scraping out on 5
  grounds), budget shape, measurement wiring, blockers (publish API
  pricing; SI-portal sync; DPDP consent wording; §5.7 legal read).

Organic AI visibility (2026-08-29): docs/
nubra-organic-ai-visibility-2026-08-29.md — live crawl audit (API
landing/blogs/insti pages serve 70 chars to AI bots — client-rendered;
zero API URLs in any sitemap; docs are the only crawlable API pages),
ranked fix list (SSR the API section, sitemaps, numbers page, Bing/
IndexNow, question-shaped headings, JSON-LD, PyPI urls), organic mention
playbook, and a 10-query 4-engine experiment kit the USER runs manually
and pastes results back for pattern extraction (baseline: Nubra ~0
mentions expected; re-run 6 weeks post-fix).

AI-search experiment (2026-08-30, user ran the 10-query panel):
docs/ai-search-experiment-results-2026-08-30.md — Nubra 0/40 answer
slots, 0/155 citations (baseline confirmed). Patterns: Zerodha's own
support/docs pages = #1 cited source (15) -> validates numbers/FAQ-page
play; Claude cites Brave-tail blogs (tradejini/liquide/sahi) = cheapest
engine to win; Pocketful already in Claude's set = feasibility proof;
Gemini memory-stale (quoted Kite Rs2000, actual Rs500); multibagg never
appeared (demoted from outreach). Re-run panel ~6wk post site fixes.
Raw capture: docs/experiment.rtfd (user file, don't commit).

Analysis deliverables (done): docs/api-trader-insights-2026-08-25.md
(senior-grade; observed/inferred/chosen wording fixed, 7210ff8) ·
out/scan-v1-all.json (4,733 rows, local only). Taxonomy: first_api splits
broker/any/unclear; seed rows = 'unclear', live classification fills it.

## In flight on prod (check before anything else)

1. **Reddit backfill**: the user was running scripts/backfill_reddit.py
   detached (`docker compose exec -dT api sh -c "... > /tmp/backfill_reddit.log"`).
   Check: tail that log + count reddit rows ingested recently. The DEPLOYED
   image may still have the fragile all-at-end script; the branch has the
   per-sub incremental version (31acf0e) + proxy session-pinning (19a1e69)
   + hardened preflight (195c341) — a release ships all three.
2. **Reddit outage history**: Aug 10-25 gap. Root causes solved in order:
   VM IP decoyed → residential proxy; Reddit geo-gated INDIA (~Aug 20) →
   proxy must be country-US; rotating exits within a session → session
   pinning. REDDIT_PROXY_URL (country-US) is in prod .env.
3. **Pending release**: whatever tag ships next carries: per-sub backfill,
   session pinning, preflight retries, digests-actually-off (YAML fix
   6f65448 — user still received digests until this deploys... may have
   deployed 2026-08-25-Jatin already; verify with docker compose ps).

## Shipped this session (all live on prod unless noted)

SSO (Google via oauth2-proxy on VM port 3001; sso_allowlist DB authz; Slack
Approve/Reject buttons; Access-requests page; 1h cookie expiry) · Team
activity page (fed by authz pings) · Explore: intent charts (100% mix,
multi-select popover+legend, bigger, label fix), AND/OR multi-keyword
search, topic/posted columns · Beacon API /api/beacon/v1 (22 endpoints,
keys via API-access page, validator script; consumer guide
docs/beacon-api-consumer-guide-2026-08-19.md; host 172.28.0.69:8101) ·
grounding fixed to v2 on prod · Instagram collector (earlier) · API-trader
watch-source expansion (16 sources).

## Parked / standing (do not re-ask; act when user raises)

Content-gen v2 ON HOLD (Nano Banana + TTS bench; needs GEMINI_API_KEY) ·
partitions + 180d purge BEFORE OCT 2026 (hard deadline) · key rotation
(everything pasted in chat: apify tokens, google client secret, slack
webhook+signing, beacon api keys, youtube/github) · S3 lifecycle rule on
nubra_beacon/instagram/ · branch→main merge decision · Slack digests off by
choice (delivery.slack_digests knob; source alerts silent — twice burned by
silent reddit outages; consider an alerts-only mode) · MCP-team handover
(fresh key + consumer guide) · Telegram/Discord + Marketcalls/AlgoTest/
Tradetron community collectors (landscape blind spots, listed in insights
doc §4).

## Session gotchas (cost real time; do not relearn)

1. docker compose exec DIES with the terminal — long prod jobs run
   detached (-dT + log file); scripts must store incrementally.
2. .env is read at container CREATION — edit then `make up S=<svc>`.
3. Bare YAML off/on = booleans — quote them, normalize in code.
4. Prod ports are remapped (api 8101, webapp 3001 behind oauth2-proxy);
   prod Makefile/compose/env are USER-MANAGED — give diffs, never assume.
5. VM→Mac file transfer = S3 presigned URL (docker cp into container,
   upload via boto3 from api container).
6. Local dev DB is a RESTORED PROD MIRROR as of 2026-08-27 (112.6k items
   incl. reddit backfill; item_ids match prod — that's why the scan seed
   works). Prod dumps are CUSTOM format (.dump) — pg_restore, not the
   gunzip path in make restore-local; lens re-seeded + 1,090 new gate
   matches classified locally (lens = 5,242).
7. oauth2-proxy sends identity upstream as X-FORWARDED-EMAIL.
8. Next 16: middleware.ts is proxy.ts.
