-- API Trading segment (docs/api-trading-section-plan-2026-08-25.md).

-- One row per item classified by the API-trader lens.
CREATE TABLE api_trader_items (
    -- no FK: social_items has a composite PK (partition-ready); joins are
    -- by item_id and the retention purge will cover this table explicitly
    item_id        bigint      PRIMARY KEY,
    -- 'irrelevant' rows = classified-and-rejected markers so the lens never
    -- re-spends on the same item; every consumer filters them out
    stage          text        NOT NULL CHECK (stage IN
                               ('exploring','first_api','building','scaling','churning','irrelevant')),
    first_api_type text        CHECK (first_api_type IN ('broker','any','unclear')),
    layer          text,
    kind           text,
    tools          jsonb       NOT NULL DEFAULT '[]',
    gist           text,
    friction_theme text,
    working_theme  text,
    classified_at  timestamptz NOT NULL DEFAULT now(),
    model          text
);
CREATE INDEX api_trader_items_stage_idx ON api_trader_items (stage);
CREATE INDEX api_trader_items_kind_idx  ON api_trader_items (kind);

-- Competitor grounding: what tracked players ship / announce. Auto rows come
-- from the weekly landscape job; manual rows from the dashboard form.
CREATE TABLE landscape_features (
    id           serial      PRIMARY KEY,
    competitor   text        NOT NULL,
    feature      text        NOT NULL,
    status       text        NOT NULL DEFAULT 'shipped'
                             CHECK (status IN ('shipped','upcoming','rumored')),
    evidence_url text,
    first_seen   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now(),
    added_by     text        NOT NULL DEFAULT 'auto',
    notes        text,
    UNIQUE (competitor, feature)
);
