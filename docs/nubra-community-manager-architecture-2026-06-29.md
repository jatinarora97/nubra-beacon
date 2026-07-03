# Nubra Community Manager — Production Architecture

_Design · 2026-06-29 · companion: `nubra-community-manager-posting-and-roundups-2026-06-29.md`_

A always-on system that **listens** across social platforms, **understands** what the
Indian trading community is saying, and **recommends** — what's trending, what's breaking,
what people want, what we should say, when, and what we should make. The current
Streamlit + SQLite + Reddit/X-CSV thing is the **POC**; this is the production target.

**Scope:** _listen → understand → recommend_, ending at a **read-only roundup** (Slack +
email). The recommendation includes **when to post** (timing intelligence). Actually
*posting* (and the approval workflow) is **out of scope** — see
[Future additions](#13-future-additions).

**Design spine:** _pluggable source adapters_ in front of a _stable canonical pipeline_.
Add a source → nothing downstream changes.

```
 ┌── ① SOURCES (pluggable) ─────────────────────────────────────────────┐
 │  IN SCOPE:  X/Twitter (paid) · Reddit                                 │
 │  LATER:     GitHub · YouTube · Discord · Telegram · App-store reviews │
 │  (SEO keywords live in nubra_features (versioned) — refine each        │
 │   source's search: recall boost, not a filter)                        │
 └───────────────────────────────┬──────────────────────────────────────┘
                                  ▼
        ② ADAPTERS   normalize every source → one SocialItem
                                  ▼
        ③ STORE      Postgres: append + dedup (hash + LSH)
                                  ▼
        ④ ENRICH     one batched LLM pass: audience · intent ·
                     topic-key · entities   (+ embeddings)
                                  ▼
        ⑤ AGGREGATE  conversations · topic velocity · issue/feature rollups · voices
                                  ▼
        ⑥ RECOMMEND  rank opportunities · brand+rep talking points (grounded on
                     nubra_features) · WHEN-TO-POST · content proposals (top 3) · compliance
                                  ▼
        ⑦ DELIVERY   Daily + Weekly roundup → Postgres  ──▶  Slack + Email (read-only)
                                                        └──▶  read-only Dashboard (filters)

        ┄┄ posting / human-approval workflow → Future additions ┄┄
```

---

## 1. POC → Production: what actually changes

| Concern | POC (today) | Production |
|---|---|---|
| Store | SQLite + a CSV | **own Postgres DB** (`nubra_community`) on Nubra's Postgres server + S3 + pgvector |
| Run model | manual button | **scheduled, headless** (EventBridge → webhook triggers) |
| Sources | Reddit (live), X (CSV) | registry: **X + Reddit** in scope; GitHub/YouTube/Discord/Telegram/app-reviews later |
| Dedup | O(n²) Jaccard | **hash + MinHash-LSH** (§5.1) |
| Topics | keyword label | **stable taxonomy keys + velocity** (§5.2) |
| Enrichment | 1 Haiku call (label only) | 1 batched call: audience + **intent** + topic + **entities** + embed |
| Output | on-screen tabs | **6 outputs + a Nubra-watch segment**, in a daily + weekly Slack/email roundup |
| Frontend | click-to-fetch pipeline | **read-only dashboard** over Postgres (filters, drill-down); writes only `feedback` + opportunity `status` (acted/dismissed). Skinned with Nubra's `blue-dark` palette |
| Posting | none | none (out of scope); we recommend *timing*, a human acts |

---

## 2. Source adapters (the only thing that varies)

```
   Adapter contract (every source implements this)
   ┌────────────────────────────────────────────────────────┐
   │  fetch(window, cursor) -> Iterable[SocialItem]          │
   │  capabilities: search? replies? threads? rate · $cost   │
   └────────────────────────────────────────────────────────┘
   registry.yaml (enabled · cadence · budget) → adapters → normalize() → social_items
```

**`SocialItem`** (canonical; the POC's `RawItem`, hardened). New vs POC: `parent_id` +
`thread_id` (so we can rebuild conversations), `lang`, `author_meta`.

| field | notes |
|---|---|
| `source`, `source_type` | reddit/twitter/discord · post/comment/tweet/reply/message |
| `external_id`, `parent_id`, `thread_id` | identity + **thread reconstruction** (§5.3) |
| `content_hash` | normalized-text sha256 (exact-dup match key — indexed, **not unique**: same text from two authors = two rows) |
| `author`, `author_meta` | handle + followers/verified/karma (Rising Voices) |
| `text`, `lang`, `url`, `created_at` | content (`created_at` = source time) |
| `ingested_at`, `duplicate_of`, `minhash_sig` | set at write: arrival time (**the watermark clock**, §3) · canonical-item link (§4.1) · persisted MinHash signature (§4.1) |
| `engagement` | jsonb; normalized `score` + native counts |
| `raw` | jsonb; full payload, lossless |

**Adding a source = write `fetch()`, map to `SocialItem`, add a registry row.** Nothing
downstream changes (X already proves this — same pipeline as Reddit).

**In scope (v1):**

| Source | Access | Cadence | Threads? |
|---|---|---|---|
| X / Twitter | twitterapi.io (paid, $-capped) | 4×/day (06/11/15/20 IST) | `conversation_id` |
| Reddit | Playwright / public | hourly | post→comments |

**Later** (drop-in adapters, same contract): GitHub issues (REST) · YouTube (Data API
comments) · Discord (invited bot, §2.1) · Telegram (Telethon public) · App-store/Play reviews.

**SEO keyword refinement:** SEO keywords are stored **inside `nubra_features`** (as a
versioned attribute on each USP/upcoming-feature row — see §5). They **expand** each
source's search (higher recall on what we care about) and **boost** ranking — never
hard-filter. Full blast radius stays; if keywords hit, great, otherwise we keep whatever's
relevant.

### 2.1 (Later) How Discord conversations are fetched (researched, for when we add it)

No ToS-compliant way to scrape arbitrary servers — but a sanctioned path exists, the only
one we use:

```
   Nubra read-only Discord BOT (own app + bot token)
     ① admin invites it into a public trading/algo server we want to listen to
     ② Gateway = realtime new messages   ③ REST GET /channels/{id}/messages = backfill
        → discord_adapter → SocialItem
```

- **Message Content** is a **privileged intent** — enable in portal + code or `content`
  comes back empty. Auto under 100 servers; **verification + approval** beyond.
- Bot needs `VIEW_CHANNEL` + `READ_MESSAGE_HISTORY`; can only read servers it's **invited**
  to (so we curate & join public Indian trading communities).
- **Excluded (ToS-violating, ban risk):** selfbots and user-token tools like
  DiscordChatExporter.

_Sources:_ [Message Content intent FAQ](https://support-dev.discord.com/hc/en-us/articles/4404772028055)
· [#5412 privileged](https://github.com/discord/discord-api-docs/discussions/5412)
· [selfbots violate ToS](https://grokipedia.com/page/discord-selfbot).

---

## 3. Canonical pipeline (downstream-invariant)

```
 ingest ─▶ normalize+dedup ─▶ [social_items] ─▶ enrich (1 batched LLM call) ─▶ aggregate ─┐
 per-src   hash + MinHash-LSH                   audience·intent·topic_key·     conversations│
 (cursor)  (§5.1)                               entities + embedding           velocity     │
                                                                               rollups      │
                                                                                            ▼
                                          ┌──────────────── recommend (⑥) ───────────────┐
                                          │ opportunities · talking points · timing ·     │
                                          │ content proposals(3) · compliance             │
                                          └─────────────────────┬─────────────────────────┘
                                                                ▼
                                       [ opportunities · content_proposals → roundups ]
```

**One enrichment call per item-batch** (Haiku) returns all of: `audience`, `intent`,
`topic_key`, `entities` → keeps LLM cost flat. **`intent`** routes everything:
`complaint` · `feature_request` · `question` · `praise` · `comparison` · `how_to` ·
`news/opinion` · `spam`. Embeddings computed only for non-spam, relevant items.

Idempotent + incremental: each stage has a **watermark** (max processed **`ingested_at`** /
last cursor — arrival time, *not* `created_at`: late-arriving items, e.g. deeper Reddit
pagination surfacing older comments, would slip past a source-time watermark); a rerun only
touches new rows; UPSERT everywhere (Nubra advisory-lock pattern).

---

## 4. Hard parts — how the non-obvious bits actually work (v1)

This is where "sounds good" becomes "buildable." Each picks the **pragmatic v1** and names
what we defer.

### 4.1 Dedup at scale
Two layers, both ~O(n) — and dedup **links, never drops** (a duplicate copy still carries
author + engagement signal we want):
- **Exact:** `content_hash` match (indexed, **not unique** — identical text from two
  different authors is two legitimate rows, both credited in `author_stats`).
- **Near-dup:** **MinHash + LSH** (e.g. `datasketch`) over text shingles → only near-dup
  candidates get a cheap Jaccard check. Signatures are **persisted** (`minhash_sig` on
  `social_items`); each run rebuilds the LSH index over a trailing **~14d** window — no
  unbounded in-memory state. Replaces the POC's O(n²) all-pairs scan.
- **Link, don't drop:** duplicates get `duplicate_of` → canonical item. Aggregation counts
  canonical items only, but still credits every copy's author and engagement — cross-posting
  is itself a popularity signal.
- **Cross-platform paraphrase** (same story on Reddit + X) is *not* dedup — it's handled at
  topic level (§4.2) and rewarded as cross-source **spread**.

### 4.2 Topics & velocity — stable keys first, emergent later
The trap: re-clustering each run gives unstable IDs → velocity is impossible. So:

```
 v1 (now):  maintain topic_taxonomy (~40 seeded trading topics)
            enrich step assigns each item a topic_key  (or "other:<label>")
            stable keys ⇒ velocity works:
               velocity_z = (today_count − mean_7d) / (std_7d + 1)
               rising if velocity_z ≥ 1.5     (cold-start <7d: rank by raw count)

 P2 (later): weekly, embed the "other:*" backlog → HDBSCAN to DISCOVER new topics
             → promote frequent clusters into the taxonomy (human-reviewed)
```
Stable keys give trustworthy "rising" signal **and** longitudinal tracking; clustering is
used only for *discovery*, where unstable IDs don't matter.

### 4.3 Conversations / threads
An **opportunity** is a *conversation*, not a lone item. Reconstruct per source via
`thread_id`/`parent_id` (Reddit post→comments, X `conversation_id`, Discord channel+thread,
Telegram `reply_to`). A `conversations` row carries: root, item_count, participants,
velocity, peak engagement, first/last seen — the unit the recommender scores.

Engagement is **snapshot-at-ingest** (watermark-driven ingest never revisits old items) —
with one exception: each ingest run re-fetches the **root items of *candidate*
conversations active in the last 24h** (those carrying a `suggested` opportunity or the
Nubra-watch flag — LLD-02 §4), so `peak_engagement` and hot-thread detection track
reality for the threads that matter while cold threads stay frozen.

### 4.4 Entities → issue & feature tracking (the "over time" requirement)
```
 broker gazetteer {nubra, zerodha, groww, upstox, dhan, angel one, …}  → deterministic link
 enrich extracts (for complaint / feature_request):
     {broker, issue_type|feature_phrase, summary}
 issue_type → fixed taxonomy (outage·order_reject·charges·kyc·app_crash·api_websocket·
              funds_settlement·support)            → stable issue_key
 feature_phrase → embed → nearest EXISTING feature_key centroid
     cosine ≥ τ (≈0.80) → assign + update centroid  |  else → mint new feature_key
   (incremental assignment, NOT per-run re-clustering — same reasoning as §4.2:
    re-clustering gives unstable keys and kills "consistently requested";
    periodic re-cluster = P2 human-reviewed cleanup only)
 ⇒ count per (broker, issue_key) / feature_key per day → trend, severity, "consistently requested"
```
Stable `issue_key`/`feature_key` are what make "persistent vs one-day spike" real.

### 4.5 Anti-gaming for Rising Voices
Followers alone are gameable. Voice score keeps the POC's relevance×consistency×breadth and
adds a light authenticity check (account age, engagement-to-follower sanity, not in a known
spam/tip list). Flag, don't hard-trust.

---

## 5. Data model (Postgres) — 18 tables in 5 layers

**Deployment:** ships next to `nubra-ai-personalization/` on the **same machine** as a
**separate service**, with its **own database `nubra_community` on the same Postgres
server** — independent `migrations/` starting at `0001`, no cross-DB coupling to
`intelligence_store` (if it ever needs Nubra market data it calls the API, not a join).
Full per-stage table flow: `nubra-community-manager-data-flow-2026-07-03.md`.

```
 L1 RAW        social_items · authors
 L2 ENRICH     item_enrichment · item_embeddings
 L3 AGGREGATE  conversations · topic_daily · issue_rollup · feature_rollup · author_stats
 L4 OUTPUT     opportunities · content_proposals · roundups
 L5 OPS/REF    pipeline_state · compliance_audit · topic_taxonomy ·
               nubra_features (USP + upcoming + SEO keywords) · feedback ·
               feature_keys (persisted feature centroids, §4.4)
               (reuse from Nubra libs: llm_usage, trace_log)
```

| Table | Key columns |
|---|---|
| `social_items` | PK `(source, external_id)` · `content_hash`·`minhash_sig`·`duplicate_of` · `thread_id`·`parent_id` · `author_id` · `text`·`lang` · `engagement` · `raw` · `created_at`·`ingested_at` |
| `authors` | `(source, handle)` · `followers`·`verified`·`account_created_at` · `first/last_seen` |
| `item_enrichment` | `item_id` PK (1:1) · `audience`·`intent`·`topic_key`·`sentiment` · `entities` jsonb · `is_noise` |
| `item_embeddings` | `item_id` PK · `embedding vector` · `model` (HNSW; non-noise only) |
| `conversations` | `thread_id` PK · `source`·`root_item_id` · `item_count`·`velocity`·`peak_engagement` · `dominant_topic_key` · last_seen |
| `topic_daily` | `(topic_key, day)` · `count`·`velocity_z`·`spread`·`engagement_sum`·`audience_mix` |
| `issue_rollup` | `(broker, issue_key, day)` · `count`·`severity`·`sentiment_avg`·`sample_item_ids` |
| `feature_rollup` | `(feature_key, day)` · `canonical_label`·`count`·`brokers_mentioned` |
| `author_stats` | `author_id` · `voice_score`·`contributions`·`communities`·`relevance`·`authenticity_flag` |
| `opportunities` | `id`·`thread_id`·`priority`·`brand_reply`·`rep_reply`·`recommended_timing`·`status` (suggested → acted \| dismissed, set by team via dashboard — the future feedback-loop signal) · `dismissed_reason` enum |
| `content_proposals` | `id`·`day`·`rank`·`format`·`hook`·`outline`·`why`·`rides_signal`·`recommended_timing` |
| `roundups` | `(period, date)` · `payload` jsonb · `delivery` jsonb |
| `pipeline_state` | `stage`/`source` · `watermark`·`cursor`·`last_success_at`·`last_error` |
| `compliance_audit` | `draft_ref`·`layer`·`verdict`·`reason`·`ts` |
| `topic_taxonomy` | `topic_key`·`label`·`seeded`·`active` |
| `feature_keys` | `feature_key`·`canonical_label`·`centroid vector`·`phrase_count`·`is_active` — the persisted centroid registry behind §4.4 incremental assignment |
| `nubra_features` | `feature`·`description`·`status`(live=USP \| upcoming)·`category`·**`seo_keywords[]`**·`version`·`is_current` — **the grounding source** for brand/rep replies **and** the SEO-keyword source (query expansion + rank boost). All version-labelled; LLM/ingest read `is_current=true` |
| `feedback` | `object_ref`·`category`·`free_text`·`submitted_by`·`ts` — internal, written by the dashboard |

> **Grounding = one vetted table.** `nubra_features` (current + upcoming, versioned) is
> small enough to pass directly to the reply LLM — so no separate KB/RAG/embeddings needed
> (this replaces the earlier `kb_chunks`). Dropped the generic `insights` table too —
> trends/issues/features/voices are *queries over the L3 rollups* frozen into
> `roundups.payload`. `post_log` is absent (posting = Future additions).

**Retention:** heavy tables (`social_items`, `item_enrichment`, `item_embeddings`)
partitioned by month, kept **180 days** (bulky `raw` jsonb may drop earlier, ~60d);
**all data is capped at 180 days** — L3 rollups, `opportunities`/`content_proposals`, and
`roundups` are pruned at 180d too (trends/persistence only ever look weeks back; 6 months
of history is ample). Two exceptions: reference/ops tables (`feature_keys`,
`topic_taxonomy`, `nubra_features`, `feedback`, `author_stats`, `pipeline_state`) are
current-state/config and kept. `compliance_audit` follows the same **180d** cap (team
decision 2026-07-03).

---

## 6. The six outputs (+ a Nubra-watch segment)

| # | Output | Built from | Method |
|---|---|---|---|
| 1 | **Trending topics** | `topic_daily` | velocity_z × cross-source spread × engagement × audience-weight |
| 2 | **Broker issues** | `issue_rollup` | per (broker, issue_key); count + trend + severity (sentiment×reach) |
| 3 | **Feature requests** | `feature_rollup` | per `feature_key`; **frequency over time** → "consistently requested" |
| 4 | **Rep talking points** | top opportunities | per-conversation organic reply, grounded on `nubra_features`, compliant |
| 5 | **Brand talking points** | same | per-conversation USP-led official reply, grounded on `nubra_features` |
| 6 | **Content proposals (top 3)** | the day's signal | LLM **ranks → keeps top 3** doable actions; always produced; **passes the compliance gate** |

**Separate segment — Nubra watch:** items where the mentioned broker **is Nubra** are
pulled into their own segment, **flagged in the next hourly heads-up** (§8 — a grievance
must not wait for the 07:30 roundup) and routed to support/grievance, **never** turned
into engagement drafts. Keeps us clear of doing grievance-handling on social.

Plus a **per-opportunity `recommended_timing`** (when-to-post) — see companion doc §2.

---

## 7. Platform & Nubra integration (reuse, don't rebuild)

```
 EventBridge cron ─▶ /triggers/fire (existing webhook) ─▶ community orchestrator (backend)
        ├─▶ Postgres (nubra_community)         ├─▶ S3 (media)
        ├─▶ Claude: Haiku=enrich · Sonnet=talking pts/proposals/roundup/compliance ─▶ Langfuse
        └─▶ Slack (digest)                     └─▶ Email/SMTP (Gmail app pwd)

 Postgres ◀── read-only ── DASHBOARD (frontend)   filters: date·source·topic·broker·
        └── feedback · opp.status ◀── writes ──┘   intent·audience·min-engagement
        (Nubra blue-dark palette; NO live fetching — pure view over the tables)
```

| Need | Reuse from nubra-ai-personalization |
|---|---|
| Scheduling | EventBridge → `/triggers/fire` webhook + trigger handlers |
| Store | **separate DB `nubra_community`** on the *same Postgres server* — own migrations from `0001`, no cross-DB coupling |
| LLM + tracing + cost | Claude + Langfuse + `llm_usage` |
| Secrets/config | dynaconf `config/.env` + yaml |
| Media / delivery | S3 client in `lib/`; Slack webhook; SMTP (Gmail app password; SES optional later) |
| Content guardrails | comms guardrail modules (crypto / tip-pump / artifact denylists from `nubraai-comms/intelligence/`) **vendored** — one safety vocabulary across push + community (LLD-02 §6.6) |

Net new: source adapters (incl. Discord bot), MinHash dedup, embeddings/pgvector,
aggregate + recommend stages, Slack/email roundup.

---

## 8. Orchestration & scheduling

Each stage is a **trigger** behind the existing webhook; EventBridge fires the cadence.
Stages chain by watermark (no global lock needed; each only consumes new rows).

| Trigger | When | Consumes → produces |
|---|---|---|
| `community:ingest_<src>` | per-source (hourly→daily) · **paused 01:00–06:00 IST** (chatter dies overnight; cursors catch up at 06:00 — nothing is lost, only fetched later) | source → `social_items` |
| `community:enrich` | every 30–60 min (06:00–01:00 IST) | new items → `item_enrichment` (+embeddings) |
| `community:aggregate` | hourly (06:00–01:00 IST) | enrichment → conversations/topic_daily/rollups |
| `community:score` | hourly (after aggregate) | conversations → scored `opportunities` (no LLM) |
| `community:headsup` | **hourly 08:00–20:00 IST** | **Slack + email heads-up**, two parts: **actions** (new priority-≥70 opportunities · new Nubra mentions · newly-rising topics · **recurring-momentum topics in new threads, weight-boosted** — sorted by boosted priority) + an **ops summary** of the last hour (fetched/deduped/noise-filtered/enriched/scored counts). Empty actions → compact ops-only digest (config) |
| `community:recommend` | with daily build | top opportunities → grounded drafts + compliance + content proposals |
| `community:roundup_daily` | ~07:30 IST (`pre_open`) | rollups + opportunities/proposals → digest → Slack + email |
| `community:roundup_weekly` | **Sat ~10:00 IST** | **Sat→Sat window**: highlights of the week, ranked with **last-week persistence weighting** (items also present last week weigh more) + weekly actions recap → Slack + email |

**Morning build (06:00–07:30 IST)** — the one place stages run as an orchestrated
sequence rather than independent timers: **06:00** ingest catch-up (all sources; X's
first poll of the day) → **~06:20** enrich **sync** (this one pass skips the Batch API so
the chain closes; ≈$0.02/day premium) → **~06:40** aggregate + score → **06:45** submit
the ⑤b generation batch → **07:15** batch deadline (sync fallback) → L2 compliance +
roundup synthesis → **07:30** roundup out. Everything collected overnight is therefore
in the day's drafts and roundup.

---

## 9. Cost (rough, per day)

Assume ~2,000 relevant items/day after prefilter.

| Item | Volume | Model | ~Cost/day |
|---|---|---|---|
| Enrichment | 2,000 items, batched | Haiku | ~$0.30–0.60 |
| Embeddings | ~2,000 | embed model | ~$0.02 |
| Talking points | ~10 opps × 2 | Sonnet | ~$0.30 |
| Content proposals + roundup | ~5 calls | Sonnet | ~$0.20 |
| Compliance gate (L2) | ~25 drafts/day | Sonnet | ~$0.10 |
| Sources (X) | budget-capped | twitterapi.io | set per `max_tweets` |

≈ **$1–2/day in LLM** + the X data budget. Caps + `llm_usage` logging keep it bounded;
Haiku for bulk, Sonnet only for the ~20 high-value generations. Cost-reduction measures
(Batch API 50%, prompt caching, X-query discipline, overnight pause) are specified in
`nubra-community-manager-cost-plan-2026-07-03.md`.

---

## 10. Operating it — health, metrics, failure

**Per-source health:** `last_success_at` + item count; alert if a source is stale beyond
its cadence (X 429s, Reddit scraper break, Discord bot removed). A dead source **degrades
gracefully** — the run continues on the others.

**Graceful LLM fallback:** enrichment retries with backoff; on hard failure falls back to
the POC's keyword classifier so the pipeline still ships a (lower-confidence) roundup.

**Quality metrics (weekly spot-check):** sample 30 items (include a **Hinglish slice** —
much of the chatter is code-switched) → intent/entity precision;
topic-assignment accuracy; % opportunities the team found useful (tagged in Slack).

**Pipeline metrics:** ingest/source, dedup rate, % enriched, stage latency, error rate →
`trace_log`-style rows + Langfuse for LLM.

---

## 11. What we deliberately keep simple in v1 (and defer)

| v1 (efficient) | Deferred |
|---|---|
| Topic **taxonomy assignment** by LLM | embedding **clustering** to discover new topics (P2) |
| MinHash-LSH near-dup | learned semantic dedup |
| Rule-based **when-to-post windows** | windows **learned** from our post outcomes |
| Heuristic voice score + authenticity flag | graph-based influence modeling |
| Recommend only | posting + approval + feedback loop (Future additions) |

---

## 12. Roadmap

```
 P0 · POC ✅          P1 · MVP prod                P2 · scale
 ───────────  ──▶  ────────────────────────  ──▶  ─────────────────────
 Streamlit         Postgres + 2 adapters           +GitHub/YouTube/Discord/
 + SQLite          (X · Reddit)                     Telegram/app-store adapters
 Reddit live       enrich · dedup · taxonomy        emergent topic clustering
 X via CSV         6 outputs + Nubra-watch          learned timing · richer voices
                   + when-to-post timing            self-learning (feedback-trained)
                   read-only dashboard
                   daily+weekly Slack/email
```

---

## 13. Future additions

| Future | Adds |
|---|---|
| **Posting with human approval** | Slack `Approve/Edit/Skip` → `post_executor` posts the chosen reply; approval queue + `post_log`. |
| **Auto-queue on timing** | act on the in-scope `recommended_timing` automatically (not just recommend it). |
| **Feedback loop** | track engagement on *our* posts → learn what works → tune ranking/timing. |
| **Semi-auto posting** | after feedback earns trust, auto-post vetted low-risk **brand** replies only. |
| **Self-learning** | use the internal `feedback` table (categories + text) to auto-tune ranking, prompts, and voice choice. |
| **More sources** | GitHub · YouTube · Discord · Telegram · app-store reviews — drop-in adapters (same contract). |
