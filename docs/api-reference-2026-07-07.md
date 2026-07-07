# Nubra Beacon — read-API reference (as of 2026-07-07)

**Orientation (read this first).** The API is FastAPI on `http://127.0.0.1:8400`
(`/docs` for interactive Swagger, `/openapi.json` for the machine spec). All
routes are prefixed `/api/v1`. The webapp never calls it cross-origin: Next.js
rewrites same-origin `/api/v1/*` to the API, so the browser sees one host.
Responses are product-shaped (server-computed sentences, flattened jsonb) so the
frontend stays thin. Auth: on prod an OIDC proxy injects `X-Auth-Request-Email`;
locally every write is attributed to `local-dev`. Write philosophy: the API is
overwhelmingly read-only; the few writes are one-way state transitions
(opportunity acted/dismissed, suggestion activate/reject), append-only inserts
(feedback), or versioned publishes (grounding catalog) — nothing destructive,
no deletes except watch-source removal. Errors are FastAPI-standard
`{"detail": ...}` with 400 (bad input), 404 (not found), 409 (one-way
transition already taken).

Registers: **T** = technical (engineers) · **PM** = what it powers, plain English.

---

## Health & overview

### GET /api/v1/health
- **T** — Dependency-light probe: attempts `SELECT 1`; returns `{ok: true, db: bool}`. Always 200 while the process lives; `db: false` means Postgres is unreachable. No auth, no params.
- **PM** — Powers the red "backend offline / database unreachable" banner; distinguishes "no data" from "system down".

### GET /api/v1/overview
- **T** — Landing-page aggregate: `kpis` (items/analyzed today, actions on table ≥40, new high-priority ≥60 today, Nubra mentions 24h, drafts ready), latest daily-roundup `headline`, top 3 `top_actions` (decorated opportunities, stripped to card fields), `top_movers` (top 3 by velocity_z), `freshness` (last item per source, enrich watermark, `schedule_installed` from crontab inspection, next hourly/morning-build times in IST), `llm_last_run` (run_id, cost_usd, calls, stages, ts).
- **PM** — Everything on the Overview page: the KPI row, freshness strip, top actions, and the LLM-cost card.

## Listening data (verification layer)

### GET /api/v1/items
- **T** — Filterable canonical items (duplicates and noise excluded): `topic`, `broker` (ILIKE over entities), `intent`, `audience`, `q` (ILIKE text), `min_engagement`, `source`, `sort` = engagement|recent, `limit` ≤100, `offset`. Text clipped to 300 chars; includes enrichment fields + `duplicate_count`.
- **PM** — The Explore table: inspect the raw posts behind every number, with filters and search.

### GET /api/v1/items/{source}/{external_id}
- **T** — Single item with full text + enrichment + up to 50 thread siblings ordered by time. 404 if unknown. `minhash_sig` stripped.
- **PM** — The item drill-down: one post plus the conversation around it.

### GET /api/v1/items/export
- **T** — Same filter semantics as `/items` (shared SQL builder — they cannot drift) but full text, spreadsheet-shaped rows (16 columns incl. IST timestamps, interactions summed from native engagement, entities as JSON string), `format` = csv (UTF-8 BOM) | xlsx (openpyxl, frozen header), `limit` default 2000 / max 10000. Control chars stripped; `=`/`+`/`-`/`@` cells formula-guarded. `Content-Disposition` names the file `beacon-items-<IST stamp>`.
- **PM** — The Export CSV / Export Excel buttons on Explore: download exactly what the current filters show.

## Rollups (what's happening)

### GET /api/v1/trends
- **T** — `topic_daily` grouped over `date`/`window` (1d|7d), `other:*` excluded; per topic: summed `count`, max `velocity_z`, max `spread`, summed `engagement_sum` (log-index, not raw interactions), taxonomy label. Ordered velocity-then-volume, `limit` ≤100.
- **PM** — The Trends chart: what the community talks about and whether it is accelerating.

### GET /api/v1/issues
- **T** — `issue_rollup` grouped by (broker, issue_key) over `from`/`to` (default last 7d): total `count` (sum of idempotent per-day rows), per-day `day_counts`, max severity, avg sentiment, deduped `sample_item_ids` resolved to ≤5 engagement-ranked quote `samples`. Optional `broker` filter. Includes Nubra itself when complaints exist.
- **PM** — The broker × issue heatmap and the "what people actually said" quote segments.

### GET /api/v1/features
- **T** — `feature_rollup` grouped by centroid `feature_key` over `from`/`to`, `min_days` gate; merged brokers_mentioned, ≤5 quote samples, canonical label. Counts are backed by the `feature_item_map` exactly-once ledger.
- **PM** — The Feature-requests cards: what traders keep asking for, phrasings merged by meaning.

### GET /api/v1/voices
- **T** — `author_stats` joined to authors, `min_score`/`limit` params; adds computed `profile_url`, top-3 `niche_topics` from enrichment, most recent thread, and a server-written `why` sentence.
- **PM** — The Voices page: who consistently matters, with proof and profile links.

### GET /api/v1/nubra-mentions
- **T** — Items matching the `nubra` word-boundary regex (noise/dupes excluded), `days` window (≤90): KPI block (mentions 24h/window, positive share, complaints from issue_rollup) + `positives` list (sentiment ≥ 0, most positive first, ≤`limit`). Negative items are counted but served by `/issues`.
- **PM** — The Nubra mentions page: the positive side of what people say about us.

