# Nubra Community Manager — LLD-03: Recommend, Compliance, Delivery & Read-API

_LLD · 2026-07-03 · source of truth for build-plan milestones **M3 + M4 + M5**._
_Parents: `nubra-community-manager-architecture-2026-06-29.md` (§6–8) ·
`…-posting-and-roundups-2026-06-29.md` (all) · `…-data-flow-2026-07-03.md` (⑤a/⑤b/⑥/⑦) ·
`…-build-plan-2026-07-03.md` (M3–M5). Siblings: LLD-01 (data layer), LLD-02 (ingest→aggregate)._

All constants below live in `config/settings.yaml` under `recommend.*` / `compliance.*` /
`timing.*` / `delivery.*` — values here are the **v1 defaults**, not code literals.

## 0. Decisions made in this LLD (beyond the parent docs)

| # | Decision | Why |
|---|---|---|
| D1 | Priority = weighted sum of 5 signals, each normalized to [0,1], × 100 | simple, inspectable, tunable per-weight |
| D2 | One Sonnet call per opportunity generates **both** drafts (brand + rep) | half the calls; consistent facts across voices |
| D3 | Drafts validated by `features_cited[]` — every cited id must exist in `nubra_features` | machine-checkable grounding, not just prompt hope |
| D4 | Compliance regenerate loop: max **2** regenerations, then drop | bounded cost; a twice-failing thread isn't worth it |
| D5 | Heads-up novelty is **per thread**, not per topic: a thread is surfaced once/day, but a topic recurring in *new* threads re-enters with a recurrence boost (§1.1) | no re-ping spam on the same thread — yet sustained momentum (same topic, fresh threads) is the strongest signal and must keep surfacing, weighted up |
| D6 | Status transition is one-way: `suggested → acted \| dismissed`; anything else → 409 | keeps the future training signal clean |
| D7 | Content proposals: LLM generates ~8 candidates + self-scores; **deterministic** re-rank picks top 3 with a format-diversity constraint | ranking reproducible; LLM only proposes |
| D8 | API auth: OIDC at nginx (edge); FastAPI trusts `X-Auth-Request-Email`; DB via `community_ro` role | no auth logic in app code; matches "hardened Streamlit" plan |
| D9 | Draft-pass batch size: top **10** opportunities/day get drafts (config `recommend.max_drafted`) | matches cost model (~10 opps × 2 drafts) |

Open question for the team: final weight values after 2 weeks of shadow-run tuning.
(`dismissed` ships with a required reason enum in v1 — see §7.)

---

## 1. ⑤a Hourly scoring pass (no LLM)

Runs after `community:aggregate` (hourly, 06:00–01:00 IST). Input: `conversations` updated
in the last 24h (plus any conversation whose opportunity is still `suggested`). Output:
`opportunities` rows (priority, matched insight, `status='suggested'`) + the hourly
heads-up (§1.3, 08:00–20:00 IST only).

### 1.1 Priority formula

```
priority = 100 · Σ wᵢ · sᵢ        (each sᵢ ∈ [0,1]; weights sum to 1)
then: if thread already surfaced in a prior roundup → priority × 0.4
      if opportunity status ∈ {acted, dismissed}   → skip (never re-score)
      if NEW thread on a topic already featured in a heads-up today
        (topic_daily.headsup_count ≥ 1)
          → priority × (1 + min(0.05 · headsup_count, 0.15))
            -- RECURRENCE BOOST: a topic still gaining traction across fresh threads
            -- is MORE relevant, not stale — it re-enters the next heads-up, weighted up
```

| Signal | w (default) | sᵢ definition |
|---|---|---|
| `freshness_velocity` | 0.25 | `0.5·min(conv_accel/4, 1) + 0.5·exp(−age_h/12)` — accelerating AND young |
| `relevance` | 0.30 | base by matched insight: competitor issue we solve **1.0** · feature we satisfy **0.9** · genuine question in-domain **0.7** · rising topic only **0.4**; + **SEO boost** `+0.1` per `nubra_features.seo_keywords` hit in thread text (cap `+0.2`); clamp 1.0 |
| `reach` | 0.15 | `min(log10(1 + max_author_followers ∨ views)/6, 1)` — 1M+ ⇒ 1.0 |
| `opportunity_type` | 0.15 | complaint-about-competitor **1.0** · feature_request we satisfy **0.9** · question/how_to **0.8** · comparison **0.7** · news/opinion **0.3** |
| `author_quality` | 0.15 | `voice_score` normalized [0,1]; if `authenticity_flag` → × 0.3 |

