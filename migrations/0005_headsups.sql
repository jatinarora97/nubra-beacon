-- 0005: headsups — persist every composed hourly heads-up (work plan
-- 2026-07-07, N3 follow-up). Previously the rendered markdown lived only in
-- out/messages/*-headsup.md; the DB held just the novelty stamps. One row per
-- composed heads-up: structured payload + rendered markdown + channel results.
-- Retention: 180d like everything else (locked decision).

CREATE TABLE headsups (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts       timestamptz NOT NULL DEFAULT now(),
    payload  jsonb NOT NULL,
    markdown text,
    delivery jsonb
);

CREATE INDEX ix_headsups_ts ON headsups (ts);
