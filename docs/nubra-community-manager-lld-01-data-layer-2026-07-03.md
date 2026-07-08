# Nubra Community Manager — LLD-01 · Data Layer

> **STALE AS OF 2026-07-08 — kept for design rationale only.** The build
> deviated in load-bearing ways (React UI, restructured packages, vendored
> scraper transport, calibrations, Docker deploy). Current truth:
> `nubra-community-manager-status-2026-07-05.md` (what is built) +
> `nubra-beacon-tech-backlog-2026-07-08.md` (what remains). Where this file
> disagrees with those, those win.

_LLD · 2026-07-03 · source of truth for M0 and the schema side of every milestone._
_Companions: `…-architecture-2026-06-29.md` (§5 data model) · `…-data-flow-2026-07-03.md` ·
`…-build-plan-2026-07-03.md` (M0). DB: **`nubra_community`** · PostgreSQL ≥ 15 · `pgvector`._

---

## 0. Decisions made in this LLD (reviewer spot-check list)

| # | Decision | Why |
|---|---|---|
| D1 | Partition key = **`ingested_at`**; `social_items` PK becomes `(source, external_id, ingested_at)`; **logical** uniqueness on `(source, external_id)` enforced in the repository under a per-source advisory lock | PG requires the partition key inside every PK/UNIQUE on a partitioned table. Retention + watermarks both run on `ingested_at`, so partitions align with pruning. Ingest is single-writer per source (advisory lock — existing Nubra pattern), so app-level uniqueness is race-free |
| D2 | **No physical FKs into partitioned tables**; `item_enrichment`/`item_embeddings` are co-partitioned by a copied `ingested_at` and joined on `item_id`; integrity via repo + weekly orphan check | An FK must reference a UNIQUE key that contains the target's partition key — `UNIQUE(item_id)` can't exist on partitioned `social_items` |
| D3 | **18th table `feature_keys`** (centroid registry) added | The accepted incremental-centroid design needs persisted centroids; `feature_rollup` only holds daily counts. Arch §5 already lists 18 incl. this table |
| D4 | `conversations` PK = `(source, thread_id)` (not `thread_id` alone) | Reddit ids and X `conversation_id`s can collide |
| D5 | `text + CHECK` instead of native Postgres enums | Enum value removal/rename is painful in migrations; intents/statuses will evolve |
| D6 | `vector(384)` (dim of `multilingual-e5-small`); `model` column on `item_embeddings` | Allows a future re-embed migration without schema change |
| D7 | `compliance_audit` stores the **full reviewed draft text**, kept **180 d** like all data (team decision 2026-07-03) | The row is the review evidence; a hash alone proves nothing without the text |
| D8 | `authors` gets surrogate `author_id` + `UNIQUE(source, handle)` | Stable join key for `social_items`/`author_stats` |

`llm_usage` / `trace_log` are created in this DB by the shared Nubra lib's own migration —
not part of `0001_init.sql`.

---

## 1. Conventions

- All timestamps `timestamptz`, UTC in DB; IST only at render time.
- `created_at` = source time · `ingested_at` = arrival time (**watermark + partition clock**).
- Migrations: `migrations/0001_init.sql`, `0002_*.sql` … applied by `run_migrations.py` (§7).
- One schema: `public` (own database → no namespace pressure).

```sql
-- 0001_init.sql preamble
CREATE EXTENSION IF NOT EXISTS vector;
```

---

## 2. DDL — L1 RAW

### 2.1 `authors`

```sql
CREATE TABLE authors (
    author_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source              text        NOT NULL,
    handle              text        NOT NULL,
    followers           integer,
    verified            boolean,
    account_created_at  timestamptz,
    author_meta         jsonb       NOT NULL DEFAULT '{}'::jsonb,
    first_seen          timestamptz NOT NULL DEFAULT now(),
    last_seen           timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, handle)
);
```

`author_meta` example (source-specific extras, lossless):

```json
{"karma": 15400, "cake_day": "2019-03-11", "bio": "options seller", "listed_count": 12}
```

### 2.2 `social_items` — partitioned

