# "API Trading" dashboard section — build plan (approved scope, 2026-08-25)

User decisions locked: the section is a GO · first_api splits into
broker-API-first vs any-API-first vs unclear · sections = Funnel, Friction,
What-works, Landscape monitor (auto-weekly competitor grounding + manual
add), Build candidates, plus a raw-data explore with lens columns.

## How it shows (UI proposal)

New sidebar GROUP "API trading" with three pages (house components, no new
deps):

1. **Overview** — the story page, four sections top-to-bottom:
   - Funnel: five stage cards (n + % + friction share) with a stacked
     kind-mix bar per stage (reuse the Explore chart components); a
     first_api split card (broker-first / any-API-first / unclear).
   - Friction board: theme table (items, share) → click a theme to expand
     its top items with links.
   - What works: same pattern over showcase themes.
   - Build candidates: the five demand patterns as cards, each showing its
     live evidence counters (theme counts + 30d trend arrow) — numbers
     recompute from the table, so the cards stay current without editing.
2. **Landscape** — competitor grounding:
   - One card per tracked player: shipped / upcoming features with
     first-seen dates and source links; freshness stamp.
   - "Add feature" form (manual entries marked as such) — mirrors the
     Grounding page pattern.
   - Coverage strip: corpus/relevant/friction mention counts per player
     (the §4 visibility table, live).
3. **Data** — Explore-style table over classified items only: raw columns +
   lens columns (stage, first_api type, layer, kind, tools, gist), same
   filters/window/export as Explore.

## Architecture (prod-grade, mirrors existing patterns)

1. **Migration 0017**: `api_trader_items` (item_id PK/FK, stage,
   first_api_type broker|any|unclear|null, layer, kind, tools jsonb, gist,
   friction_theme, working_theme, classified_at, model) ·
   `landscape_features` (id, competitor, feature, status
   shipped|upcoming|rumored, evidence_url, first_seen, last_seen, added_by
   auto|<email>, notes).
2. **Pipeline stage** `community/enrich/api_trader.py`: candidate gate
   (the validated regex) over newly-enriched items → Haiku lens classifier
   (same batch mechanics as enrichment; absence-based on api_trader_items;
   bounded per run; llm_usage-tracked). Runs inside the hourly pipeline
   after enrich — new items cost pennies/day.
3. **Historical seed at zero LLM cost**: the local full-corpus scan
   (out/scan-v1-all.json) carries PROD item_ids (the dump preserves them) —
   ship as `data/api_trader_seed.json.gz` + loader script; prod backfills
   the table in minutes without re-spending the ~$8. Seed rows get
   first_api_type=unclear (the split starts with new classifications);
   themes are computed at load by the same bucketer the pipeline uses.
4. **Landscape monitor job**: weekly gate (same last-success pattern as
   fetch_every_hours) inside the morning build: for each player in a new
   registry block `api_trading.landscape` (name + public URLs: changelog /
   API docs / pricing), fetch pages via httpx → Haiku extracts
   feature+status deltas vs stored rows → upsert (added_by=auto,
   evidence_url) → new/changed rows flagged for the Landscape page.
   Chatter-derived features (tools column) surface on the same page.
   Manual add = internal endpoint + the form.
5. **Internal endpoints** `/api/v1/api-trading/*`: funnel, frictions,
   working, candidates, landscape (GET/POST/DELETE), items (cursor,
   filters). Beacon API (`/api/beacon/v1/api-traders/*`) = phase 2.
6. **Doc fix riding along**: rephrase the onboarding build-candidate line —
   "first order in minutes" is our framing of 119 onboarding-friction items,
   not a quoted complaint.

## Build order + estimates (evaluate → redo → evaluate at each step)

1. Migration + seed loader + verify counts on local prod-mirror (0.5d)
2. Pipeline classifier stage + local E2E on fresh items (0.5d)
3. Internal endpoints + tests on real data (0.5d)
4. Landscape monitor job + registry block + first live fetch of the 7 (1d)
5. UI (three pages) + screenshot verification both themes (1d)
6. Release + prod seed load + first weekly landscape run (0.25d)

Total ≈ 3.75 days of build. Every step ends with an evaluation pass on the
restored prod mirror before moving on.

## Open items (non-blocking, decide during build)

1. Landscape URL list per player (I seed with obvious ones: Dhan/Zerodha/
   Upstox/Fyers/AngelOne changelog+API pages, AlgoTest/Tradetron/OpenAlgo
   sites; user can edit in registry).
2. Weekly digest for the section (Slack knob exists; digests currently off).
