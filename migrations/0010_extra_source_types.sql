-- Add source families used by the add-on intelligence collectors.
-- Existing Reddit/X collectors are unchanged; this only widens accepted values.

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
        'community_forum'
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
        'issue'
    ));