```sql
CREATE TABLE social_items (
    item_id       bigint      GENERATED ALWAYS AS IDENTITY,
    source        text        NOT NULL CHECK (source IN
                    ('twitter','reddit','github','youtube','discord','telegram','app_review')),
    source_type   text        NOT NULL CHECK (source_type IN
                    ('post','comment','tweet','reply','message','review','issue')),
    external_id   text        NOT NULL,
    parent_id     text,                        -- source-native id of parent (nullable)
    thread_id     text,                        -- source-native conversation/thread id
    author_id     bigint      NOT NULL REFERENCES authors(author_id),
    text          text        NOT NULL,        -- normalized text (see LLD-02 §2)
    lang          text,                        -- 'en' | 'hi' | 'hi-en' (Hinglish) | …
    url           text,
    content_hash  char(64)    NOT NULL,        -- sha256 hex of normalized text; NOT unique (D1/arch §4.1)
    minhash_sig   bytea,                       -- 128 × uint32 LeanMinHash (512 B); NULL until dedup pass
    duplicate_of  bigint,                      -- item_id of canonical item; NULL = canonical (logical FK, D2)
    engagement    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    raw           jsonb,                       -- full source payload; scrubbed at ~60d (§6)
    created_at    timestamptz NOT NULL,        -- source time
    ingested_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, external_id, ingested_at)
) PARTITION BY RANGE (ingested_at);
```

`engagement` shape — always a normalized `score` + native counts:

```json
{"score": 412, "native": {"likes": 380, "retweets": 22, "replies": 10, "views": 51230}}
{"score": 96,  "native": {"upvotes": 91, "comments": 34, "upvote_ratio": 0.94}}
```

**Logical uniqueness (D1):** the repo inserts with
`INSERT … SELECT … WHERE NOT EXISTS (SELECT 1 FROM social_items WHERE source=$1 AND external_id=$2)`
while holding `pg_advisory_xact_lock(hashtext('ingest:'||source))`. Engagement refresh
(active-24h conversation roots) is an `UPDATE … WHERE source=$1 AND external_id=$2`.

---

## 3. DDL — L2 ENRICH (co-partitioned, D2)

```sql
CREATE TABLE item_enrichment (
    item_id      bigint      NOT NULL,          -- logical FK → social_items.item_id
    ingested_at  timestamptz NOT NULL,          -- copied from the item; co-partition key
    audience     text        CHECK (audience IN
                   ('active_trader','long_term_investor','beginner','influencer','other')),
    intent       text        NOT NULL CHECK (intent IN
                   ('complaint','feature_request','question','praise',
                    'comparison','how_to','news_opinion','spam')),
    topic_key    text        NOT NULL,          -- topic_taxonomy key or 'other:<label>'
    sentiment    real        CHECK (sentiment BETWEEN -1 AND 1),
    entities     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    is_noise     boolean     NOT NULL DEFAULT false,
    model        text        NOT NULL,          -- e.g. 'claude-haiku-4-5' | 'kw-fallback'
    enriched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, ingested_at)
) PARTITION BY RANGE (ingested_at);

CREATE TABLE item_embeddings (
    item_id      bigint      NOT NULL,
    ingested_at  timestamptz NOT NULL,
    embedding    vector(384) NOT NULL,          -- multilingual-e5-small (D6)
    model        text        NOT NULL DEFAULT 'multilingual-e5-small',
    PRIMARY KEY (item_id, ingested_at)
) PARTITION BY RANGE (ingested_at);
```

`entities` shape (only populated fields present):

```json
{
  "brokers": ["zerodha"],
  "issue":   {"broker": "zerodha", "issue_key": "order_reject",
              "summary": "GTT orders rejected at open"},
  "feature_phrase": "basket orders with margin preview",
  "tickers": ["NIFTY", "BANKNIFTY"]
}
```

`issue_key` ∈ fixed taxonomy (arch §4.4): `outage · order_reject · charges · kyc ·
app_crash · api_websocket · funds_settlement · support` — enforced by the enrich schema
validator, not a DB constraint (taxonomy lives in code/config).

