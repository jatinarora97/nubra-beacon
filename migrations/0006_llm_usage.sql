-- 0006: llm_usage — one row per LLM call (sync) or per submitted batch (batch=true).
-- Cost is computed at WRITE time in community/llm/trace.py from its dated price
-- table and stored, so the dashboard never re-prices history after a rate change.
-- langfuse_trace_id links the row to the Langfuse generation when keys are set.

CREATE TABLE llm_usage (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts                 timestamptz NOT NULL DEFAULT now(),
    run_id             text NOT NULL,            -- one per ./cm invocation (process-scoped)
    stage              text NOT NULL,            -- scrape|clean|enrich|aggregate|score|draft|compose|dispatch|api|other
    purpose            text NOT NULL,            -- '<module>.<function>' of the caller
    model              text NOT NULL,
    input_tokens       integer NOT NULL DEFAULT 0,
    output_tokens      integer NOT NULL DEFAULT 0,
    cost_usd           numeric(10, 6),           -- NULL = model missing from price table
    duration_ms        integer,
    batch              boolean NOT NULL DEFAULT false,
    langfuse_trace_id  text,
    metadata           jsonb
);

CREATE INDEX ix_llm_usage_ts     ON llm_usage (ts);
CREATE INDEX ix_llm_usage_run    ON llm_usage (run_id);

COMMENT ON TABLE llm_usage IS
    'One row per LLM call (batch API: one row per submitted batch, batch=true, '
    'aggregate tokens). Written by community/llm/trace.py; cost priced at write '
    'time. Surfaced on /llm and the Overview KPI.';
