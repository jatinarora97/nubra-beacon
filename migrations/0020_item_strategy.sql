-- Strategy detection over ALL items (Explore + API-trading Data columns).
-- Absence-based like item_enrichment: a row per judged item, is_strategy=false
-- rows are markers so gated non-strategies are never re-bought. No FK on
-- item_id (social_items has a composite, partition-ready PK).
CREATE TABLE IF NOT EXISTS item_strategy (
    item_id          bigint PRIMARY KEY,
    is_strategy      boolean NOT NULL,
    strategy_raw     text,             -- verbatim rule text quoted from the post
    strategy_summary text,             -- LLM-normalized description of the rules
    model            text NOT NULL,
    classified_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_item_strategy_flag
    ON item_strategy (is_strategy) WHERE is_strategy;