---

## 4. DDL — L3 AGGREGATE

```sql
CREATE TABLE conversations (
    source              text        NOT NULL,
    thread_id           text        NOT NULL,
    root_item_id        bigint,                 -- logical FK
    item_count          integer     NOT NULL DEFAULT 0,
    participant_count   integer     NOT NULL DEFAULT 0,
    velocity            real,                   -- acceleration: items last 3h / max(items prior 3h, 1) — LLD-02 §8.1
    peak_engagement     integer,                -- max engagement.score seen (refreshed roots)
    dominant_topic_key  text,
    is_nubra_watch      boolean     NOT NULL DEFAULT false,
    headsup_at          timestamptz,            -- last time this thread appeared in an hourly heads-up
                                                --   (Nubra-watch per-day dedup: resurface only if < start of today IST)
    first_seen          timestamptz,
    last_seen           timestamptz,
    PRIMARY KEY (source, thread_id)             -- D4
);

CREATE TABLE topic_daily (
    topic_key       text    NOT NULL,
    day             date    NOT NULL,
    count           integer NOT NULL DEFAULT 0,   -- canonical items only (dupes linked, not counted)
    velocity_z      real,
    spread          smallint,                      -- distinct sources today
    engagement_sum  bigint,
    audience_mix    jsonb,                         -- {"active_trader": 0.6, "beginner": 0.3, …}
    headsup_at      timestamptz,                   -- set when this (topic, day) was first surfaced as newly-rising
                                                   --   in a heads-up; aggregate's full-day recompute must NOT clobber it
    headsup_count   smallint NOT NULL DEFAULT 0,   -- how many heads-ups featured this topic today — drives the
                                                   --   recurrence boost (LLD-03 §1.1); owned by the heads-up sender
    PRIMARY KEY (topic_key, day)
);

CREATE TABLE issue_rollup (
    broker          text    NOT NULL,              -- gazetteer-normalized
    issue_key       text    NOT NULL,
    day             date    NOT NULL,
    count           integer NOT NULL DEFAULT 0,
    severity        real,                          -- sentiment × reach composite
    sentiment_avg   real,
    sample_item_ids bigint[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (broker, issue_key, day)
);

CREATE TABLE feature_keys (                        -- D3 · centroid registry
    feature_key      text        PRIMARY KEY,      -- 'feat_00042'
    canonical_label  text        NOT NULL,
    centroid         vector(384) NOT NULL,
    phrase_count     integer     NOT NULL DEFAULT 1,  -- running-mean denominator
    is_active        boolean     NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feature_rollup (
    feature_key      text    NOT NULL REFERENCES feature_keys(feature_key),
    day              date    NOT NULL,
    canonical_label  text    NOT NULL,             -- denormalized for cheap reads
    count            integer NOT NULL DEFAULT 0,
    brokers_mentioned text[] NOT NULL DEFAULT '{}',
    sample_item_ids  bigint[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (feature_key, day)
);

CREATE TABLE author_stats (
    author_id          bigint  PRIMARY KEY REFERENCES authors(author_id),
    voice_score        real    NOT NULL DEFAULT 0,
    contributions      integer NOT NULL DEFAULT 0,
    communities        integer NOT NULL DEFAULT 0,
    relevance          real,
    authenticity_flag  boolean NOT NULL DEFAULT false,  -- true = suspicious (arch §4.5)
    updated_at         timestamptz NOT NULL DEFAULT now()
);
```

---

## 5. DDL — L4 OUTPUT + L5 OPS/REF