### GET /api/v1/roundups
- **T** — One roundup row by `period` = daily|weekly and optional `date` (default: latest). Returns period, date, structured `payload`, `delivery` state. 404 when none exist.
- **PM** — The Weekly roundup page (and the daily headline on Overview).

## Opportunities (what to do)

### GET /api/v1/opportunities
- **T** — Scored opportunities with `date`/`status`/`min_priority`/`limit` filters, decorated server-side: kind label, `why_engage` sentence (insight + velocity + capability match), age, timing fields, both drafts.
- **PM** — The Opportunities page: ranked conversations worth joining, drafts included.

### POST /api/v1/opportunities/{opp_id}/status
- **T** — One-way transition `suggested → acted|dismissed`; dismissal requires a reason from the enum (`not_relevant`, `already_handled`, `too_late`, `too_risky`, `other`). 409 if already transitioned; attribution from the auth header.
- **PM** — The Acted / Dismiss buttons on each opportunity card.

## Content (what to make)

### GET /api/v1/content-proposals
- **T** — Briefs for `date` (default: latest day present), flattened from outline jsonb: treatment, format_family, platform (+why), hook, beats, caption, hashtags, cta, visual direction, timing window, `revisions_count`, `last_revised_by`.
- **PM** — The Content-briefs page: creator-ready briefs riding today's signal.

### GET /api/v1/content-taxonomy
- **T** — Registry-controlled `format_families` and `platforms` lists (the allowed values for generation and revision).
- **PM** — The platform dropdown in brief editing; the guardrail on what formats Beacon may propose.

### POST /api/v1/content-proposals/revise
- **T** — Body `{rank (required int), day?, instruction?, platform?, manual?: {field: value}}`. Manual edits apply directly (locked fields rejected); `platform`/`instruction` trigger an LLM revision (Haiku, one Sonnet retry) constrained to minimal change, validated against taxonomy + required fields + L1 compliance, grounded on the current catalog. History appended to `outline.revisions` (last 2 fed back, 10 kept). Returns the updated flattened proposal. Traced to `llm_usage` as stage `api`.
- **PM** — The Edit mode on brief cards: tweak fields by hand or tell Beacon what to change.

## Grounding (what Beacon may claim)

### GET /api/v1/features-catalog
- **T** — Current `nubra_features` rows (feature, description, status live|upcoming, category, seo_keywords) + the version string and publish time.
- **PM** — The Grounding page's current catalog: the only claims drafts are allowed to make.

### POST /api/v1/features-catalog
- **T** — Full-replacement publish: validated non-empty list → new version `v<n+1>` inserted with `is_current` flipped from the prior set; attribution returned (not persisted — no author column). 400 on empty/invalid rows or duplicate names.
- **PM** — The "Publish as new version" button; the next draft run grounds on what you saved.

## Sources & discovery (configure)

### GET /api/v1/sources · POST /api/v1/sources · POST /api/v1/sources/{id}/toggle · DELETE /api/v1/sources/{id}
- **T** — `watch_sources` CRUD. Kinds: subreddit, x_hashtag, x_handle, x_query, keyword. POST normalizes pasted prefixes (`r/`, `@`, `#`, URLs), rejects spaces except for x_query/keyword, accepts `config` jsonb (keyword: `{x: bool, reddit: bool}`, defaults both true), upserts reactivating on conflict. Toggle flips `active`; DELETE removes. DB is the source of truth — next scrape run picks changes up.
- **PM** — The entire Sources page: everything Beacon listens to, managed without a deploy.

### GET /api/v1/topic-suggestions
- **T** — `topic_taxonomy` rows with status `suggested` (from HDBSCAN discovery over `other:*` embeddings): key, label, `suggested_why`, item count, suggested_at.
- **PM** — The "Emerging themes Beacon noticed" section on Trends.

### POST /api/v1/topic-suggestions/{topic_key}/activate · /reject
- **T** — One-way status transition from `suggested`; 404 for unknown or already-decided keys. Activation makes the topic part of the live enrichment taxonomy (the prompt reads active topics from the DB).
- **PM** — The Activate / Dismiss buttons — a human decision before Beacon starts tagging a new theme.

## Feedback (input from the team)

### GET /api/v1/feedback · POST /api/v1/feedback
- **T** — Append-only `feedback` table. POST requires `object_ref` (jsonb) + `category`; GET filters by `category`, newest first, `limit` ≤100. Categories in use: `feature_request` (community Features page intake), `ui_feature_request` (Beacon requests page).
- **PM** — The Beacon-requests page and any "log this" input: team asks that shape the backlog.

## LLM usage (system)

### GET /api/v1/llm-usage/summary
- **T** — `llm_usage` aggregated over `days` (≤180): totals (cost, tokens, calls, batch split, traced/unpriced counts), per-day, per-stage, per-model series.
- **PM** — The LLM-usage page: what the AI layer costs and where it goes.

### GET /api/v1/llm-usage/last-run
- **T** — Stage/purpose/model breakdown + total cost for the most recent `run_id`. 404 before any usage exists.
- **PM** — The "LLM cost last run" card on Overview.

---

**Staleness note.** This file describes the API as of **2026-07-07** (29 routes).
The always-current truth is `http://127.0.0.1:8400/openapi.json` (or `/docs`) —
regenerate or amend this reference whenever endpoints change.
