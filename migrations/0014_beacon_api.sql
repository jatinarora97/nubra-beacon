-- Beacon read-only API (docs/beacon-api-surface-2026-08-17.md, locked 2026-08-17).

-- Per-consumer keys: secret shown once at mint, only its sha256 stored.
CREATE TABLE api_keys (
    key_id       serial PRIMARY KEY,
    key_hash     text        NOT NULL UNIQUE,
    label        text        NOT NULL,
    created_by   text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    last_used_at timestamptz,
    revoked_at   timestamptz
);

-- Who pulled what (beacon API calls only; internal dashboard routes untouched).
CREATE TABLE beacon_api_log (
    id      bigserial   PRIMARY KEY,
    key_id  int         REFERENCES api_keys(key_id),
    route   text        NOT NULL,
    params  jsonb,
    status  int         NOT NULL,
    ts      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX beacon_api_log_ts_idx ON beacon_api_log (ts);

-- Full-text search for /items/search (websearch syntax: OR, quoted phrases).
ALTER TABLE social_items ADD COLUMN text_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', left(text, 8000))) STORED;
CREATE INDEX social_items_text_tsv_idx ON social_items USING gin (text_tsv);

-- Keyset-cursor ordering for /items (ingested_at DESC, item_id DESC).
CREATE INDEX IF NOT EXISTS social_items_ingested_id_idx
    ON social_items (ingested_at DESC, item_id DESC);