```sql
CREATE TABLE opportunities (
    id                  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source              text    NOT NULL,
    thread_id           text    NOT NULL,
    day                 date    NOT NULL,
    priority            smallint NOT NULL CHECK (priority BETWEEN 0 AND 100),
    matched_insight     jsonb,          -- {"type":"issue","broker":"zerodha","issue_key":"order_reject"}
    brand_reply         text,           -- NULL until ⑤b draft pass
    rep_reply           text,
    recommended_timing  jsonb,
    status              text    NOT NULL DEFAULT 'suggested'
                          CHECK (status IN ('suggested','acted','dismissed')),
    status_updated_by   text,
    status_updated_at   timestamptz,
    dismissed_reason    text CHECK (dismissed_reason IN
                          ('not_relevant','already_handled','too_late','too_risky','other')),
                                        -- required when status='dismissed' (API-enforced)
    pinged_at           timestamptz,    -- when this opp appeared in an hourly heads-up (NULL = not yet surfaced)
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, thread_id)          -- never re-surface the same thread
);

CREATE TABLE content_proposals (
    id                  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    day                 date    NOT NULL,
    rank                smallint NOT NULL CHECK (rank BETWEEN 1 AND 3),
    format              text    NOT NULL CHECK (format IN
                          ('infographic','reel','short','post','thread')),
    hook                text    NOT NULL,
    outline             jsonb   NOT NULL DEFAULT '[]'::jsonb,  -- ordered beats — the actionable part
    why                 text,                                  -- why this proposal lands
    rides_signal        jsonb   NOT NULL,   -- {"type":"topic","topic_key":"fo_expiry","velocity_z":2.4}
    recommended_timing  jsonb,
    created_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (day, rank)
);

CREATE TABLE roundups (
    period    text  NOT NULL CHECK (period IN ('daily','weekly')),
    date      date  NOT NULL,
    payload   jsonb NOT NULL,
    delivery  jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (period, date)
);

CREATE TABLE pipeline_state (
    stage            text  NOT NULL,     -- 'ingest'|'dedup'|'enrich'|'aggregate'|'score'|'recommend'|'roundup'
    source           text  NOT NULL DEFAULT '',   -- per-source for ingest; '' otherwise
    watermark        timestamptz,        -- max processed arrival clock (ingested_at; enriched_at for aggregate — LLD-02 §9)
    cursor           jsonb,              -- source-native pagination cursor
    last_success_at  timestamptz,
    last_error       text,
    last_error_at    timestamptz,
    items_last_run   integer,
    PRIMARY KEY (stage, source)
);

CREATE TABLE compliance_audit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draft_ref   jsonb  NOT NULL,   -- {"kind":"opportunity","id":123,"voice":"brand"} |
                                   -- {"kind":"content_proposal","id":45}
    draft_text  text   NOT NULL,   -- full reviewed text (D7 — the evidence)
    layer       text   NOT NULL CHECK (layer IN ('L1_rules','L2_llm','L3_human')),
    verdict     text   NOT NULL CHECK (verdict IN ('pass','fail')),
    reason      text,
    ts          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE topic_taxonomy (
    topic_key  text    PRIMARY KEY,
    label      text    NOT NULL,
    seeded     boolean NOT NULL DEFAULT true,
    active     boolean NOT NULL DEFAULT true,
    evergreen  boolean NOT NULL DEFAULT false,  -- educational/timeless topic — timing rule input (LLD-03 §4)
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE nubra_features (
    id            bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature       text    NOT NULL,
    description   text    NOT NULL,
    status        text    NOT NULL CHECK (status IN ('live','upcoming')),
    category      text,
    seo_keywords  text[]  NOT NULL DEFAULT '{}',
    version       text    NOT NULL,          -- publish label, e.g. '2026-07-01'
    is_current    boolean NOT NULL DEFAULT false,
    published_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (feature, version)
);
-- exactly one current row per feature:
CREATE UNIQUE INDEX uq_nubra_features_current ON nubra_features(feature) WHERE is_current;

CREATE TABLE feedback (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_ref   jsonb  NOT NULL,   -- {"kind":"roundup","period":"daily","date":"2026-07-03"} | …
    category     text   NOT NULL,   -- 'useful'|'not_useful'|'wrong'|'idea'|…
    free_text    text,
    submitted_by text   NOT NULL,   -- SSO identity
    ts           timestamptz NOT NULL DEFAULT now()
);
```

`roundups.payload` / `.delivery` shapes:

