-- API-trading content queue rides the social_recommendations engine as a
-- lens (plan: docs/api-content-queue-plan-2026-09-09.md).
ALTER TABLE social_recommendations
    ADD COLUMN IF NOT EXISTS lens text NOT NULL DEFAULT 'general',
    ADD COLUMN IF NOT EXISTS seed_url text;

CREATE INDEX IF NOT EXISTS ix_social_recs_lens_status
    ON social_recommendations (lens, status, day DESC);

-- The api_trading lens seeds reddit/YouTube-community threads with reply
-- briefs — widen the platform and format vocabularies for it.
ALTER TABLE social_recommendations
    DROP CONSTRAINT IF EXISTS social_recommendations_platform_check,
    ADD CONSTRAINT social_recommendations_platform_check CHECK (platform = ANY
        (ARRAY['linkedin','x','instagram','youtube','reddit','youtube_community'])),
    DROP CONSTRAINT IF EXISTS social_recommendations_post_format_check,
    ADD CONSTRAINT social_recommendations_post_format_check CHECK (post_format = ANY
        (ARRAY['text_post','thread','carousel','short_video','product_demo','seed_reply']));
