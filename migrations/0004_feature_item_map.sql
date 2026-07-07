-- 0004: feature_item_map — exactly-once ledger of which item fed which feature
-- key (work plan 2026-07-07, B3). Fixes the additive feature_rollup upsert:
-- counts are recomputed FROM this map (replay-safe), and centroid folding in
-- _feature_key_for happens only when an item first enters the map.

CREATE TABLE feature_item_map (
    item_id     bigint PRIMARY KEY,
    feature_key text   NOT NULL REFERENCES feature_keys(feature_key),
    day         date   NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_feature_item_map_key_day ON feature_item_map (feature_key, day);
