-- Emergent-topic discovery (work plan E1): clustered `other:*` chatter becomes
-- SUGGESTED taxonomy rows that a human activates (same pattern as discovered
-- hashtags). status supersedes the vestigial boolean `active` (kept in sync,
-- nothing reads it today) — existing rows are all the static seed => 'active'.
ALTER TABLE topic_taxonomy ADD COLUMN status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'suggested', 'rejected'));
ALTER TABLE topic_taxonomy ADD COLUMN suggested_why text;
ALTER TABLE topic_taxonomy ADD COLUMN suggested_count integer;
ALTER TABLE topic_taxonomy ADD COLUMN suggested_at timestamptz;
