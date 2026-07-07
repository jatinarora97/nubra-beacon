# Nubra Beacon — Work Plan (2026-07-07)

_The execution tracker for everything approved on 2026-07-07. Companion to the
status doc (`nubra-community-manager-status-2026-07-05.md`, which stays the
"what is built" authority). Work through the phases in order; each phase is
sized to be built AND validated together. Parked items at the bottom are not
to be started — resurface them when the phases above are done._

---

## 1 · Approved items, reframed

### From the existing backlog

- **B1 · Backend-offline banner** — the webapp soft-fails to empty states when
  the read-API is down, indistinguishable from "no data" (bit us once). Add a
  lightweight `/health` probe + a persistent banner in the layout when the API
  is unreachable, so a dead backend is loudly visible.
- **B2 · Weekly roundup page** — the Sat→Sat weekly roundup payload + markdown
  already generate into the `roundups` table; no webapp route renders them.
  Add a page (nav under "What's happening") rendering the latest weekly (and
  a way to see previous ones).
- **B3 · feature_rollup idempotency** — same latent bug class as the Issues
  double-count fixed 2026-07-05: `count = count + new` on conflict means a
  watermark replay inflates counts. Fix requires an item→feature_key mapping
  (store which items fed each key) so per-day recompute doesn't re-fold
  centroid running means. Do together with E1 (below) — the mapping serves both.
