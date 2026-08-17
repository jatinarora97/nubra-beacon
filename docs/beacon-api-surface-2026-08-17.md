# Beacon API surface — full component map (2026-08-17, plan only)

Lens change (user, 2026-08-17): WE define the API surface for every Beacon
component, not just the 7 endpoints the team asked for. Consumer = an MCP
agent that fetches data for one or more sources in a date range.

Supersedes workstream 2 scope in `beacon-expansion-plan-2026-08-14.md`
(auth/keys/rate-limit/cursor/kill-switch design there still stands verbatim).

## Global rules (every endpoint, designed for an LLM consumer)

1. Common params everywhere: `sources` (comma list, default ALL),
   `since`/`until` ISO8601. **Default range = the current IST calendar day**
   (Beacon thinks in IST trading days; agents override freely).
2. Same envelope everywhere: `{ "results": [...], "next_cursor": ... }`,
   keyset cursor, stable ordering.
3. **Compact by default** — an MCP agent burns context on every byte. Text
   truncated to 300 chars, `raw` omitted; `?detail=full` or the single-item
   endpoint returns everything. Default `limit` 25 (cap 200).
4. `GET /taxonomy` is the discovery key: valid topics, intents, issue types,
   brokers, sources, audiences — so the agent filters by real enum values
   instead of hallucinating them.
5. Read-only v1. Write actions (ack a recommendation, edit a brief, add a
   watch source) are a deliberate v2 decision — flag, don't build.

## Component map — every Beacon component and its API

### A · Corpus — what people said (backed by social_items + item_enrichment)

| Endpoint | Answers | Notes |
|---|---|---|
| `GET /items` | "everything posted about X since Y" | filters: sources, since/until, topic, intent, audience, broker, sentiment_min/max, q, min_engagement, include_noise (default false), has_transcript |
| `GET /items/search` | "posts saying THIS phrase" | websearch syntax (OR, quotes) + match_snippet; GIN index migration |
| `GET /items/{source}/{external_id}` | one item, everything | full text (incl. TRANSCRIPT/ON-SCREEN), enrichment, thread siblings, raw, tier status |

### B · People — who said it (backed by authors)

| Endpoint | Answers | Notes |
|---|---|---|
| `GET /authors` | "who talks about this" | per-author item_count, first/last seen, top topics, avg engagement; filters: sources, q, min_items, since |
| `GET /authors/{source}/{handle}` | one voice in depth | profile + recent items + topic mix (the Voices page, as JSON) |

### C · Intelligence — what Beacon concluded (backed by the rollups the dashboard renders)

| Endpoint | Answers | Notes |
|---|---|---|
| `GET /trends` | "what's moving" | window hourly/daily/custom, score + delta_vs_prev + item_ids, same math as Trends page |
| `GET /broker-issues` | "what's broken where" | broker × issue_type segments, mention_count + engagement_sum, representative quotes, item_ids |
| `GET /feature-requests` | "what people wish existed" | feature_rollup + exactly-once mention counts, item_ids |
| `GET /nubra-mentions` | "what they say about US" | the Nubra mentions page as JSON (brand hits across sources, sentiment split) |
| `GET /topic-suggestions` | "themes Beacon discovered on its own" | HDBSCAN candidates + status (proposed/accepted) |

### D · Action layer — what Beacon recommends (recommend/compose/dispatch)

| Endpoint | Answers | Notes |
|---|---|---|
| `GET /opportunities` | "top actionables + WHY" | score (bar 60), reason components (engagement/recurrence/audience/intent), status, linked draft id |
| `GET /drafts` | "the compliant reply, ready" | by opportunity or date; guardrail status |
| `GET /briefs` | "today's content briefs" | by day; format_family, platform, edit state, repetition-judge verdict |
| `GET /social-recommendations` | "posts the social engine suggests" | grounding-version stamped |
| `GET /roundups` | "the hourly heads-up / weekly wrap as data" | period=hourly/daily/weekly, stored messages + week-in-numbers stats |

### E · Ops + meta — is Beacon healthy, what does it know, what does it cost

