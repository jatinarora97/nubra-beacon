-- 0023: health monitoring (Slack alerts) — three create-only tables.
-- job_runs: one row per cron invocation (written by runner.py via
--   community/health/ledger.py; never allowed to fail a pipeline run).
-- health_state: per-check alert state (dedupe/reminder/resolve) + internal
--   rows (_epoch, watchdog_heartbeat, digest_heartbeat).
-- resource_samples: host/DB metrics sampled by the watchdog (disk, memory,
--   load, DB size, process start times) for trend/ETA checks.
-- Retention: the 180d purge job does not exist yet (backlog P1); include these
-- tables when it is written.

CREATE TABLE job_runs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job           text        NOT NULL,   -- run-local | morning-build | source:<name> | stage:<name>
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    status        text        NOT NULL CHECK (status IN
                    ('running','ok','degraded','failed','skipped_locked')),
    failed_stages text[]      NOT NULL DEFAULT '{}',
    stats         jsonb,
    error         text
);
CREATE INDEX ix_job_runs_job_started ON job_runs (job, started_at DESC);
CREATE INDEX ix_job_runs_started     ON job_runs (started_at DESC);

CREATE TABLE health_state (
    check_key        text        PRIMARY KEY,
    level            text        NOT NULL DEFAULT 'ok' CHECK (level IN ('ok','warn','crit')),
    detail           text,
    since            timestamptz NOT NULL DEFAULT now(),
    last_seen        timestamptz NOT NULL DEFAULT now(),
    last_alerted_at  timestamptz,
    consecutive_ok   integer     NOT NULL DEFAULT 0
);

CREATE TABLE resource_samples (
    ts      timestamptz      NOT NULL DEFAULT now(),
    metric  text             NOT NULL,
    value   double precision NOT NULL
);
CREATE INDEX ix_resource_samples_metric_ts ON resource_samples (metric, ts DESC);