- **B4 · Reddit engagement refresh** — engagement is snapshot-at-fetch; threads
  that became action candidates never see their upvotes/comments grow. Add a
  `fetch_items`-equivalent on the vendored scraper transport: re-visit candidate
  threads (opportunities' threads first) on a cadence and update `engagement`.

### Explorations answered (see §3 for the full reports)

- **E1 · Emergent-topic discovery (HDBSCAN over `other:*`)** — approved. Weekly
  job clusters the embeddings of items tagged `other:*` (153 non-noise items
  today across ~240 ad-hoc keys) and proposes new taxonomy topics as INACTIVE
  suggestions (same human-activation pattern as discovered hashtags).
  **Exploration verdict:** clustering also earns its keep in 2 more places —
  feature-key maintenance (re-cluster feature phrases to catch centroid drift
  and should-merge keys; produces the item→key mapping B3 needs) and, later,
  issue-type discovery (cluster complaint texts to propose new issue keys —
  parked until complaint volume grows). Not useful for voices or brief dedup
  today (too little data, MinHash already covers near-dups).
- **E2 · Learned posting windows — recap only, stays parked.** v1 timing is
  rule-based: "engage now" when a thread is live & rising (<~12h, accelerating),
  else schedule into fixed IST windows (pre-open 08:30–09:15, open 09:15–10:00,
  post-close 15:30–17:00, evening 20:00–22:30). "Learned windows" is the P2
  upgrade that replaces that static table with windows regressed from the
  performance of OUR OWN posts — it requires the posting-with-approval workflow
  + a post_log + engagement tracking on our posts to exist first. Parked with
  its prerequisites.

### New requests

- **N1 · Nubra mentions page** — under "What's happening": what people say
  about Nubra, the positive side (praise, organic recommendations, questions
  answered well). Sourced from items matching the `nubra` gazetteer entry with
  non-negative sentiment + `is_nubra_watch` conversations. Note: current DB has
  ZERO Nubra mentions (small brand + X credits out) — page ships with honest
  empty states and fills as data arrives.
- **N2 · Nubra in Broker issues** — the negative side, same visibility logic.
  Finding: `nubra` is ALREADY in the broker gazetteer and nothing excludes it
  from `issue_rollup` — there simply are no Nubra complaints in the data yet.
  Work = verify end-to-end with a synthetic item, make Nubra's row visually
  distinct in the heatmap (own accent, pinned first when present), and note on
  the page that Nubra is watched like every other broker.
- **N3 · Postgres coverage audit** — answered in §3: everything product-facing
  is in Postgres except hourly heads-up messages (markdown archive only).
  Approved follow-up: persist heads-ups to the DB alongside roundups.
- **N4 · Freshness on Overview** — "last updated at" + "next update scheduled"
  strip on the Overview page, per source (X / Reddit last item ingested, last
  enrich/aggregate watermark, next hourly run + next morning build from the
  schedule definition).
- **N5 · Langfuse integration** — replicate the personalization-comms pattern
  (they use the `langfuse` SDK + their own `llm_usage` table carrying a
  `langfuse_trace_id` per row + a run-scoped trace context in
  `intelligence/trace.py`). Plan first (own phase), then: wrap
  `community/llm/client.py` so every call (sync + batch) emits a Langfuse
  generation under a per-run trace, keyed by stage. Separate Langfuse project
  ("separate stream") from personalization.
- **N6 · LLM cost surfacing** — extends N5: `llm_usage` table in OUR schema
  (per call: stage, model, tokens in/out, cost, duration, run id, trace link),
  last-run cost KPI on Overview, and a dedicated "LLM usage" page — visual
  (per-stage/per-model/per-day spend, token trends, batch-vs-sync split),
  deliberately not a Langfuse clone.
- **N7 · How-it-works page** — plain-English, visual-first explainer of the
  whole pipeline for a no-code audience: what we listen to, how items become
  trends/issues/actions, where compliance gates sit, what humans do. More
  diagram than prose; lives in the webapp (nav: "How Beacon works").
- **N8 · USP / grounding editor** — a page showing exactly what the drafts are
  grounded on: current `nubra_features` rows (live + upcoming USPs, keywords)
  — editable from the frontend. Each save publishes a NEW VERSION (the table is
  already versioned with `is_current`), picked up by the next draft run. This
  is the human-visible face of the "assumed-v0 until marketing's swap" decision.
- **N9 · Content-brief editing (LLM-assisted)** — briefs become editable:
  direct manual tweaks AND an instruction box ("shorter", "make it for
  LinkedIn") that triggers a targeted revision call — Haiku by default
  (escalate to Sonnet only if validation fails), context = current brief +
  its rides_signal + the last 2 revisions, prompt constrained to CHANGE ONLY
  WHAT THE INSTRUCTION ASKS. Revised briefs re-pass L1 compliance; history
  kept (last 2 shown to the model, all kept in DB).
- **N10 · API reference doc** — every endpoint: what it does, params, response
  shape — in two registers: technical (for engineers) and plain-English (for
  PMs). Generated from the FastAPI app where possible so it can't go stale;
  lives in `docs/` + linked from the webapp How-it-works page.
- **N11 · Topic/keyword watch across sources** — Sources page grows a fifth
  kind: `keyword` (e.g. "MTF", "basket orders"). One keyword fans out to the
  sources the user ticks: X (added to search queries), Reddit (post-filter on
  fetched items + optional subreddit search), and it also tags matching items
  so Explore can filter by watched keyword. Efficient shape: keywords are a
  scrape-time filter for X (query term) and a clean-time matcher for Reddit
  (no extra fetches), with per-source enable flags in `watch_sources.category`
  or a small config jsonb.

## 2 · Execution phases (build + validate together)

| Phase | Items | Theme |
|---|---|---|
| **1** | B1, B2, N4, N1, N2 | Visibility quick wins — all frontend + small API additions |
| **2** | B3, B4, N3-followup (persist heads-ups) | Data correctness & persistence |
| **3** | N5 (plan → build), N6 | LLM observability (Langfuse + cost surfacing) |
| **4** | N8, N9 | Content controls (grounding editor, brief editing) |
| **5** | N11, E1 | Discovery (keyword watch, emergent topics + feature re-cluster) |
| **6** | N7, N10 | Education & docs (how-it-works page, API reference) |

Sequencing logic: 1 is pure surface (fast validation), 2 fixes counting/data
trust before observability starts measuring it, 3 before 4 so brief-editing
LLM calls are traced from day one, 5 rides on 2's item→key mapping, 6 last so
it documents the finished shape.

## 3 · Reports (the "reflect back" items)

### Postgres coverage audit (N3)

**In Postgres (system of record):** social_items, item_enrichment,
item_embeddings (pgvector), authors + author_stats (voices), conversations,
topic_daily + topic_taxonomy, issue_rollup, feature_rollup + feature_keys,
opportunities (incl. both drafts, status, novelty stamps), content_proposals
(briefs), roundups (daily AND weekly payload + delivery state),
compliance_audit, feedback, watch_sources, nubra_features (versioned),
pipeline_state (watermarks), schema_migrations. **19 tables — everything the
product shows is DB-backed.**

**On disk only (the gaps):**
1. **Hourly heads-up messages** — rendered markdown in `out/messages/` only;
   the DB has the novelty stamps but not the composed message. → approved fix
   in Phase 2 (store like roundups).
2. **LLM usage / stage traces** — stdout only. → closed by Phase 3 (N5/N6).
3. Raw Reddit scrape JSON (`out/reddit_scraper/`) — deliberate fetch cache,
   not a record; re-scrapable. Stays on disk.
4. `registry.yaml` + `.env` — config/secrets, git- and env-managed by design.
   Anything that must be UI-editable is already DB-backed (watch_sources,
   nubra_features after N8).

### Where clustering (HDBSCAN) pays off beyond `other:*` (E1)

| Candidate | Verdict | Why |
|---|---|---|
| `other:*` topics → new taxonomy suggestions | **DO (approved)** | 153 items / ~240 ad-hoc keys today; weekly cluster → INACTIVE topic suggestions, human activates |
| Feature-key maintenance (re-cluster phrases) | **DO (with B3)** | catches centroid drift + should-merge keys; produces the item→key mapping B3 needs anyway |
| Issue-type discovery (cluster complaints) | **LATER** | only 9 complaint items today — nothing to cluster; revisit at ~100+ |
| Voices micro-communities | **SKIP for now** | low product value vs cost; voices already rank well |
| Brief/hook dedup across days | **SKIP** | repetition guard cheaper via embedding similarity check at generation time |

## 4 · Parked (do NOT start; resurface after Phase 6)

- Auth (SSO/OIDC proxy + API header enforcement) — before rollout beyond team
- "Needs you" go-live set: Slack webhook + Gmail app password in `.env`,
  X credits top-up, `./cm schedule --install`, marketing's features catalog +
  keyword excel (`seed_features --from-xlsx` loader when it lands)
- Shadow run 1–2 weeks → scoring-weight re-tune (needs cron installed)
- Doc-sync pass over stale LLDs
- Prod deploy hardening (systemd/nginx/TLS, backups)
- Learned posting windows (E2) + posting-with-approval workflow + self-learning
  from feedback — chained prerequisites, in that order
- More sources (YouTube/Telegram/app reviews)
