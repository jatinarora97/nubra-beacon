# LLD-02 — Ingestion, Enrichment & Aggregation

_LLD · 2026-07-03 · source of truth for build-plan **M1 + M2**._
_Parents: `nubra-community-manager-architecture-2026-06-29.md` (§2–§5) ·
`…-data-flow-2026-07-03.md` (stages ①–④) · `…-build-plan-2026-07-03.md` (M1, M2)._
_Siblings: LLD-01 (data layer / DDL) · LLD-03 (recommend / delivery / API)._

Covers stages ① INGEST → ② NORMALIZE+DEDUP → ③ ENRICH → ④ AGGREGATE, exactly as the
data-flow doc draws them, at implementation depth.

---

## 0. Decisions made in this LLD (beyond the parent docs)

| # | Decision | Why |
|---|---|---|
| D1 | `feature_keys` reference table (key · label · centroid · counts) | centroids must persist between runs; `feature_rollup` is per-day and can't hold them. **DDL in LLD-01 §4** (the 18th table). |
| D2 | `item_enrichment.enriched_at` column; aggregate watermarks on it | aggregate needs its own arrival clock, same late-arrival logic as ingest→enrich. **DDL in LLD-01 §3.** |
| D3 | Engagement refresh updates `engagement`+`raw` only, never `ingested_at` | refreshed rows must not re-enter enrich (they're already enriched). |
| D4 | Canonical dup = earliest `ingested_at` (tiebreak: `(source, external_id)` asc) | deterministic, idempotent on rerun. |
| D5 | MinHash: `num_perm=128`, word 3-shingles, LSH threshold 0.7, Jaccard confirm ≥ 0.8 | standard datasketch operating point; short texts (< 3 words) skip near-dup entirely. |
| D6 | Enrich batch = 20 items/call, ≤ 2 retries, then keyword fallback **per batch** | keeps one malformed batch from stalling the stage. |
| D7 | Embedding = `intfloat/multilingual-e5-small` (384-d, cosine), `"query: "` prefix | e5 convention; 384-d keeps HNSW small. `bge-m3` swap = config change. |
| D8 | Unified `engagement.score = log1p(likes + 2·shares + 3·replies)` | replies signal conversation, weigh highest; log for heavy tails. |
| D9 | Broker linking is gazetteer-only: LLM-extracted `broker` string must resolve against the alias table or it becomes `null` | LLM never invents a broker key. |
| D10 | Severity = `log1p(reach_sum) × neg_share` (see §8.4) | reach × how negative; simple, explainable. |

The subreddit list in §1.3 is plugged in as v1 config (exhaustive tiered starter set,
extensible without code changes); SEO keywords remain a marketing input.

---

## 1. `SocialItem` contract, adapter base, registry

### 1.1 SocialItem (pydantic v2 — the only shape adapters may emit)

```python
class Engagement(BaseModel):
    score: float = 0.0                  # unified: log1p(likes + 2*shares + 3*replies)
    native: dict[str, int] = {}         # e.g. {"likes":10,"retweets":2,"replies":5,"views":900}

class AuthorMeta(BaseModel):
    followers: int | None = None
    verified: bool | None = None
    karma: int | None = None            # reddit
    account_created_at: datetime | None = None

class SocialItem(BaseModel):
    source: Literal["twitter", "reddit"]          # extend enum per new adapter
    source_type: Literal["post", "comment", "tweet", "reply", "message"]
    external_id: str                              # source-native id, stable
    parent_id: str | None = None                  # direct parent (reply chain)
    thread_id: str                                # conversation root key (§2.4 / §3.3)
    author: str                                   # handle, no '@'/'u/' prefix
    author_meta: AuthorMeta = AuthorMeta()
    text: str                                     # raw text, untruncated
    lang: str | None = None                       # source hint; else None (enrich may set)
    url: str
    created_at: datetime                          # SOURCE time, tz-aware UTC
    engagement: Engagement = Engagement()
    raw: dict                                     # full source payload, lossless
```

Derived at write time by the store (never by adapters): `content_hash`, `minhash_sig`,
`duplicate_of` (§5), `ingested_at = now()` (the watermark clock).

### 1.2 Adapter base

```python
class Capabilities(BaseModel):
    search: bool; replies: bool; threads: bool
    rate_limit_per_min: int
    cost_per_1k_items_usd: float | None

class SourceAdapter(ABC):
    name: str                                     # registry key
    capabilities: Capabilities

    @abstractmethod
    def fetch(self, window: TimeWindow, cursor: str | None) -> Iterator[SocialItem]:
        """Yield items with created_at inside `window`, oldest→newest where the
        source allows. Must be resumable from `cursor`. Never raises on a single
        bad item — log + skip. Raises AdapterError only on total failure."""

    @abstractmethod
    def fetch_items(self, external_ids: list[str]) -> list[SocialItem]:
        """Point lookups — used by the engagement refresh (§4)."""

    def next_cursor(self) -> str | None: ...      # opaque; persisted in pipeline_state
```

Contract rules:
- Adapters normalize into `SocialItem` and do **nothing else** — no dedup, no filtering
  beyond source-native noise (deleted/removed items), no LLM.
- One failed adapter never blocks the run: the orchestrator catches `AdapterError`, marks
  `pipeline_state.last_error`, continues with other sources (graceful-degrade rule, arch §10).

### 1.3 `registry.yaml`

```yaml
sources:
  # all crons in IST (TZ=Asia/Kolkata on the scheduler). No source runs 01:00–06:00 IST —
  # chatter dies overnight; cursors/watermarks catch up at 06:00, nothing is lost.
  twitter:
    enabled: true
    module: community.sources.twitter:TwitterAdapter
    cadence: "0 6,11,15,20 * * *"   # 4×/day; the 06:00 poll feeds the morning build (arch §8)
    budget:
      max_items_per_run: 1500       # hard cap → adapter stops yielding
      max_usd_per_day: 5.00
    queries:                        # base queries; SEO expansion appended at runtime (§2.2)
      - "(zerodha OR groww OR upstox OR dhan OR \"angel one\" OR nubra) lang:en OR lang:hi"
      - "(brokerage OR \"option selling\" OR \"algo trading\") (india OR nse OR bse)"
  reddit:
    enabled: true
    module: community.sources.reddit:RedditAdapter
    cadence: "0 0,6-23 * * *"       # hourly 06:00–00:59 IST; paused 01–06
    budget: {max_items_per_run: 2000}
    subreddits:                     # tiered; the adapter health check flags dead/renamed subs on the first run
      # tier 1 — core trading & market chatter
      - IndianStreetBets            # the largest Indian trading community
      - IndianStockMarket
      - IndiaInvestments            # moderated, high-quality investing discussion
      - StockMarketIndia
      - DalalStreetTalks
      - DalalStreetBets
      # tier 2 — broker/product/feature chatter (funds, personal finance, charges)
      - mutualfunds                 # despite the generic name, predominantly Indian MF discussion
      - personalfinanceindia
      - FIREIndia
      - IndiaFinance
      - IndiaTax                    # charges/taxation complaints often name brokers
```

Adding a source = one module + one registry block. Nothing downstream changes.

---

## 2. X adapter (twitterapi.io)

### 2.1 Endpoints

| Purpose | Endpoint | Used by |
|---|---|---|
| Search | `GET /twitter/tweet/advanced_search` (`query`, `queryType=Latest`, `cursor`) | `fetch()` |
| Point lookup | `GET /twitter/tweets` (`tweet_ids=` batch of ≤ 100) | `fetch_items()` (refresh §4) |
| Thread backfill | `advanced_search` with `conversation_id:<id>` | only for priority-≥40 candidate conversations, budget-permitting (cost plan §2.2) |

Auth: `X-API-Key` header from dynaconf. All calls logged (endpoint, cost units, items) to
`trace_log`.

### 2.2 Query construction — SEO expansion (expand, never filter)

```
base_queries (registry)                              →  run as-is (full blast radius)
+ expansion query, built per run:
    kw = SELECT unnest(seo_keywords) FROM nubra_features WHERE is_current
    chunks of ≤ 12 keywords → ("kw1" OR "kw2" OR …) (india OR nse OR trading)
```

Expansion queries are **additional** searches — they raise recall on Nubra-relevant phrases.
Nothing is ever dropped for not matching a keyword. Items matching an expansion query get
`raw._matched_seo=true` (recommend's rank boost reads this; LLD-03).

### 2.3 Budget + backoff

- Run stops yielding at `max_items_per_run` or when projected day-spend ≥ `max_usd_per_day`
  (cost tracked per call in `pipeline_state.cursor` json).
- `429`/`5xx`: exponential backoff 1s → 2s → 4s → 8s, max 5 tries, then `AdapterError`
  (health alert; other sources continue).

### 2.4 Mapping → SocialItem

| SocialItem | from tweet payload |
|---|---|
| `external_id` | `id` |
| `thread_id` | `conversationId` (falls back to `id` for roots) |
| `parent_id` | `inReplyToId` |
| `source_type` | `tweet` if root else `reply` |
| `author`, `author_meta` | `author.userName` · followers/verified/createdAt |
| `engagement.native` | likes, retweets+quotes (as `shares`), replies, views |
| `lang` | tweet `lang` |
| `created_at` | `createdAt` → UTC |

Cursor = twitterapi.io's `next_cursor` per query, persisted as
`{query_idx: cursor}` json in `pipeline_state`.

---

## 3. Reddit adapter (Playwright — kept as-is for now)

### 3.1 Config

Subreddit list in `registry.yaml` (the tiered v1 list above is live config — the first
scheduled run's health check flags any dead or renamed sub, and the list is extensible
without code changes). Per run, per
subreddit: `new` listing (depth: posts newer than watermark − 48h, cap 100 posts) + comments
of any post that is **new or active < 24h**.

### 3.2 Traversal

```
for sub in subreddits:
    goto old.reddit.com/r/{sub}/new/          # stable DOM, cheap pages
    collect post stubs until created < window.start
    for post in stubs (new or active<24h):
        goto post permalink + "?limit=500"
        parse post body → SocialItem(source_type="post")
        walk comment tree (depth-first, "load more" up to 3 expansions)
              → SocialItem(source_type="comment")
```

### 3.3 Mapping

| SocialItem | from |
|---|---|
| `external_id` | thing id (`t3_…` post / `t1_…` comment) |
| `thread_id` | the post's `t3_…` id (for both post and all its comments) |
| `parent_id` | comment's parent thing id (`t3_…` for top-level) |
| `author_meta.karma` | author karma when visible; else None |
| `engagement.native` | `{likes: score, replies: num_comments-or-child-count}` |

### 3.4 Failure detection / health

- Selector miss on ≥ 3 consecutive pages → `AdapterError("layout_changed")`.
- 0 items across 2 consecutive scheduled runs → staleness alert (arch §10) even without a
  raised error.
- Each run records `items_fetched`, `pages_visited`, `selector_misses` into
  `pipeline_state.cursor` json for trend-level debugging.

---

## 4. Engagement refresh (active-conversation roots)

Per ingest run, per source, **before** the normal fetch:

```sql
SELECT c.root_item_id, si.external_id
FROM conversations c
JOIN social_items si ON si.item_id = c.root_item_id
LEFT JOIN opportunities o ON (o.source, o.thread_id) = (c.source, c.thread_id)
WHERE c.source = :source
  AND c.last_seen > now() - interval '24 hours'
  AND (o.status = 'suggested' OR c.is_nubra_watch)  -- candidates only (cost plan §2.2);
LIMIT 200;                                          -- a brand-new thread scores first on its
                                                    -- ingest-time engagement (fresh enough)
```

→ `adapter.fetch_items(external_ids)` → plain UPDATE (no `ON CONFLICT` possible — there is
no DB-level unique on `(source, external_id)`; LLD-01 D1):

```sql
UPDATE social_items
SET engagement = :engagement,
    raw        = :raw
WHERE source = :source AND external_id = :external_id;
-- deliberately untouched: ingested_at, text, content_hash, minhash_sig, duplicate_of
```

**D3:** `ingested_at` unchanged → refreshed rows stay behind the enrich watermark (already
enriched, must not re-enrich). Everything else (all metadata, text) is frozen at first
ingest; only engagement counters move. Aggregate recomputes `peak_engagement` from the
updated rows on its next hourly pass — no special path needed.

---

## 5. Normalize + dedup (link, never drop)

### 5.1 Text normalization (input to hashing/minhash only — stored `text` stays raw)

```
norm(text): NFKC → lowercase → strip URLs (http/https/t.co/redd.it)
            → strip @mentions and u/ user refs → collapse whitespace → trim
```

`content_hash = sha256(norm(text))` — hex, indexed, **not unique** (same text from two
authors = two legitimate rows; both credited in `author_stats`).

### 5.2 MinHash + LSH (D5)

```
tokens   = norm(text).split()
if len(tokens) < 3:  minhash_sig = NULL   # too short for shingles; exact-hash only
shingles = 3-word sliding windows
sig      = datasketch.MinHash(num_perm=128) over shingles → LeanMinHash → bytea
```

Per dedup run:
1. Build `MinHashLSH(threshold=0.7, num_perm=128)` from `minhash_sig` of all items with
   `ingested_at > now()-14d` (the trailing window; ~30k sigs, trivially in-memory).
2. For each **new** item (past the dedup watermark): exact pass first —
   `content_hash` match inside the 14d window → duplicate.
3. Else LSH query → candidates → confirm `jaccard(sig_new, sig_cand) ≥ 0.8` → duplicate.
4. Duplicate → `duplicate_of = canonical.item_id` where canonical is the match with the earliest
   `ingested_at` (tiebreak `(source, external_id)` asc — D4). Chains are flattened: if the
   match itself has `duplicate_of`, point to *its* canonical (one hop max, by construction).
5. Not a duplicate → `duplicate_of = NULL`.

**Nothing is deleted.** Downstream rules:
- **Enrich** processes canonical items only (`duplicate_of IS NULL`); duplicates get no
  enrichment row of their own — readers join through the canonical.
- **Aggregate counts** (topic_daily.count, rollup counts, conversation item_count) count
  canonical items only.
- **Author + engagement credit** sums over canonical **and** duplicates (cross-posting is
  itself a signal): `author_stats` contributions and `engagement_sum` include dup rows.

### 5.3 What near-dup is NOT

Cross-platform paraphrase (same story, different words on Reddit vs X) is deliberately not
dedup — it surfaces as topic-level `spread` (§8.2) and is rewarded, not removed (arch §4.1).

---

## 6. Enrichment (stage ③ — one batched Haiku call)

### 6.1 Batching + flow

- **Deterministic pre-filter first** (cost plan §2.3): emoji-only / pure-link / empty
  text and known spam-handle authors are written as `is_noise=true, model='rule-prefilter'`
  with no LLM call — plus the **reused comms guardrails** (§6.6: crypto-only chatter,
  tip/pump language, scraper artifacts). Only unambiguous cases; anything debatable goes
  to the model.
- Input: remaining canonical items with `ingested_at >` enrich watermark, `is_noise`
  unknown, ordered by `ingested_at`, batches of **20** (D6).
- Calls go through the **Anthropic Batch API** (−50% — cost plan §2.1): submit the pass
  as one batch, poll; if not `ended` within 25 min, run that pass sync and resume
  batching next pass. Results keyed by `custom_id` (arrival order is undefined);
  `errored`/`expired` items fall back to sync calls individually. **Exception:** the
  06:00 morning-build pass runs sync (one full-price Haiku pass/day, ≈$0.02) so the
  06:00→07:30 chain closes on time (arch §8).
- One Haiku call per batch of 20; response schema-validated (pydantic); on validation failure
  retry ≤ 2 with an appended "your last output failed validation: <err>" turn; then
  **keyword-classifier fallback for that batch only** (written with `model='kw-fallback'`, LLD-01 §3).
- Writes `item_enrichment` (1:1, UPSERT on `item_id`) with `enriched_at = now()` (D2);
  logs `llm_usage` + Langfuse trace per call.

### 6.2 Prompt sketch (`llm/prompts/enrich.txt`)

```
You label social posts from Indian trading communities. Text is often Hinglish /
code-switched Hindi-English ("bhai zerodha ka app phir se hang ho gaya") — treat Hinglish
as first-class; never mark an item noise or unknown merely for not being English.

For EACH item return JSON per the schema:
- audience: who is talking (active_trader | long_term_investor | beginner | influencer | other)
- intent: complaint | feature_request | question | praise | comparison | how_to |
          news_opinion | spam
- topic_key: EXACTLY one key from the provided taxonomy list, or "other:<3-word-label>"
- sentiment: -1.0 .. 1.0
- entities: for complaint/feature_request only —
    {broker: <name-as-written or null>, issue_type: <from fixed list> OR
     feature_phrase: <verbatim-ish short phrase>, summary: <≤15 words>}
- is_noise: true for spam/tips/pump groups/irrelevant

Items: [{id, source, text, thread_hint}]      Taxonomy: [<~40 topic keys+labels>]
Issue types: outage | order_reject | charges | kyc | app_crash | api_websocket |
             funds_settlement | support
```

### 6.3 Output schema (validated)

```json
{"items": [{
  "id": "…",
  "audience": "active_trader",
  "intent": "complaint",
  "topic_key": "broker_reliability",
  "sentiment": -0.7,
  "entities": {"broker": "zerodha", "issue_type": "app_crash",
                "feature_phrase": null, "summary": "Kite hung during expiry open"},
  "is_noise": false }]}
```

Post-validation hard checks (code, not model): `topic_key ∈ taxonomy ∪ other:*`;
`issue_type ∈ fixed list`; `intent ∈ enum`; count(items) == count(input) and ids match.

### 6.4 Broker linking (D9)

`entities.broker` (free text) → alias gazetteer → canonical broker key or `null`:

```
nubra: [nubra] · zerodha: [zerodha, kite, coin] · groww: [groww] ·
upstox: [upstox] · dhan: [dhan] · angel_one: [angel one, angelone, angel broking] · …
```

Word-boundary, case-insensitive match on the LLM's string; no match → `broker = null`
(counts as un-attributed complaint; never guessed). Gazetteer lives in
`reference/taxonomy.py`, versioned in git.

### 6.5 Cost guardrails

~2,000 items/day ÷ 20 = ~100 Haiku calls (~$0.30–0.60/day, arch §9). Hard stop if the
stage's day-spend (from `llm_usage`) exceeds 5× budget → alert + fallback classifier.

### 6.6 De-noising guardrails — reused from `nubra-ai-personalization`

The comms service ships deterministic content guardrails for push notifications — all
pure-Python/regex, **stdlib-only**, living in
`nubra-ai-personalization/nubraai-comms/intelligence/`. We reuse them on *incoming*
items during de-noise so both services share one safety vocabulary:

| Reused piece (source) | Use here |
|---|---|
| `lib/content_policy.py` — `mentions_crypto(*texts)` (word-boundary crypto denylist: bitcoin, web3, nft, memecoin, …; env `NUBRA_BLOCK_CRYPTO`) | crypto-only items → `is_noise=true` (`model='rule-guardrail'`) — off-mission for an NSE/BSE broker, and consistent with the comms-wide crypto block |
| `notifications/guardrails.py` — `_FEAR_PHRASES` + `_BUY_SELL_CALL_PATTERNS` denylists ("guaranteed", "sure shot", "act now", "buy now", "load up on", …) | **tip/pump detection**: items dominated by this language → noise; augments the spam-handle list (§8.5) |
| `lib/validation.py` — `validate_text(text)` (`nan_leak`, `raw_symbol`, currency-style `Issue`s) | **scraper-artifact detection**: items that are mostly placeholders / raw option symbols → noise |
| the same denylists, imported by the L1 compliance gate (LLD-03 §3.1) | a phrase banned in push copy is banned in community drafts — one vocabulary across surfaces |

**Mechanics:** the modules are vendored verbatim into
`community/lib/comms_guardrails/` (provenance header with source path + commit;
`scripts/sync_guardrails.py` re-copies from the comms repo and CI diff-checks for
drift). Reuse only the **string-only** entry points — `mentions_crypto`,
`validate_copy(title, body)`, `validate_text(text)`, `evaluate(title, body, …)`. The
push-specific *delivery* guards (frequency caps, quiet hours, `apply()`,
`notification_decisions` dedupe) are **not** reused.

**Caution — classifier, not censor:** a genuine complaint may *quote* tip language
("this influencer promised 'sure shot returns'"). Rule hits mark noise only when the
pattern **dominates** the text (matched tokens above a config threshold); otherwise the
item proceeds to Haiku enrichment as usual.

---

## 7. Embeddings

- Model: `intfloat/multilingual-e5-small`, CPU, 384-d, cosine (D7). Swap to `bge-m3` is a
  config key (`embeddings.model`) + a new `item_embeddings.model` value — never overwrite
  rows produced by a different model.
- Input: `"query: " + norm(text)` truncated to 512 tokens.
- Scope: canonical, non-noise items only (`duplicate_of IS NULL AND NOT is_noise`).
- Write: UPSERT `item_embeddings(item_id, embedding, model)`.
- Index: HNSW, `vector_cosine_ops`, `m=16, ef_construction=64` (LLD-01 DDL).

---

## 8. Aggregation (stage ④, hourly)

Consumes enrichment rows with `enriched_at >` aggregate watermark; all writes UPSERT.

### 8.1 `conversations`

Group new canonical items by `(source, thread_id)`:

```
item_count      += new canonical items in thread
participants     = count(distinct author) (recomputed per thread touched)
velocity         = items in last 3h / max(items in prior 3h, 1)
peak_engagement  = max(engagement.score) over thread incl. refreshed roots + dup credit
dominant_topic_key = mode(topic_key) over thread's canonical items
first_seen / last_seen maintained
```

Nubra-watch tagging happens here: any thread containing a linked `broker='nubra'` entity
gets `is_nubra_watch=true` (⑤a reads it; LLD-03).

### 8.2 `topic_daily`

Per `(topic_key, day)` over canonical non-noise items:

```
count          = items
velocity_z     = (today_count − mean_7d) / (std_7d + 1)     # trailing 7 full days
                 cold-start (<7d history): velocity_z = NULL → rank by raw count
spread         = count(distinct source with ≥ 2 items)
engagement_sum = Σ engagement.score  (canonical + their duplicates — dup credit)
audience_mix   = jsonb {audience: share}
```

“Rising” = `velocity_z ≥ 1.5` (arch §4.2). Recompute the current day's row on every pass
(idempotent full-day recompute — cheap, avoids increment drift). The UPSERT must **not
touch `headsup_at`** — that column is owned by the heads-up sender (LLD-03 §1.3) and a
recompute that clobbered it would re-surface already-pinged topics.

### 8.3 `issue_rollup`

Per `(broker, issue_key, day)` where `intent='complaint'` and broker linked:
`count`, `sentiment_avg`, `sample_item_ids` (≤ 5, highest engagement),
`severity = log1p(Σ author_followers-or-reach) × neg_share` where
`neg_share = fraction of items with sentiment < −0.3` (D10).

### 8.4 `feature_rollup` + `feature_keys` (incremental centroid assignment)

```
for item where intent='feature_request' and feature_phrase is not null:
    v = embed("query: " + feature_phrase)                  # same e5 model
    best = argmax over feature_keys of cosine(v, centroid) # brute force; few hundred keys
    if best.sim >= τ (0.80):
        key = best.key
        centroid ← (centroid*n + v)/(n+1); n += 1          # running mean, then renormalize
    else:
        key = FeatureKeyRepo.create(label, v)              # mints feat_NNNNN (LLD-01 §11); centroid=v, n=1
        canonical_label = feature_phrase
    upsert feature_rollup(key, day): count += 1, brokers_mentioned ∪= {broker}
```

- Centroids persist in **`feature_keys`** (D1; DDL = LLD-01 §4): `feature_key PK ('feat_NNNNN') ·
  canonical_label · centroid vector(384) · phrase_count · is_active · created_at/updated_at`.
- **No per-run re-clustering** — that's exactly the instability arch §4.2 forbids. P2:
  periodic (monthly) HDBSCAN over accumulated phrases proposes merges → human-reviewed
  migration script rewrites keys once, with an audit row.
- τ is config (`aggregate.feature_sim_threshold=0.80`); log near-misses (0.7–0.8) weekly
  for threshold tuning.

### 8.5 `author_stats`

Per author touched this pass (contributions include duplicates — dup credit):

```
relevance    = share of author's items that are non-noise & topic ∈ taxonomy (not other:*)
consistency  = active days in last 30 / 30
breadth      = distinct topic_keys in last 30d, capped at 8, /8
voice_score  = 100 × (0.4·relevance + 0.3·consistency + 0.3·breadth)
authenticity_flag if ANY:
    account age < 90d · followers>10k with median engagement <1 ·
    author in known tip/spam handle list (reference/taxonomy.py)
```

Flag, don't hard-trust (arch §4.5): flagged authors keep their score; recommend downweights.

---

## 9. Watermark mechanics (per stage)

`pipeline_state(stage, source)` rows; all times UTC.

| Stage | Watermark predicate | Advances to | Notes |
|---|---|---|---|
| ingest | source cursor (opaque) | adapter `next_cursor()` | plus `last_success_at`, health counters |
| dedup | `ingested_at > wm` | max `ingested_at` seen | runs inside the ingest transaction batch, after write |
| enrich | `ingested_at > wm AND duplicate_of IS NULL` | max `ingested_at` **of successfully enriched batch** | failed batch → wm not advanced past it |
| aggregate | `enriched_at > wm` | max `enriched_at` seen | current-day rollup rows fully recomputed (idempotent) |

Rules:
- Watermarks always compare on **arrival clocks** (`ingested_at`/`enriched_at`), never
  `created_at` — late-arriving items (deeper Reddit pagination) are picked up (arch §3).
- A stage advances its watermark **only after** its writes commit (same transaction).
- Every write is UPSERT → any stage can be re-run from an older watermark with no
  duplicates (recovery = set watermark back, rerun).
- Concurrency: per-(stage,source) Postgres advisory lock (Nubra pattern) — a slow run and
  its successor never interleave.

---

## 10. Stage health (consumed by ops, arch §10)

Each stage writes to `pipeline_state`: `last_success_at`, `last_error`,
`items_in/items_out`, duration. Alerts (LLD-03 delivery channel): source stale beyond
2× cadence · enrich fallback active · dedup window query > 60s · embedding backlog > 5k.
