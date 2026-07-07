-- Keyword watch (work plan N11): a fifth source kind. A keyword fans out to
-- the sources enabled in config, e.g. {"x": true, "reddit": true}.
ALTER TABLE watch_sources DROP CONSTRAINT watch_sources_kind_check;
ALTER TABLE watch_sources ADD CONSTRAINT watch_sources_kind_check
    CHECK (kind IN ('subreddit','x_hashtag','x_handle','x_query','keyword'));
ALTER TABLE watch_sources ADD COLUMN config jsonb NOT NULL DEFAULT '{}'::jsonb;
