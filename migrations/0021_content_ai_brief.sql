-- Content queue upgrade (2026-09-17): every brief carries an AI-ready
-- production brief (paste into an image/video/text AI -> finished asset),
-- and the queue covers all posting platforms incl. instagram + youtube.
ALTER TABLE social_recommendations
    ADD COLUMN IF NOT EXISTS ai_brief text;

ALTER TABLE social_recommendations
    DROP CONSTRAINT IF EXISTS social_recommendations_post_format_check,
    ADD CONSTRAINT social_recommendations_post_format_check CHECK (post_format = ANY
        (ARRAY['text_post','thread','carousel','short_video','product_demo',
               'seed_reply','image_post']));

-- GitHub joins the posting platforms (dev-flywheel content: examples,
-- discussions) — exception platform, min 1/day instead of 2.
ALTER TABLE social_recommendations
    DROP CONSTRAINT IF EXISTS social_recommendations_platform_check,
    ADD CONSTRAINT social_recommendations_platform_check CHECK (platform = ANY
        (ARRAY['linkedin','x','instagram','youtube','reddit','youtube_community',
               'github']));
