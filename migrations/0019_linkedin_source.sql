-- LinkedIn public-post collector (community/scrape/linkedin.py) — widen the
-- social_items source vocabulary. Partitioned parents propagate CHECKs.
ALTER TABLE social_items
    DROP CONSTRAINT IF EXISTS social_items_source_check,
    ADD CONSTRAINT social_items_source_check CHECK (source = ANY (ARRAY[
        'twitter','reddit','github','youtube','discord','telegram',
        'app_review','community_forum','instagram','linkedin']));

-- Sources page manages linkedin queries like every other collector target
ALTER TABLE watch_sources
    DROP CONSTRAINT IF EXISTS watch_sources_kind_check,
    ADD CONSTRAINT watch_sources_kind_check CHECK (kind = ANY (ARRAY[
        'subreddit','x_hashtag','x_handle','x_query','keyword','youtube_query',
        'github_query','forum','app','instagram_account','linkedin_query']));
