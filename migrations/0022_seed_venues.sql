-- Seed-venue correctness (intern feedback 2026-09-23): a seed reply's
-- platform must match where the target thread lives — broker forums and
-- Stack Overflow become first-class venues instead of masquerading as reddit.
ALTER TABLE social_recommendations
    DROP CONSTRAINT IF EXISTS social_recommendations_platform_check,
    ADD CONSTRAINT social_recommendations_platform_check CHECK (platform = ANY
        (ARRAY['linkedin','x','instagram','youtube','reddit','youtube_community',
               'github','forum','stackoverflow']));
