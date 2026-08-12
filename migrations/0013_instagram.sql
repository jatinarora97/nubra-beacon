-- Instagram collector (plan: docs/instagram-collector-plan-2026-08-12.md).
-- Widens accepted values only; existing collectors unchanged.

ALTER TABLE social_items DROP CONSTRAINT social_items_source_check;
ALTER TABLE social_items ADD CONSTRAINT social_items_source_check
    CHECK (source IN (
        'twitter',
        'reddit',
        'github',
        'youtube',
        'discord',
        'telegram',
        'app_review',
        'community_forum',
        'instagram'
    ));

ALTER TABLE social_items DROP CONSTRAINT social_items_source_type_check;
ALTER TABLE social_items ADD CONSTRAINT social_items_source_type_check
    CHECK (source_type IN (
        'post',
        'comment',
        'tweet',
        'reply',
        'message',
        'review',
        'issue',
        'reel',
        'sidecar'
    ));

-- instagram_account: value = handle (no '@'); config = per-account overrides
ALTER TABLE watch_sources DROP CONSTRAINT watch_sources_kind_check;
ALTER TABLE watch_sources ADD CONSTRAINT watch_sources_kind_check
    CHECK (kind IN ('subreddit','x_hashtag','x_handle','x_query','keyword',
                    'youtube_query','github_query','forum','app',
                    'instagram_account'));
