-- Isolated social recommendation store. No existing table or constraint is changed.

CREATE TABLE IF NOT EXISTS social_recommendation_runs (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status          text NOT NULL CHECK (status IN ('running','succeeded','failed','skipped')),
    model           text NOT NULL,
    prompt_version  text NOT NULL,
    context_version text NOT NULL,
    window_days     integer NOT NULL CHECK (window_days BETWEEN 1 AND 90),
    stats           jsonb NOT NULL DEFAULT '{}'::jsonb,
    error           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    completed_at    timestamptz
);

CREATE INDEX IF NOT EXISTS ix_social_rec_runs_created
    ON social_recommendation_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS social_recommendations (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id              bigint NOT NULL REFERENCES social_recommendation_runs(id) ON DELETE CASCADE,
    day                 date NOT NULL,
    recommendation_key  text NOT NULL,
    segment             text NOT NULL CHECK (segment IN ('retail','api')),
    platform            text NOT NULL CHECK (platform IN ('linkedin','x','instagram','youtube')),
    post_format         text NOT NULL CHECK (post_format IN
                            ('text_post','thread','carousel','short_video','product_demo')),
    title               text NOT NULL,
    hook                text NOT NULL,
    body                text NOT NULL,
    cta                 text NOT NULL,
    exact_copy          text NOT NULL,
    hashtags            text[] NOT NULL DEFAULT '{}',
    mapped_features     jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_evidence     jsonb NOT NULL DEFAULT '[]'::jsonb,
    rationale           text NOT NULL,
    visual_brief        text NOT NULL,
    recommended_timing  text,
    priority_score      numeric NOT NULL CHECK (priority_score BETWEEN 0 AND 100),
    status              text NOT NULL DEFAULT 'draft' CHECK (status IN
                            ('draft','approved','rejected','published')),
    compliance_status   text NOT NULL CHECK (compliance_status IN ('passed','failed')),
    model               text NOT NULL,
    prompt_version      text NOT NULL,
    context_version     text NOT NULL,
    edited_by           text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, recommendation_key)
);

CREATE INDEX IF NOT EXISTS ix_social_recs_day_segment_priority
    ON social_recommendations (day DESC, segment, priority_score DESC);
CREATE INDEX IF NOT EXISTS ix_social_recs_status
    ON social_recommendations (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS social_recommendation_events (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_id   bigint NOT NULL REFERENCES social_recommendations(id) ON DELETE CASCADE,
    event_type          text NOT NULL CHECK (event_type IN ('edited','approved','rejected','published')),
    actor               text NOT NULL,
    note                text,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_rec_events_recommendation
    ON social_recommendation_events (recommendation_id, created_at DESC);
