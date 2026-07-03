-- Nubra Community Manager · 0001_init.sql
-- Source of truth: docs/nubra-community-manager-lld-01-data-layer-2026-07-03.md
-- 18 tables in 5 layers. Local build note: DB roles/grants (LLD-01 §10) are a prod
-- concern and are not created here (single local user).

CREATE EXTENSION IF NOT EXISTS vector;

-- ── L1 RAW ────────────────────────────────────────────────────────────────

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

CREATE TABLE social_items (
    item_id       bigint      GENERATED ALWAYS AS IDENTITY,
    source        text        NOT NULL CHECK (source IN
                    ('twitter','reddit','github','youtube','discord','telegram','app_review')),
    source_type   text        NOT NULL CHECK (source_type IN
                    ('post','comment','tweet','reply','message','review','issue')),
    external_id   text        NOT NULL,
    parent_id     text,
    thread_id     text,
    author_id     bigint      NOT NULL REFERENCES authors(author_id),
    text          text        NOT NULL,
    lang          text,
    url           text,
    content_hash  char(64)    NOT NULL,        -- sha256 of normalized text; NOT unique (arch §4.1)
    minhash_sig   bytea,                       -- LeanMinHash bytes; NULL until dedup pass / too short
    duplicate_of  bigint,                      -- item_id of canonical; NULL = canonical (logical FK)
    engagement    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    raw           jsonb,
    created_at    timestamptz NOT NULL,        -- source time
    ingested_at   timestamptz NOT NULL DEFAULT now(),   -- arrival time = watermark + partition clock
    PRIMARY KEY (source, external_id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- ── L2 ENRICH (co-partitioned) ────────────────────────────────────────────

CREATE TABLE item_enrichment (
    item_id      bigint      NOT NULL,          -- logical FK → social_items.item_id
    ingested_at  timestamptz NOT NULL,          -- copied from the item; co-partition key
    audience     text        CHECK (audience IN
                   ('active_trader','long_term_investor','beginner','influencer','other')),
    intent       text        NOT NULL CHECK (intent IN
                   ('complaint','feature_request','question','praise',
                    'comparison','how_to','news_opinion','spam')),
    topic_key    text        NOT NULL,
    sentiment    real        CHECK (sentiment BETWEEN -1 AND 1),
    entities     jsonb       NOT NULL DEFAULT '{}'::jsonb,
    is_noise     boolean     NOT NULL DEFAULT false,
    model        text        NOT NULL,          -- 'claude-haiku-*' | 'kw-fallback' | 'rule-prefilter' | 'rule-guardrail'
    enriched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, ingested_at)
) PARTITION BY RANGE (ingested_at);

CREATE TABLE item_embeddings (
    item_id      bigint      NOT NULL,
    ingested_at  timestamptz NOT NULL,
    embedding    vector(384) NOT NULL,          -- multilingual-e5-small
    model        text        NOT NULL DEFAULT 'multilingual-e5-small',
    PRIMARY KEY (item_id, ingested_at)
) PARTITION BY RANGE (ingested_at);

-- ── L3 AGGREGATE ──────────────────────────────────────────────────────────

CREATE TABLE conversations (
    source              text        NOT NULL,
    thread_id           text        NOT NULL,
    root_item_id        bigint,
    item_count          integer     NOT NULL DEFAULT 0,
    participant_count   integer     NOT NULL DEFAULT 0,
    velocity            real,                   -- acceleration: items last 3h / max(items prior 3h, 1)
    peak_engagement     integer,
    dominant_topic_key  text,
    is_nubra_watch      boolean     NOT NULL DEFAULT false,
    headsup_at          timestamptz,            -- last heads-up appearance (Nubra-watch per-day dedup)
    first_seen          timestamptz,
    last_seen           timestamptz,
    PRIMARY KEY (source, thread_id)
);

CREATE TABLE topic_daily (
    topic_key       text    NOT NULL,
    day             date    NOT NULL,
    count           integer NOT NULL DEFAULT 0,       -- canonical items only
    velocity_z      real,
    spread          smallint,
    engagement_sum  bigint,
    audience_mix    jsonb,
    headsup_at      timestamptz,                      -- first surfaced as newly-rising today
    headsup_count   smallint NOT NULL DEFAULT 0,      -- times featured today (recurrence boost)
    PRIMARY KEY (topic_key, day)
);

CREATE TABLE issue_rollup (
    broker          text    NOT NULL,
    issue_key       text    NOT NULL,
    day             date    NOT NULL,
    count           integer NOT NULL DEFAULT 0,
    severity        real,
    sentiment_avg   real,
    sample_item_ids bigint[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (broker, issue_key, day)
);

CREATE TABLE feature_keys (
    feature_key      text        PRIMARY KEY,          -- 'feat_00042'
    canonical_label  text        NOT NULL,
    centroid         vector(384),                      -- NULL in local mode (embeddings skipped)
    phrase_count     integer     NOT NULL DEFAULT 1,
    is_active        boolean     NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feature_rollup (
    feature_key       text    NOT NULL REFERENCES feature_keys(feature_key),
    day               date    NOT NULL,
    canonical_label   text    NOT NULL,
    count             integer NOT NULL DEFAULT 0,
    brokers_mentioned text[]  NOT NULL DEFAULT '{}',
    sample_item_ids   bigint[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (feature_key, day)
);

CREATE TABLE author_stats (
    author_id          bigint  PRIMARY KEY REFERENCES authors(author_id),
    voice_score        real    NOT NULL DEFAULT 0,
    contributions      integer NOT NULL DEFAULT 0,
    communities        integer NOT NULL DEFAULT 0,
    relevance          real,
    authenticity_flag  boolean NOT NULL DEFAULT false,
    updated_at         timestamptz NOT NULL DEFAULT now()
);

-- ── L4 OUTPUT ─────────────────────────────────────────────────────────────

CREATE TABLE opportunities (
    id                  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source              text    NOT NULL,
    thread_id           text    NOT NULL,
    day                 date    NOT NULL,
    priority            smallint NOT NULL CHECK (priority BETWEEN 0 AND 100),
    matched_insight     jsonb,
    brand_reply         text,
    rep_reply           text,
    recommended_timing  jsonb,
    status              text    NOT NULL DEFAULT 'suggested'
                          CHECK (status IN ('suggested','acted','dismissed')),
    status_updated_by   text,
    status_updated_at   timestamptz,
    dismissed_reason    text CHECK (dismissed_reason IN
                          ('not_relevant','already_handled','too_late','too_risky','other')),
    pinged_at           timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source, thread_id)
);

CREATE TABLE content_proposals (
    id                  bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    day                 date    NOT NULL,
    rank                smallint NOT NULL CHECK (rank BETWEEN 1 AND 3),
    format              text    NOT NULL CHECK (format IN
                          ('infographic','reel','short','post','thread')),
    hook                text    NOT NULL,
    outline             jsonb   NOT NULL DEFAULT '[]'::jsonb,
    why                 text,
    rides_signal        jsonb   NOT NULL,
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

-- ── L5 OPS/REF ────────────────────────────────────────────────────────────

CREATE TABLE pipeline_state (
    stage            text  NOT NULL,     -- 'ingest'|'dedup'|'enrich'|'aggregate'|'score'|'recommend'|'roundup'
    source           text  NOT NULL DEFAULT '',
    watermark        timestamptz,        -- arrival clock (ingested_at; enriched_at for aggregate)
    cursor           jsonb,
    last_success_at  timestamptz,
    last_error       text,
    last_error_at    timestamptz,
    items_last_run   integer,
    PRIMARY KEY (stage, source)
);

CREATE TABLE compliance_audit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    draft_ref   jsonb  NOT NULL,
    draft_text  text   NOT NULL,
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
    evergreen  boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE nubra_features (
    id            bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feature       text    NOT NULL,
    description   text    NOT NULL,
    status        text    NOT NULL CHECK (status IN ('live','upcoming')),
    category      text,
    seo_keywords  text[]  NOT NULL DEFAULT '{}',
    version       text    NOT NULL,
    is_current    boolean NOT NULL DEFAULT false,
    published_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (feature, version)
);
CREATE UNIQUE INDEX uq_nubra_features_current ON nubra_features(feature) WHERE is_current;

CREATE TABLE feedback (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_ref   jsonb  NOT NULL,
    category     text   NOT NULL,
    free_text    text,
    submitted_by text   NOT NULL,
    ts           timestamptz NOT NULL DEFAULT now()
);

-- ── Partitions (2026-06 → 2026-10; prod: partition_job creates rolling) ──

DO $$
DECLARE
    t text; m date;
BEGIN
    FOREACH t IN ARRAY ARRAY['social_items','item_enrichment','item_embeddings'] LOOP
        m := date '2026-06-01';
        WHILE m < date '2026-11-01' LOOP
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I_y%sm%s PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
                t, to_char(m, 'YYYY'), to_char(m, 'MM'), t, m, m + interval '1 month');
            m := m + interval '1 month';
        END LOOP;
    END LOOP;
END $$;

-- ── Indexes (beyond PKs) ──────────────────────────────────────────────────

CREATE INDEX ix_items_src_ext      ON social_items (source, external_id);
CREATE INDEX ix_items_ingested     ON social_items (ingested_at);
CREATE INDEX ix_items_item_id      ON social_items (item_id);
CREATE INDEX ix_items_hash         ON social_items (content_hash);
CREATE INDEX ix_items_thread       ON social_items (source, thread_id, created_at);
CREATE INDEX ix_items_author       ON social_items (author_id);
CREATE INDEX ix_items_dup          ON social_items (duplicate_of) WHERE duplicate_of IS NOT NULL;
CREATE INDEX ix_enrich_topic       ON item_enrichment (topic_key, ingested_at);
CREATE INDEX ix_enrich_intent      ON item_enrichment (intent) WHERE NOT is_noise;
CREATE INDEX ix_opps_day_prio      ON opportunities (day, priority DESC);
CREATE INDEX ix_opps_unpinged      ON opportunities (priority) WHERE pinged_at IS NULL;
CREATE INDEX ix_audit_ts           ON compliance_audit (ts);
CREATE INDEX ix_feedback_ts        ON feedback (ts);
