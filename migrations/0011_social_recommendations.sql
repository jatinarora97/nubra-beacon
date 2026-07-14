-- Social media recommendation workflow.
-- Human approval is required before publishing; no auto-posting is introduced here.

CREATE TABLE IF NOT EXISTS social_post_recommendations (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_key     text NOT NULL UNIQUE,
    title                 text NOT NULL,
    summary               text NOT NULL,
    recommendation_type   text NOT NULL,
    target_persona        text,
    platform              text NOT NULL,
    format_family         text NOT NULL,
    priority_score        numeric NOT NULL DEFAULT 0,
    status                text NOT NULL DEFAULT 'suggested'
                          CHECK (status IN (
                              'suggested',
                              'shortlisted',
                              'needs_design',
                              'draft_ready',
                              'approved',
                              'published',
                              'rejected'
                          )),
    mapped_features       jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_signals        jsonb NOT NULL DEFAULT '[]'::jsonb,
    reason                text NOT NULL,
    post_angle            text NOT NULL,
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_recs_status_score
    ON social_post_recommendations (status, priority_score DESC);

CREATE INDEX IF NOT EXISTS ix_social_recs_created
    ON social_post_recommendations (created_at DESC);

CREATE TABLE IF NOT EXISTS social_post_drafts (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_id  bigint NOT NULL REFERENCES social_post_recommendations(id) ON DELETE CASCADE,
    channel            text NOT NULL,
    draft_copy         text NOT NULL,
    creative_brief     text NOT NULL,
    prompt_version     text NOT NULL DEFAULT 'deterministic-v1',
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_drafts_recommendation
    ON social_post_drafts (recommendation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS social_post_approval_events (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_id  bigint NOT NULL REFERENCES social_post_recommendations(id) ON DELETE CASCADE,
    old_status         text,
    new_status         text NOT NULL,
    actor              text NOT NULL DEFAULT 'system',
    note               text,
    created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_social_approval_events_recommendation
    ON social_post_approval_events (recommendation_id, created_at DESC);