```json
{"period":"daily", "date":"2026-07-03",
 "trending":[{"topic_key":"fo_expiry","velocity_z":2.4,"spread":2}],
 "broker_issues":[…], "feature_requests":[…], "rising_voices":[…],
 "opportunities":[{"id":123,"priority":84}], "content_proposals":[…],
 "nubra_watch":[{"kind":"complaint","url":"…","summary":"…","routed_to":"support"}],
 "stats":{…}}
-- full shape = LLD-03 §6.1 (the M4 source of truth); weekly adds `deltas`
```
```json
{"slack": {"status":"sent","ts":"2026-07-03T02:01:12Z"},
 "email": {"status":"sent","message_id":"…"}}
```

`recommended_timing`: `{"action":"now","window":"live","why":"thread +40%/hr"}` or
`{"action":"schedule","window":"08:45–09:15 IST","why":"pre-open reach"}`.

---

## 6. Indexes (beyond PKs) — with justification

```sql
-- social_items
CREATE INDEX ix_items_src_ext      ON social_items (source, external_id);          -- logical-uniqueness probe + engagement UPDATE
CREATE INDEX ix_items_ingested     ON social_items (ingested_at);                  -- watermark scans (every stage)
CREATE INDEX ix_items_item_id      ON social_items (item_id);                      -- joins from L2/L3 (no unique possible, D2)
CREATE INDEX ix_items_hash         ON social_items (content_hash);                 -- exact-dup probe
CREATE INDEX ix_items_thread       ON social_items (source, thread_id, created_at);-- conversation rebuild
CREATE INDEX ix_items_author       ON social_items (author_id);                    -- author_stats aggregation
CREATE INDEX ix_items_dup          ON social_items (duplicate_of) WHERE duplicate_of IS NOT NULL; -- dup audits

-- item_enrichment
CREATE INDEX ix_enrich_topic       ON item_enrichment (topic_key, ingested_at);    -- topic_daily build
CREATE INDEX ix_enrich_intent      ON item_enrichment (intent) WHERE NOT is_noise; -- issue/feature rollups

-- item_embeddings (per-partition HNSW, created via partition-creation job)
CREATE INDEX ix_embed_hnsw         ON item_embeddings USING hnsw (embedding vector_cosine_ops);

-- authors / opportunities / audit
CREATE INDEX ix_authors_src_handle ON authors (source, handle);                    -- (covered by UNIQUE; listed for intent)
CREATE INDEX ix_opps_day_prio      ON opportunities (day, priority DESC);          -- roundup top-N
CREATE INDEX ix_opps_unpinged      ON opportunities (priority) WHERE pinged_at IS NULL; -- ⑤a heads-up novelty query
CREATE INDEX ix_audit_ts           ON compliance_audit (ts);                       -- retention + audit pulls
CREATE INDEX ix_feedback_ts        ON feedback (ts);
```

Note: on partitioned tables every index above is propagated to each partition
automatically (declared on the parent).

---

## 7. Partitioning

- **Tables:** `social_items`, `item_enrichment`, `item_embeddings` — monthly `RANGE (ingested_at)`.
- **Naming:** `<table>_y2026m07` for `['2026-07-01','2026-08-01')`.
- **Creation:** `scripts/partition_job.py` (cron, monthly + at deploy) creates the **next 2
  months** if absent — HNSW indexes on new `item_embeddings` partitions come free via the
  parent-declared index:

```sql
CREATE TABLE IF NOT EXISTS social_items_y2026m08
  PARTITION OF social_items FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');
-- (same for item_enrichment / item_embeddings)
```

- **No DEFAULT partition** — a missing partition should fail loudly at ingest (bug in the
  creation job), not silently accumulate in a catch-all that blocks future partition DDL.
- **Integrity across partitions (D2):** weekly orphan check in `scripts/healthcheck.py`:
  `item_enrichment`/`item_embeddings` rows whose `item_id` no longer exists, and
  `duplicate_of` pointers to pruned items → alert (should only appear if retention and
  co-partitioning drift).

---

## 8. Retention jobs (`scripts/retention_job.py`, daily cron)

