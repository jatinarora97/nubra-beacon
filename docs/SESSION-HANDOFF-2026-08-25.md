# Session handoff — 2026-08-25 (read with ~/.claude/skills/nubra-beacon + docs/HANDOVER.md)

Next session: read this, the nubra-beacon skill, and HANDOVER.md — then start
WITHOUT asking the user for basics. Everything below is committed on
`jatin/beacon-updates` (prod deploys from it).

## The active workstream: API-trader segment → "API Trading" dashboard section

1. **Approved + planned**: docs/api-trading-section-plan-2026-08-25.md is
   the build blueprint (UI = sidebar group with Overview/Landscape/Data
   pages; pipeline = candidate gate + Haiku lens into api_trader_items;
   landscape monitor = weekly competitor-grounding job + manual add;
   historical seed at $0 via out/scan-v1-all.json — PROD item_ids, the
   Aug 25 dump preserves them). Estimates inside. BUILD NOT STARTED — begin
   here after the user's go/corrections on the 3-page layout.
2. **Analysis deliverables (done)**: docs/api-trader-insights-2026-08-25.md
   (senior-grade: funnel, friction economics, landscape visibility map —
   AlgoTest/Tradetron/no-code layer are blind spots) ·
   docs/api-trader-segment-2026-08-22.md (working doc). Dataset:
   out/scan-v1-all.json (4,733 classified rows, local).
3. **Taxonomy decision**: first_api splits into broker-API-first /
   any-API-first / unclear (seed rows = unclear).
4. **Honesty note**: "first order in 5 minutes" is OUR framing, not a
   quoted thread — fix the phrasing in the insights doc during the build
   (plan §6 has receipts: 70 onboarding-friction threads).

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
6. Local dev DB is a RESTORED PROD MIRROR as of 2026-08-25 (99k items,
   item_ids match prod — that's why the scan seed works).
7. oauth2-proxy sends identity upstream as X-FORWARDED-EMAIL.
8. Next 16: middleware.ts is proxy.ts.