**Naming (two different velocities):** `conv_accel` = `conversations.velocity` — the
thread's own 3-hour acceleration ratio (LLD-02 §8.1); `velocity_z` = the daily z-score of
the conversation's `dominant_topic_key` in `topic_daily` (NULL → 0 in cold-start). The
freshness signal uses the *thread's* acceleration; topic-level rise feeds `relevance` and
the timing rule.

Thresholds (config `recommend.thresholds`): **≥ 70** → next heads-up + top of roundup ·
**40–69** → secondary section · **< 40** → not persisted (noise).

### 1.2 Nubra-watch diversion

Before scoring: if `conversations.is_nubra_watch` (set by aggregate when any item's
gazetteer-linked `entities.broker == 'nubra'` — LLD-02 §8.1) → **divert**. No opportunity,
no drafts. Instead:

- tag sub-type from dominant intent: `complaint | question | praise | mention`;
- **always included in the next heads-up** (regardless of priority — a grievance never
  waits), deduped per `thread_id`/day (D5);
- `complaint`/`question` → posted plainly to the alerts channel for now;
  `delivery.nubra_watch_mention` **defaults to empty** — set it later to add an
  @-mention (e.g. `@community-support`) to the route line.

### 1.3 Hourly heads-up (Slack + email · 08:00–20:00 IST)

Fires after each ⑤a pass inside the window. Two parts every time: an **actions section**
(what to look at, sorted by weight) and an **ops summary** (what the system did in the
last hour).

**Actions section — novelty + recurrence (D5):**
- new priority-≥70 opportunities — `opportunities.pinged_at IS NULL`, stamped on send;
- new Nubra mentions — `conversations.headsup_at IS NULL OR < start-of-today IST`,
  stamped on send;
- topics newly crossing `velocity_z ≥ 1.5` today — `topic_daily.headsup_at IS NULL` on
  today's row, stamped on send (`headsup_count` incremented on every inclusion);
- **recurring momentum** — a topic already featured today that keeps gaining traction in
  a *new* thread re-enters via that thread's opportunity, carrying the recurrence boost
  (§1.1) and a marker line, e.g. `↗ algo_trading — still rising, 3rd thread today`.

**Ordering:** action items are sorted by final (boosted) priority, descending — the
recurrence boost naturally floats sustained topics to the top.

**Ops summary — the "what happened last hour" framework**, computed from
`pipeline_state`, window counts on `social_items`/`item_enrichment` (arrival clocks),
`conversations`, `topic_daily`, `opportunities`, and `llm_usage`:

| Field | Source |
|---|---|
| fetched per source | `pipeline_state.items_last_run` per `(ingest, source)` |
| after dedup / dupes linked | `social_items` in window, `duplicate_of` split |
| noise filtered (rule + LLM) | `item_enrichment.is_noise` in window, by `model` |
| enriched | `item_enrichment` rows in window |
| new conversations · topics rising | `conversations.first_seen` in window · `topic_daily` crossings |
| opportunities scored (new ≥70) | `opportunities` created/updated in window |
| Nubra mentions | `conversations.is_nubra_watch` new in window |
| LLM spend today | `llm_usage` day sum |

**On empty actions:** a compact **ops-only digest** still posts (config
`delivery.headsup_on_empty: ops_summary | skip`, default `ops_summary`) — the team sees
the system is alive and what it processed; the full-size message fires only when there
are actions. `skip` restores the earlier silent behavior if the hourly cadence proves
noisy.

Delivery: Slack to `delivery.slack_alerts_channel` (separate from the roundup channel)
plus the same content as a short email (Gmail SMTP, app password) to `delivery.headsup_recipients`.