| Data | Policy | Mechanism |
|---|---|---|
| `social_items` / `item_enrichment` / `item_embeddings` | 180 d | `DROP TABLE <partition>` where the partition's upper bound < now()−180d (instant, no vacuum debt) |
| `social_items.raw` | ~60 d | per-partition batched `UPDATE … SET raw = NULL WHERE ingested_at < now()-interval '60 days' AND raw IS NOT NULL` |
| `opportunities`, `content_proposals` | 180 d | `DELETE WHERE day < now()-interval '180 days'` |
| L3 rollups (`topic_daily`·`issue_rollup`·`feature_rollup`) · `roundups` | 180 d | `DELETE WHERE day/date < now()-interval '180 days'` |
| `conversations` | 180 d | `DELETE WHERE last_seen < now()-interval '180 days'` |
| `compliance_audit` | 180 d (team decision 2026-07-03) | `DELETE WHERE ts < now()-interval '180 days'` |
| `authors`, `feature_keys`, taxonomy, features, feedback, `author_stats`, `pipeline_state` | reference/ops — kept | current-state, config, or FK target (`authors` is small — one row per distinct author — and referenced by `social_items`/`author_stats`) |

```text
retention_job:
  for tbl in (social_items, item_enrichment, item_embeddings):
      for part in partitions(tbl) where upper_bound < today - 180d:  DROP part
  scrub raw jsonb on partitions straddling the 60d line (batch 5k rows/txn)
  delete expired opportunities / content_proposals / rollup / roundup / conversations / compliance_audit rows
  log counts → trace_log
```

Partition + retention jobs connect as the **table-owner (admin) role** used by
`run_migrations.py` — neither `community_pipeline` nor `community_ro` has the DDL
privileges (`DROP TABLE` on partitions) these jobs need.

---

## 9. Migrations — convention + runner

- Files: `migrations/NNNN_description.sql`, immutable once merged; `0001_init.sql` = every
  DDL block in §§2–6 + the first three monthly partitions + roles/grants (§10). A file is
  applied at most once, keyed by its leading `version` number — renaming a merged file is a
  no-op (it never re-runs); only a new number runs.
- Tracking table (created by the runner if absent):

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     integer      PRIMARY KEY,
    filename    text         NOT NULL,
    dirty       boolean      NOT NULL DEFAULT false,  -- true = left half-applied; next run aborts
    applied_at  timestamptz  NOT NULL DEFAULT now()
);
```

- `run_migrations.py`: take `pg_advisory_lock(hashtext('nubra_community:migrate'))` → abort if any
  row is `dirty` → apply pending files in numeric order. For each file: mark its version `dirty`
  (committed), run the file in **one transaction per file**, then clear `dirty`. A crash
  mid-migration leaves the row `dirty` so it must be resolved by hand before the next run.
  `--dry-run` prints pending.

---

## 10. Roles & grants

```sql
CREATE ROLE community_pipeline LOGIN PASSWORD :'pipeline_pw';   -- all pipeline stages
CREATE ROLE community_ro       LOGIN PASSWORD :'ro_pw';         -- read-API + dashboard

GRANT CONNECT ON DATABASE nubra_community TO community_pipeline, community_ro;
GRANT USAGE  ON SCHEMA public            TO community_pipeline, community_ro;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO community_pipeline;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO community_pipeline;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO community_ro;
GRANT INSERT ON feedback TO community_ro;
GRANT USAGE  ON SEQUENCE feedback_id_seq TO community_ro;
GRANT UPDATE (status, status_updated_by, status_updated_at, dismissed_reason) ON opportunities TO community_ro;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO community_pipeline;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO community_ro;   -- new partitions stay readable
```

The column-restricted `UPDATE` on `opportunities` is the entire write surface of the
dashboard beyond `feedback` — matches build-plan §7.

---

## 11. Repository layer (`store/repositories.py`) — surface only

Semantics notes: every batch method is idempotent (safe to re-run on the same input);
`item` params are `SocialItem` dataclasses (LLD-02 §1).

```python
class SocialItemRepo:
    def insert_new(self, items: list[SocialItem]) -> list[int]: ...
        # per-source advisory lock; insert-if-absent on (source, external_id);
        # returns item_ids of genuinely new rows (D1)
    def update_engagement(self, source: str, external_id: str, engagement: dict) -> None: ...
    def set_dedup(self, sigs: list[tuple[int, bytes]],
                  dup_links: list[tuple[int, int]]) -> None: ...   # (item_id, minhash_sig), (dup, canonical)
    def fetch_window(self, since: datetime, until: datetime | None = None,
                     canonical_only: bool = False) -> Iterator[ItemRow]: ...
    def active_conversation_roots(self, hours: int = 24) -> list[ItemRow]: ...  # engagement re-fetch set

