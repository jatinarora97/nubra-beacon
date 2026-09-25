-- Watch-targets for the four add-on collectors become UI-manageable
-- (house pattern: watch_sources = source of truth, registry = seed).
--   youtube_query : value = YouTube search query; category retail|api_algo
--   github_query  : value = GitHub issue-search query
--   forum         : value = forum base/sitemap URL; config = {platform, broker, name, sitemap_url?}
--   app           : value = app display name; config = {broker, apple_id?, google_package?}
ALTER TABLE watch_sources DROP CONSTRAINT watch_sources_kind_check;
ALTER TABLE watch_sources ADD CONSTRAINT watch_sources_kind_check
    CHECK (kind IN ('subreddit','x_hashtag','x_handle','x_query','keyword',
                    'youtube_query','github_query','forum','app'));
