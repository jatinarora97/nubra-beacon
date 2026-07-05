-- User-managed collection sources (added from the UI, consumed on the next
-- scrape run). Registry lists become the SEED; this table is the source of
-- truth thereafter. `active=false` rows are kept (soft off / suggestions).

CREATE TABLE watch_sources (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind        text   NOT NULL CHECK (kind IN ('subreddit','x_hashtag','x_handle','x_query')),
    value       text   NOT NULL,               -- normalized: no r/, @, # prefixes
    category    text,                          -- brokers | market_trading | investing_pf | fno_algo | custom
    active      boolean NOT NULL DEFAULT true,
    added_by    text    NOT NULL DEFAULT 'ui', -- 'seed' | 'ui' | 'discovery'
    note        text,                          -- e.g. why discovery suggested it
    created_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (kind, value)
);