class AuthorRepo:
    def upsert(self, source: str, handle: str, meta: AuthorMeta) -> int: ...    # returns author_id

class EnrichmentRepo:
    def pending_items(self, watermark: datetime, limit: int) -> list[ItemRow]: ...
    def insert_batch(self, rows: list[EnrichmentRow]) -> None: ...

class EmbeddingRepo:
    def insert_batch(self, rows: list[tuple[int, datetime, list[float]]]) -> None: ...
    def nearest(self, embedding: list[float], k: int = 10,
                min_cosine: float | None = None) -> list[tuple[int, float]]: ...

class FeatureKeyRepo:                                     # D3 — centroid assignment
    def nearest_centroid(self, embedding: list[float]) -> tuple[str, float] | None: ...
    def create(self, label: str, centroid: list[float]) -> str: ...          # mints feat_NNNNN
    def fold_in(self, feature_key: str, embedding: list[float]) -> None: ... # running-mean centroid update

class RollupRepo:
    def upsert_topic_daily(self, rows: list[TopicDailyRow]) -> None: ...
    def upsert_issue_rollup(self, rows: list[IssueRollupRow]) -> None: ...
    def upsert_feature_rollup(self, rows: list[FeatureRollupRow]) -> None: ...
    def upsert_author_stats(self, rows: list[AuthorStatsRow]) -> None: ...

class ConversationRepo:
    def upsert_from_items(self, since: datetime) -> int: ...   # rebuild/refresh touched threads

class OpportunityRepo:
    def upsert_scored(self, rows: list[ScoredOpportunity]) -> None: ...  # ⑤a; UNIQUE(source,thread_id) → update priority
    def unpinged_above(self, threshold: int = 70) -> list[OpportunityRow]: ...
    def mark_pinged(self, ids: list[int]) -> None: ...
    def top_for_drafting(self, day: date, limit: int) -> list[OpportunityRow]: ...
    def attach_drafts(self, id: int, brand: str | None, rep: str | None,
                      timing: dict) -> None: ...                          # ⑤b
    def set_status(self, id: int, status: str, by: str) -> None: ...      # RO-role path (dashboard)

class PipelineStateRepo:
    def get(self, stage: str, source: str = '') -> PipelineState: ...
    def advance(self, stage: str, source: str, watermark: datetime,
                cursor: dict | None, items: int) -> None: ...
    def record_error(self, stage: str, source: str, error: str) -> None: ...

class ComplianceRepo:
    def log(self, draft_ref: dict, draft_text: str, layer: str,
            verdict: str, reason: str | None) -> None: ...

class RoundupRepo:      # save(period, date, payload) · mark_delivered(channel, meta) · get(period, date)
class FeedbackRepo:     # insert(object_ref, category, free_text, submitted_by)
class FeaturesRepo:     # current() -> list[FeatureRow] · seo_keywords() -> list[str] · publish(rows, version)
class TaxonomyRepo:     # active() -> dict[topic_key, label] · add(topic_key, label, seeded=False)
```

---

## 12. Open questions

1. `sample_item_ids` arrays point into 180d-pruned partitions — dashboards must tolerate
   missing items for rollup rows older than that (rollups outlive their samples by design).
2. If item volume grows ≫ 2k/day, revisit `ix_items_src_ext` probe cost vs. a hash-partitioned
   uniqueness side-table — not needed at current scale.
