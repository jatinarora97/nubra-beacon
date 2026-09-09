-- LinkedIn public-post collector (community/scrape/linkedin.py) — widen the
-- social_items source vocabulary. Partitioned parents propagate CHECKs.
ALTER TABLE social_items
    DROP CONSTRAINT IF EXISTS social_items_source_check,
    ADD CONSTRAINT social_items_source_check CHECK (source = ANY (ARRAY[
        'twitter','reddit','github','youtube','discord','telegram',
        'app_review','community_forum','instagram','linkedin']));