```
🔥 HOT THREAD  ·  priority 84  ·  r/IndianStockMarket  ·  2.1k views · +40%/hr
“Zerodha order rejections again today?? third time this expiry…”
insight: broker-issue (zerodha · order_reject, rising 3d)  ·  age 4h
→ drafts land in tomorrow 07:30 roundup — engage sooner? thread: <url>
─
↗ STILL RISING  ·  priority 78 (boosted ×1.10)  ·  algo_trading — 3rd new thread today
“anyone actually making money with algo on Indian brokers?”  ·  X · 800 views
→ sustained momentum since the 11:00 heads-up. thread: <url>
─
🟠 NUBRA MENTION (complaint)
“@nubra app not showing my P&L since morning”  ·  X · 12 replies
→ routed to support — do NOT engage from marketing. thread: <url>
─
📊 LAST HOUR · 14:00–15:00 IST
fetched 214 (X 130 · Reddit 84) → 197 kept (17 dupes linked) · 22 noise-filtered
enriched 175 · 6 new conversations · 2 topics rising · 3 opportunities scored (1 new ≥70)
Nubra mentions: 1 · LLM spend today: $0.41
```

One message per firing (batched blocks), max 5 opportunity blocks + all Nubra-watch
blocks; overflow noted as "+N more in dashboard".

---

## 2. ⑤b Daily draft pass

With the daily build. Select `status='suggested' AND priority ≥ 40` from the last 36h,
order by priority, take top **10** (D9). Each gets ONE Sonnet call → both drafts.