| Endpoint | Answers | Notes |
|---|---|---|
| `GET /runs` | "is the data fresh" | pipeline_state per stage×source: watermark, last success/error, items_last_run |
| `GET /source-health` | "are collectors alive" | `?live=true` adds real probes (Apify credits, API reachability) |
| `GET /watch-sources` | "what does Beacon listen to" | the 123-row watch list (subreddits, handles, queries, instagram accounts) |
| `GET /taxonomy` | "what filter values exist" | topics (live, incl. HDBSCAN-accepted), intents, issue_types, brokers, sources, audiences |
| `GET /grounding` | "what can Nubra actually do" | current context version + 31 features — lets the agent ground replies exactly like our compose stage does |
| `GET /usage` | "what is Beacon spending" | llm_usage rollup (tokens, $ by stage/model) + Apify run costs |

Components with NO partner API on purpose: compliance_audit (internal
evidence trail), feedback intake (dashboard-only), clean/dedup internals
(invisible by design — consumers see deduped output).

## Why this shape works for an MCP agent

1. One endpoint = one MCP tool; the "Answers" column above IS the tool
   description. ~19 tools across 5 families.
2. Aggregates-first: the agent answers "what happened today" from C/D
   endpoints (cheap, small), drilling into A only for receipts —
   `item_ids[]` on every rollup row is the drill-down key.
3. `taxonomy` + `grounding` remove the two classic agent failure modes:
   invented filter values and invented product facts.
4. Same-day IST default means the lazy call ("what's up?") is also the
   correct call.
5. Optional follow-up (not in scope): we ship the MCP server ourselves — a
   thin wrapper, one tool per endpoint. Half a day, zero new logic. Decide
   after the REST layer is live.

## Build phases (auth/keys/limits/audit from the expansion plan apply as-is)

1. Phase 1 (1 day): plumbing (keys, cursor, envelope, taxonomy) + family A
   + `/runs`. The MCP agent can already answer "find and quote".
2. Phase 2 (1 day): family C + D — trends, issues, features, mentions,
   opportunities, drafts, briefs, roundups. The agent can answer "so what?".
3. Phase 3 (0.5 day): family B + remaining E (authors, watch-sources,
   grounding, usage, source-health) + dashboard API-doc page section.
4. Phase 4 (0.5 day, optional, decide later): our own MCP server wrapper.

Total ~2.5 days REST (+0.5 optional MCP wrapper).

## LOCKED decisions (user, 2026-08-17)

1. All 19 endpoints approved.
2. **Default date range = rolling 24h** (`ingested_at >= now() - 24h`) —
   marginally simpler than IST-day (no timezone math), and user's tiebreak
   rule said rolling wins.
3. **Read-only v1.** Writes are v2.
4. **MCP server is their side.** Phase 4 dropped. Our deliverable =
   functional REST + the contract doc.
5. **Auth = per-consumer API keys** (not one shared key). Same code either
   way; per-consumer means: revoke one leaker without breaking others,
   per-key rate limits, and the audit log says WHO pulled what. Mechanics:
   `scripts/mint_api_key.py` prints the secret once, DB stores only
   sha256(secret); caller sends `X-API-Key: <secret>`; middleware hashes and
   looks it up; unknown/revoked → 401. Issuing = we run the script per team
   and hand each their key.
6. **Full data by default** (compact-by-default REVERSED): full text, all
   enrichment, `raw` included. Only internal pipeline bookkeeping stays
   stripped from raw (s3_* keys, transcript_state, tiers_done — our plumbing,
   not their data). Default limit stays 25 (cap 200) purely as a page size.
7. `external_id` = the platform's own id for the item — the second half of
   our (source, external_id) uniqueness pair, returned on every /items row
   (copy it from a list response into the detail call). Examples: X tweet id
   `1823...90`, reddit `t3_1abcd2`, youtube `yt_video_dQw4w9`, instagram
   shortCode `DJJFNA-BV7f` (from instagram.com/p/DJJFNA-BV7f/), app review
   id, github issue node.
8. "Aggregates-first" framing dropped (it was usage guidance, not a
   feature). **Cursor pagination stays on every list endpoint** as designed:
   `next_cursor` opaque keyset, stable ordering. Rollup rows keep whatever
   item links their tables already store (free); no extra cross-linking
   work.

Next action: user says "go" → Phase 1 (plumbing + corpus family + /runs).