**Cost mechanics (cost plan §2.1/§2.4):** the *independent* generation calls — 10 drafts
+ the content-proposal candidates call — are submitted as one **Anthropic Batch API job
at 06:45 IST**, as the tail of the morning-build sequence (arch §8) (−50%; sync fallback
at 07:15 if the batch hasn't ended — results keyed by `custom_id`). The *dependent* calls — L2 compliance reviews of those outputs,
regenerations, roundup synthesis — run **sync afterwards** (they consume the batch's
outputs, ~$0.15/day, not worth the deadline risk). The shared prefix (system prompt +
serialized `nubra_features`) carries `cache_control`, so the sync compliance/regeneration
calls read it at 0.1×; inside the batch, cache hits are best-effort.

### 2.1 Prompt structure (per opportunity)

```
SYSTEM
You draft social replies for Nubra, a SEBI-regulated Indian stock broker.
HARD RULES:
- Assert ONLY facts present in NUBRA_FEATURES below. No other Nubra claims.
- status="upcoming" features: phrase as "coming soon" — never a promise or date.
- No investment advice, no buy/sell/target/SL language, no return figures.
- Never disparage a competitor by name; speak to the problem, not the brand.
- Educational, factual, conversational. India context, INR, IST.
- The text may be Hinglish if the thread is — mirror the thread's register.

USER
NUBRA_FEATURES (is_current=true):        # JSON rows: id, feature, description, status, category
[...]
CONVERSATION (root + top replies, ≤1500 chars):
[...]
MATCHED_INSIGHT: {kind: broker_issue, broker: zerodha, issue_key: order_reject, trend: rising_3d}
TASK: produce a BRAND reply and a REP reply per the JSON schema.
BRAND = official Nubra voice: crisp, factual, USP-led.
REP   = human persona: curious, peer-to-peer, helpful, soft pull; MUST include the
        disclosure line verbatim: "Full disclosure — I'm part of the team at Nubra."
```

### 2.2 Output schema (validated; retry once on schema failure)

```json
{
  "brand": { "text": "...", "features_cited": ["f_012", "f_031"] },
  "rep":   { "text": "...", "features_cited": ["f_012"], "disclosure_included": true },
  "skip_reason": null
}
```

Post-validation (code, not LLM): every `features_cited` id exists and `is_current`;
`rep.text` contains the disclosure string; any "coming soon"-phrased sentence maps to a
`status='upcoming'` row; a draft naming a capability with empty `features_cited` →
regenerate. `skip_reason` lets the model decline (e.g. thread turned hostile) — logged,
opportunity kept without drafts.

---

## 3. Compliance gate (applied to replies AND content proposals)

```
draft ─▶ L1 rules (deterministic) ─▶ L2 Sonnet review ─▶ pass → store
   ▲            │fail                       │fail
   └────────────┴── regenerate with violation feedback (max 2, D4) ── still failing → DROP
every attempt × layer → compliance_audit(draft_ref, layer, verdict, reason, ts)   · kept 180d
```

### 3.1 L1 deterministic denylist (v1 starting set; case-insensitive; config-extendable)

| Rule id | Pattern (regex, abridged) | Catches |
|---|---|---|
| `l1.returns` | `\b(guarantee\w*|assured|risk[- ]?free)\b.{0,40}\b(returns?|profits?|income)\b` · `\b\d{1,3}\s?%\s*(returns?|profits?|gains?)\b` | guaranteed/assured/X% returns |
| `l1.tips` | `\b(intraday|stock|option|F&O)?\s*(tips?|calls?)\b` · `\byou should (buy|sell|short)\b` | tips/calls, direct advice |
| `l1.targets` | `\b(target|tgt)\s*[:=]?\s*(₹|rs\.?)?\s?\d` · `\b(SL|stop[- ]?loss)\s*[:=]?\s*(₹|rs\.?)?\s?\d` | price targets, SL/target patterns |
| `l1.sureshot` | `\b(sure[- ]?shot|jackpot|multibagger|pakka profit)\b` | hype vocabulary |
| `l1.pii` | `\b[6-9]\d{9}\b` (IN mobile) · email regex · `\b[A-Z]{5}\d{4}[A-Z]\b` (PAN) | PII leakage |
| `l1.shaming` | `(zerodha|groww|upstox|dhan|angel one)\W{0,20}(scam|fraud|chor|loot|thie\w+)` | naming-and-shaming |
| `l1.promise` | `\b(will|by)\s+(launch|release)\w*\s+(on|in)\s+\w+` when near an `upcoming` feature name | dated promises on upcoming features |
| `l1.shared` | imported from the vendored comms guardrails (LLD-02 §6.6): `_FEAR_PHRASES`, `_BUY_SELL_CALL_PATTERNS`, crypto denylist | one safety vocabulary across push + community surfaces |

Any hit → fail with rule id + matched excerpt (the `reason` in `compliance_audit`).

### 3.2 L2 Sonnet review

Temperature 0. Input: the draft + a fixed SEBI/ASCI checklist (advice, inducement,
unsubstantiated claims, disclosure present for rep, comparative-advertising fairness,
tone). Output schema:

```json
{ "verdict": "pass" | "fail",
  "violations": [ { "rule": "sebi.no_advice", "excerpt": "...", "reason": "..." } ],
  "confidence": 0.0 }
```

`fail` → violations are appended to the regeneration prompt ("your previous draft failed
compliance because: …"). L3 remains the human reading the roundup.

---

## 4. When-to-post timing

Exact rule tree (evaluated at draft time; thresholds in `timing.*`):

```
if (conv_accel ≥ 2 or topic velocity_z ≥ 1.5) and age_h < 12
                                            → {action:"now",      window:"live"}
elif topic_taxonomy.evergreen               → {action:"schedule", window: best_window(format)}
elif age_h < 24                             → {action:"today",    window: next_window(now_ist)}
else                                        → {action:"schedule", window:"08:30–09:15"}   # next pre-open
```

Windows (config `timing.windows_ist`, from posting doc §5): pre-open `08:30–09:15` ·
open `09:15–10:00` · post-close `15:30–17:00` · evening `20:00–22:30`.
`best_window(format)`: reel/short → evening; explainer/infographic → pre-open; issue
response → post-close.

```json
"recommended_timing": { "action": "now|today|schedule",
                        "window": "live" | "HH:MM–HH:MM IST",
                        "why": "thread +40%/hr, 4h old" }
```

---

## 5. Content proposals (top 3, always on)

One Sonnet call with the day's signal (top 5 rising topics + velocity, top issues, top
feature requests) → **~8 candidates**, each self-scored 0–1 on `impact · reach_fit ·
effort (inverse) · timeliness · on_brand`. Then deterministic (D7):

```
score = 0.30·impact + 0.25·reach_fit + 0.20·timeliness + 0.15·effort_inv + 0.10·on_brand
rank desc → enforce diversity (≤2 of the same format in top 3) → keep 3
→ each passes the compliance gate (§3) before persisting to content_proposals
```

```json
{ "rank": 1, "format": "reel|short|infographic|thread|post",
  "hook": "...", "outline": ["...", "..."],
  "rides_signal": {"topic_key": "fo_expiry", "velocity_z": 2.3},
  "why": "...", "recommended_window": "20:00–22:30 IST", "scores": { } }
```

---

## 6. Roundup + delivery (M4)

### 6.1 `roundups.payload` (daily; weekly adds `deltas`)

```json
{ "period": "daily", "date": "2026-07-03",
  "trending":        [ {"topic_key":"", "label":"", "velocity_z":0, "spread":0, "sample_urls":[]} ],
  "broker_issues":   [ {"broker":"", "issue_key":"", "count":0, "trend":"rising|stable|new", "severity":0} ],
  "feature_requests":[ {"feature_key":"", "label":"", "count":0, "days_requested":0} ],
  "opportunities":   [ {"id":0, "priority":0, "url":"", "insight":{}, "brand_draft":"",
                        "rep_draft":"", "recommended_timing":{}, "status":"suggested"} ],
  "content_proposals": [ {"rank":0, "format":"", "hook":"", "outline":[], "why":"",
                          "rides_signal":{}, "recommended_window":""} ],
  "nubra_watch":     [ {"kind":"complaint", "url":"", "summary":"", "routed_to":"support"} ],
  "rising_voices":   [ {"handle":"", "source":"", "voice_score":0, "why":""} ],
  "stats": {"items_ingested":0, "conversations":0, "pings_sent":0, "drafts_dropped_compliance":0} }
```

Weekly: see §6.3 (Sat→Sat framework with last-week persistence weighting).

### 6.2 Synthesis + delivery

- **Sonnet synthesis** turns the payload into the narrative digest (one call): 2-line
  headline summary, then sections in the §6.1 order; terse, scannable, no new facts
  (payload-grounded — same rule as replies).
- **Slack**: Block Kit — header (`📡 Community Roundup — Thu 3 Jul`), context stats line,
  sections; each opportunity = one block (priority badge · draft snippets in a code block ·
  timing · dashboard deep-link). Nubra-watch section always last (plain post;
  an @-mention is added only when `delivery.nubra_watch_mention` is set — empty in v1).
- **Email (Gmail SMTP, app password)**: same sections as HTML (blue-dark inline styles), full drafts included —
  the archive copy.
- `roundups.delivery` = `{"slack": {"status":"sent","ts":"","attempts":1}, "email": {...}}`.
  3 attempts, exponential backoff (30s/2m/10m); any channel still failing → alert to the
  alerts channel (Slack down → email the alert, and vice versa). Roundup row is written
  **before** delivery attempts (payload never lost).

### 6.3 Weekly roundup — Sat→Sat framework

Fires **Saturday ~10:00 IST**; window = previous Saturday 00:00 IST → this Saturday
00:00 IST. It presents the **highlights of the week**, ranked with a **last-week
persistence weighting**: before ranking, load last week's weekly payload
(`roundups WHERE period='weekly'`, previous date) and boost any topic / broker-issue /
feature-request that also appeared there —

```
weekly_rank_score = week_metric × (1 + 0.25 · min(weeks_running − 1, 3))
   week_metric   = count/engagement over the Sat→Sat window (per section)
   weeks_running = consecutive weekly roundups the item has appeared in (from prior
                   payloads; capped at 4 → max boost ×1.75)
```

Payload sections (each item carries `weeks_running` so persistence is visible):

```json
{ "period": "weekly", "window": {"from": "2026-06-27", "to": "2026-07-04"},
  "highlights":        [ "3–5 synthesized one-liners — the week in one glance" ],
  "persisted":         [ {"kind":"topic|issue|feature", "key":"", "label":"",
                          "weeks_running":2, "wow_delta":"+40%"} ],
  "new_this_week":     [ {"kind":"", "key":"", "label":"", "count":0} ],
  "topic_movers":      [ ], "persisted_issues": [ ],
  "consistent_features": [ ],   // requested ≥4 of 7 days
  "voices_to_build":   [ ],
  "actions_recap":     {"headsups_sent":0, "opportunities_surfaced":0, "acted":0,
                        "dismissed_by_reason":{}, "drafts_gated":0, "items_processed":0}
}
```

`actions_recap` is the week-level ops summary — same framework as the hourly ops block,
aggregated Sat→Sat (includes what the team did: acted/dismissed counts from
`opportunities.status`).

### 6.4 Message templates — customizable, no code deploy

Every outbound message renders from a **Jinja2 template** in
`community/delivery/templates/` — editing copy, ordering, or which fields show is a
template change, not a code change:

| Template pair (slack `.j2` + email `.j2`) | Context variables (the contract) |
|---|---|
| `headsup_*` | `window` · `actions[]` (sorted by boosted priority; each: `kind`, `priority`, `boost_note`, `title`, `insight`, `age`, `url`) · `nubra_watch[]` · `ops` (the §1.3 ops-summary fields) · `is_ops_only` |
| `roundup_daily_*` | the §6.1 payload, verbatim |
| `roundup_weekly_*` | the §6.3 payload, verbatim |

Rules: the **context dict is the stable contract** (code side); templates may use any
subset. Templates are validated in CI by rendering each against a fixture payload
(`tests/fixtures/delivery/*.json`) — a broken template fails the build, never a 3am
send. Slack templates emit Block Kit JSON; email templates emit inline-styled HTML
(blue-dark).

---

## 7. Read-API (FastAPI, M5)

Base `/api/v1`. All GETs read via `community_ro`. Common filters: `from`, `to` (ISO dates),
`source`, `limit` (default 20, max 100). Errors: RFC-7807 JSON.

| Endpoint | Params | Returns |
|---|---|---|
| `GET /trends` | `date`, `window=1d\|7d`, `limit` | `[{topic_key, label, count, velocity_z, spread, engagement_sum}]` |
| `GET /issues` | `broker`, `from`, `to` | `[{broker, issue_key, day_counts[], severity, sentiment_avg, sample_item_ids[]}]` |
| `GET /features` | `from`, `to`, `min_days` | `[{feature_key, label, count, days_requested, brokers_mentioned[]}]` |
| `GET /voices` | `limit`, `min_score` | `[{author_id, handle, source, voice_score, contributions, authenticity_flag}]` |
| `GET /opportunities` | `date`, `status`, `min_priority` | `[{id, thread_id, url, priority, insight, brand_reply, rep_reply, recommended_timing, status}]` |
| `GET /content-proposals` | `date` | the day's ranked 3 (schema §5) |
| `GET /roundups` | `period`, `date` | `payload` + `delivery` |
| `GET /items` | `topic`, `broker`, `intent`, `audience`, `q`, `min_engagement`, paging | drill-down list (joins `item_enrichment`; canonical items only, `duplicate_count` included) |
| `GET /items/{source}/{external_id}` | — | full item + enrichment + thread siblings |
| `POST /feedback` | body `{object_ref, category, free_text}` | 201; category ∈ config enum |
| `POST /opportunities/{id}/status` | body `{status: "acted"\|"dismissed", dismissed_reason?}` | 200; **only from `suggested`** else 409 (D6); `dismissed_reason` **required when dismissing** (enum `not_relevant\|already_handled\|too_late\|too_risky\|other`, else 400); writes `status`, `dismissed_reason`, `status_updated_by` (SSO email), `status_updated_at` |

**`url` on opportunities is derived at read time** — `conversations.root_item_id →
social_items.url` — it is not stored on `opportunities` (same derivation for the roundup
payload and the heads-up).

**Auth (D8):** nginx `oauth2-proxy`/OIDC at the edge; API only on the internal net; trusts
`X-Auth-Request-Email` header (rejected if absent); that email lands in `status_updated_by` /
`feedback.submitted_by`. DB roles: `community_ro` + `INSERT ON feedback` +
`UPDATE (status, status_updated_by, status_updated_at, dismissed_reason) ON opportunities`.

## 8. Dashboard (Streamlit, M5)

| Page | Backed by | Notes |
|---|---|---|
| Overview | `/roundups` | today's digest rendered; links into every other page |
| Trends | `/trends` | velocity chart per topic; date/window filter |
| Broker issues | `/issues` | broker × issue matrix, trend sparklines |
| Feature requests | `/features` | persistence view ("requested N of last 7 days") |
| Opportunities | `/opportunities` | priority-sorted; **Acted / Dismiss buttons** (Dismiss opens a reason picker — the enum) → `POST …/status`; drafts copy-to-clipboard |
| Content | `/content-proposals` | top-3 cards with window + rides-signal |
| Voices | `/voices` | table + authenticity flags |
| Drill-down | `/items` | global filters (date·source·topic·broker·intent·audience·min-engagement) → item list → `/items/{…}` detail |

Every page: sidebar filters + a **feedback widget** (category select + free text →
`POST /feedback` with the page's `object_ref`). All reads through the API only —
`st.cache_data(ttl=300)`; **no live fetching**, no direct DB access from the dashboard
process. Theme: `config.toml` + injected `design_system.css` (blue-dark).
