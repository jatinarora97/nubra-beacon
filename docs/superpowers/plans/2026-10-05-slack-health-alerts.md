# Slack Health Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A morning Slack status message plus an immediate critical-alert watchdog that tell the team whether Beacon's jobs, scrapers, LLM calls, data freshness, resources and DB partitions are healthy.

**Architecture:** A new `community/health/` package holds small check functions that return `Result(key, level, detail)`. A pure state machine (`state.py`) turns results into alert / remind / resolve decisions stored in a `health_state` table. `runner.py` records every cron job into a `job_runs` ledger. Two new commands, `./cm watchdog` (every 20 min, critical only) and `./cm health-digest` (daily 08:05 IST), run from the VM crontab and post to a dedicated Slack alerts webhook. Everything ships in the Docker image; nothing depends on host files except the crontab lines, `.env` and the backup `touch`.

**Tech Stack:** Python 3.12, psycopg 3 (via `community.store.db`), Typer (`runner.py`), httpx (`dispatch/slack.py`), Postgres, pytest (tests are `unittest.TestCase` classes, like `tests/test_extra_sources.py`).

**Spec:** `docs/superpowers/specs/2026-10-05-slack-health-alerts-design.md` (read it first; this plan implements it).

## Global Constraints

- **Do not commit unless the user has asked you to.** Every "Commit" step below applies only after they say so; otherwise skip it. When committing, end the message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- **Additive only.** One new migration that only creates tables (no ALTER/DROP/UPDATE/DELETE). Edits to existing files are limited to `runner.py`, `community/dispatch/slack.py`, `community/config/registry.yaml`, `community/config/env.example`, `deploy/crontab.prod`, `deploy/crontab.prod.utc`, `deploy/README-prod.md`, `CLAUDE.md`.
- **Pipeline safety.** Nothing in `community/health/` may make a pipeline run fail, skip or slow down. The ledger functions never raise. The watchdog and digest never take the pipeline advisory lock and never use `flock`.
- **Messages are emoji-free** (locked decision). Use plain tags: `[CRITICAL]`, `[RESOLVED]`, `[TEST]`.
- **Prod-only sending.** All Slack posts go through `community.dispatch.slack.send`, which already skips unless `MODE=prod`.
- **No fallback to the approvals webhook by default.** `SLACK_WEBHOOK_URL` carries SSO access approvals. Health alerts use `SLACK_ALERTS_WEBHOOK_URL`; falling back is opt-in via `health.fallback_to_default_webhook`.
- **`registry.yaml` is bind-mounted from the VM**, so every `health:` setting needs an in-code default (`community/health/config.py`); the registry block only overrides.
- **Time zone:** use the fixed-offset `IST` from `community.config.log` (no `zoneinfo`/tzdata). Database timestamps are timezone-aware.
- **Style:** `from __future__ import annotations`, module docstring explaining why, broad `except Exception` marked `# noqa: BLE001`, logging via `community.config.log.get_logger`.
- **Migration number:** `0023_health_monitoring.sql` (latest existing is 0022). If another migration takes 0023 first, renumber this file; nothing in code depends on the number.

## Deviations from the spec (decided while planning, from reading the code)

1. **Source staleness** uses `pipeline_state.last_success_at` (collector last succeeded) for all sources, because several daily sources can legitimately add zero new items. The "newest item" check (`social_items.max(ingested_at)`) is applied only to `health.sources.volume_sources` (default `["twitter"]`).
2. **Query timeout** is 20 s (set through the `PGOPTIONS` environment variable inside the watchdog/digest process), not 5 s, because the enrichment-backlog query scans a week of items.
3. **Added check `job_failed:<job>`**: critical when the last 2 finished runs of a job all failed (exception), so a job that starts but always crashes is not mistaken for healthy.
4. **Monitoring epoch:** the first watchdog run stores a `_epoch` row in `health_state`; scheduled slots before it are ignored, so the first deploy cannot raise a false "job overdue".
5. **Hourly probes** (Anthropic key, Apify usage) run only when the watchdog fires in minutes 0-19 of an hour, or whenever the check is already critical; this needs no extra state.
6. **Enrichment backlog threshold** defaults to 200 items; calibrate against real data in Task 15.
7. **Job timing is explicit per job** (`start_window_min`, `grace_min`, `crit_after_missed`, `max_run_min`). A run still `running` longer than `max_run_min` is critical (`job_slow:<job>`); this is how "morning build not finished by 07:30" is enforced (max 90 min from 06:00). It replaces the spec's generic "running more than 3 h" warning.

## Review Focus

Failure modes the spec implies but a straight reading of the tasks would not test; each has a pinning test in the task named.

1. **First run after deploy with an empty ledger** must not alert (no false "job overdue"). Pinned in Task 9.
2. **The 07:00 hourly run skipping behind the 06:00 morning build** (or the `flock -n` skip, which leaves no ledger row) must not count as missed. A stuck holder older than 3 h must NOT excuse it. Pinned in Task 5.
3. **Slack outage:** if the post fails, the alert must be retried on the next watchdog run, not silently marked as sent. Pinned in Task 12.
4. **A check that raises** must not kill the watchdog and must not falsely resolve an open critical alert. Pinned in Task 12.
5. **Dev machines (Windows, no `/proc`, no `statvfs`) and sources with no `pipeline_state` row** must not crash the collectors or checks. Pinned in Tasks 8 and 10.

## Validation already done on this plan (2026-10-05)

Before handing this plan over, every code block in Tasks 1-14 was materialized into a throwaway copy of the repo (outside the working tree) and exercised:
- **Tests:** the plan's own 168 health tests pass, together with the pre-existing `tests/test_extra_sources.py` (173 passed), with the `runner.py` and `slack.py` edits applied as written.
- **SQL on real Postgres 17:** the migration, the partition-bounds regex over `pg_get_expr`, the ledger and state upserts, the freshness / backlog / source / LLM queries, `./cm watchdog` and `./cm health-digest` dry-runs, and a full alert lifecycle (one critical alert, no repeat on the next run, `[RESOLVED]` after two clean runs).
- **Not validated here (Task 15 covers them):** the Linux-only collectors (`/proc`, `statvfs` on a real bind mount), the real `anthropic` / Apify / twitterapi.io probes, real Slack delivery, and behaviour against the full existing schema (including pgvector) and real data.

---

## Prerequisites (do once, not a task)

Work from the repo root in Git Bash. There is no `.venv` in this checkout yet.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # heavy (torch); lighter alternative below
# lighter: .venv/Scripts/python -m pip install "psycopg[binary]" python-dotenv pyyaml typer httpx pytest pydantic anthropic
export CM_PYTHON=.venv/Scripts/python                      # the ./cm wrapper honours CM_PYTHON
docker compose up -d postgres                              # dev DB on localhost:5544
./cm migrate                                               # applies migrations 0001-0022 locally
```

Test command used throughout (run from the repo root):

```bash
"$CM_PYTHON" -m pytest tests/<file> -v
```

Baseline before changing anything: `"$CM_PYTHON" -m pytest -q` and `./cm doctor` (note which checks already FAIL locally so they are not blamed on this work).

## File Structure

Create:
- `migrations/0023_health_monitoring.sql` — `job_runs`, `health_state`, `resource_samples`.
- `community/health/__init__.py` — empty package marker.
- `community/health/model.py` — `Result`, level constants, `owns` decorator.
- `community/health/config.py` — `DEFAULTS` and `load()` (deep-merge of `registry.yaml: health:`).
- `community/health/ledger.py` — never-raising `job_runs` writers plus `recent_runs`.
- `community/health/schedule.py` — pure expected-slot / missed-slot logic.
- `community/health/state.py` — `Row`, `Decision`, pure `decide`, and `health_state` persistence.
- `community/health/notify.py` — message formatting and webhook resolution/posting.
- `community/health/resources.py` — collectors, `resource_samples` I/O, pure evaluators, `check_resources`.
- `community/health/checks_jobs.py` — job overdue / failed / stuck / stage-failing, watchdog heartbeat.
- `community/health/checks_data.py` — partitions, freshness, enrichment backlog, sources.
- `community/health/checks_llm.py` — Anthropic key, credits, LLM usage.
- `community/health/engine.py` — `run_checks`, `build_plan`, `run_watchdog`, `run_digest`.
- `community/health/digest.py` — digest rendering and context collection.
- Tests: `tests/test_health_migration.py`, `test_health_config.py`, `test_health_ledger.py`, `test_health_runner.py`, `test_health_schedule.py`, `test_health_state.py`, `test_health_notify.py`, `test_health_resources.py`, `test_health_checks_jobs.py`, `test_health_checks_data.py`, `test_health_checks_llm.py`, `test_health_engine.py`, `test_health_digest.py`.

Modify: `runner.py`, `community/dispatch/slack.py`, `community/config/registry.yaml`, `community/config/env.example`, `deploy/crontab.prod`, `deploy/crontab.prod.utc`, `deploy/README-prod.md`, `CLAUDE.md`.

---

### Task 1: Migration 0023 (three new tables)

**Files:**
- Create: `migrations/0023_health_monitoring.sql`
- Test: `tests/test_health_migration.py`

**Interfaces:**
- Produces: tables `job_runs(id, job, started_at, finished_at, status, failed_stages, stats, error)`, `health_state(check_key, level, detail, since, last_seen, last_alerted_at, consecutive_ok)`, `resource_samples(ts, metric, value)`. Every later task reads/writes exactly these column names.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_migration.py
from __future__ import annotations

import pathlib
import re
import unittest

MIGRATION = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "0023_health_monitoring.sql"


class HealthMigrationTests(unittest.TestCase):
    def test_file_exists_and_creates_the_three_tables(self):
        sql = MIGRATION.read_text()
        for table in ("job_runs", "health_state", "resource_samples"):
            self.assertRegex(sql, rf"CREATE TABLE {table}\b")

    def test_migration_is_additive_only(self):
        sql = re.sub(r"--.*", "", MIGRATION.read_text())  # ignore comments
        for forbidden in ("ALTER ", "DROP ", "DELETE ", "UPDATE ", "TRUNCATE "):
            self.assertNotIn(forbidden, sql.upper(), f"{forbidden.strip()} must not appear")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_migration.py -v`
Expected: FAIL (FileNotFoundError for the migration).

- [ ] **Step 3: Write the migration**

```sql
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_migration.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Preview and apply against the local dev DB**

Run: `./cm migrate --dry-run` — Expected output includes `pending: 0023_health_monitoring.sql` (note: the `--dry-run` flag is handled by `python migrations/run_migrations.py --dry-run`; if `./cm migrate --dry-run` rejects the flag, run `"$CM_PYTHON" migrations/run_migrations.py --dry-run`).
Run: `./cm migrate` — Expected: `applied: 0023_health_monitoring.sql` then `migrations up to date`.
Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "\dt job_runs health_state resource_samples"` — Expected: 3 rows listed.

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add migrations/0023_health_monitoring.sql tests/test_health_migration.py
git commit -m "Health monitoring: job_runs, health_state, resource_samples tables" -m "Create-only migration; no existing table touched.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Package skeleton, `Result` model, defaults and config loader

**Files:**
- Create: `community/health/__init__.py`, `community/health/model.py`, `community/health/config.py`
- Test: `tests/test_health_config.py`

**Interfaces:**
- Produces:
  - `model.OK`, `model.WARN`, `model.CRIT` (strings `"ok"|"warn"|"crit"`), `model.RANK` (`dict[str,int]`).
  - `model.Result(key: str, level: str, detail: str, hint: str = "")` frozen dataclass.
  - `model.owns(*prefixes)` decorator that sets `fn.PREFIXES = prefixes`.
  - `config.DEFAULTS: dict` and `config.load(registry: dict | None = None) -> dict` (a fresh deep-merged copy; reads `settings.registry["health"]` when `registry` is None).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_config.py
from __future__ import annotations

import unittest

from community.health import config
from community.health.model import CRIT, OK, RANK, WARN, Result, owns


class ModelTests(unittest.TestCase):
    def test_levels_rank_in_severity_order(self):
        self.assertLess(RANK[OK], RANK[WARN])
        self.assertLess(RANK[WARN], RANK[CRIT])

    def test_result_defaults_and_immutability(self):
        r = Result("disk", CRIT, "92% used")
        self.assertEqual(r.hint, "")
        with self.assertRaises(Exception):
            r.level = OK  # frozen

    def test_owns_records_prefixes(self):
        @owns("a:", "b")
        def check(cfg, now):
            return []
        self.assertEqual(check.PREFIXES, ("a:", "b"))


class ConfigTests(unittest.TestCase):
    def test_defaults_when_registry_has_no_health_block(self):
        cfg = config.load({})
        self.assertEqual(cfg["remind_hours"], 6)
        self.assertEqual(cfg["muted"], ["reddit"])
        self.assertFalse(cfg["fallback_to_default_webhook"])
        self.assertEqual(cfg["slack_webhook_env"], "SLACK_ALERTS_WEBHOOK_URL")
        self.assertIn("run-local", cfg["jobs"])

    def test_registry_overrides_merge_deeply(self):
        cfg = config.load({"health": {"remind_hours": 2,
                                      "resources": {"disk_crit_pct": 95}}})
        self.assertEqual(cfg["remind_hours"], 2)
        self.assertEqual(cfg["resources"]["disk_crit_pct"], 95)
        self.assertEqual(cfg["resources"]["disk_warn_pct"], 80)  # untouched default

    def test_load_returns_a_copy(self):
        a = config.load({})
        a["muted"].append("x")
        self.assertEqual(config.load({})["muted"], ["reddit"])

    def test_run_local_schedule_matches_the_prod_crontab(self):
        hours = config.load({})["jobs"]["run-local"]["hours"]
        self.assertEqual(sorted(hours), [0] + list(range(7, 24)))

    def test_every_default_job_declares_its_timing(self):
        for name, job in config.load({})["jobs"].items():
            for key in ("hours", "start_window_min", "grace_min",
                        "crit_after_missed", "max_run_min"):
                self.assertIn(key, job, f"{name} is missing {key}")
            self.assertLess(job["start_window_min"], job["grace_min"] + 1, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_config.py -v`
Expected: FAIL (`ModuleNotFoundError: community.health`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/__init__.py
```

(empty file)

```python
# community/health/model.py
"""Shared result type for health checks.

A check function takes (cfg, now) and returns list[Result]. `owns(...)` tags it
with the key prefixes it is responsible for, so the engine can tell "this key
is no longer reported because the problem cleared" from "this key is missing
because the check crashed".
"""
from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
WARN = "warn"
CRIT = "crit"
RANK = {OK: 0, WARN: 1, CRIT: 2}


@dataclass(frozen=True)
class Result:
    key: str
    level: str
    detail: str
    hint: str = ""


def owns(*prefixes: str):
    def deco(fn):
        fn.PREFIXES = prefixes
        return fn
    return deco
```

```python
# community/health/config.py
"""Health settings: in-code DEFAULTS deep-merged with registry.yaml `health:`.

registry.yaml is bind-mounted from the prod VM and shadows the image copy, so a
release cannot rely on a new block being present there — everything the checks
need has a default here; the registry only overrides.
"""
from __future__ import annotations

import copy

from community.config.settings import settings

DEFAULTS: dict = {
    "remind_hours": 6,
    "resolve_after_ok": 2,
    "slack_webhook_env": "SLACK_ALERTS_WEBHOOK_URL",
    "fallback_to_default_webhook": False,   # SLACK_WEBHOOK_URL carries SSO approvals
    "muted": ["reddit"],                    # known broken (parked) — digest line only
    "lock_exempt_minutes": 180,             # a lock holder younger than this excuses a skipped slot
    "job_failing_runs": 2,
    "stage_failing_runs": 3,
    # Mirrors deploy/crontab.prod (IST). weekdays: Mon=0 .. Sun=6 (Saturday=5).
    # start_window_min: how late after the slot a run may START and still count
    #   (cron fires on the minute; keep it far below the slot interval).
    # grace_min: how long after the slot before "never started" is declared.
    # crit_after_missed: consecutive missed slots that make it critical.
    # max_run_min: a run still `running` longer than this is critical (job_slow).
    "jobs": {
        "run-local": {"hours": [0] + list(range(7, 24)), "minute": 0,
                      "start_window_min": 10, "grace_min": 15,
                      "crit_after_missed": 3, "max_run_min": 180},
        "morning-build": {"hours": [6], "minute": 0,   # must finish by ~07:30
                          "start_window_min": 10, "grace_min": 20,
                          "crit_after_missed": 1, "max_run_min": 90},
        "source:instagram": {"hours": [2], "minute": 0,
                             "start_window_min": 10, "grace_min": 20,
                             "crit_after_missed": 1, "max_run_min": 180},
        "stage:compose": {"hours": [10], "minute": 0, "weekdays": [5],
                          "start_window_min": 10, "grace_min": 15,
                          "crit_after_missed": 1, "max_run_min": 45},
        # dispatch is chained after compose with && in the crontab, so it starts
        # whenever compose finishes — give it a wide start window
        "stage:dispatch": {"hours": [10], "minute": 0, "weekdays": [5],
                           "start_window_min": 60, "grace_min": 65,
                           "crit_after_missed": 1, "max_run_min": 45},
    },
    "partitions": {
        "tables": ["social_items", "item_enrichment", "item_embeddings"],
        "crit_days": 10,
        "warn_days": 35,
    },
    "sources": {
        # registry source name -> pipeline_state.source (stage='ingest')
        "map": {"twitter": "twitter", "reddit": "reddit", "youtube": "youtube",
                "github": "github", "broker_communities": "community_forum",
                "app_reviews": "app_review", "instagram": "instagram",
                "linkedin": "linkedin"},
        "max_age_hours": {"twitter": 10, "reddit": 12, "default": 30},
        "volume_sources": ["twitter"],
        "volume_max_age_hours": 10,
    },
    "freshness": {
        "topics_after_ist": 8.0,          # hours, IST
        "daily_roundup_after_ist": 7.75,  # 07:45
        "weekly_roundup_after_ist": 11.0, # Saturday only
    },
    "enrichment_backlog_warn": 200,
    "llm": {"spend_multiple": 3.0, "spend_floor_usd": 1.0, "no_calls_hours": 24},
    "credits": {"apify_warn_pct": 80, "apify_crit_pct": 98},
    "resources": {
        "disk_warn_pct": 80, "disk_crit_pct": 90,
        "disk_eta_warn_days": 21, "disk_eta_crit_days": 7,
        "mem_warn_pct": 20, "mem_crit_pct": 10, "mem_crit_samples": 3,
        "load_warn_per_core": 2.0, "swap_warn_pct": 50,
        "cron_log_warn_mb": 500, "backup_crit_hours": 30,
        "restart_crit_count": 2,
    },
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            out[key] = _merge(base[key], value)
        else:
            out[key] = value
    return out


def load(registry: dict | None = None) -> dict:
    reg = settings.registry if registry is None else registry
    return copy.deepcopy(_merge(DEFAULTS, reg.get("health") or {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_config.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health tests/test_health_config.py
git commit -m "Health: Result model, in-code defaults, registry-merged config" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Job ledger (never raises)

**Files:**
- Create: `community/health/ledger.py`
- Test: `tests/test_health_ledger.py`

**Interfaces:**
- Consumes: tables from Task 1.
- Produces (all in `community.health.ledger`):
  - `summarize(result) -> tuple[str, list[str]]` — `("ok"|"degraded", failed_stage_names)`; a stage failed when its value is a dict containing `"error"` (same rule as `runner._run_local_inner`).
  - `start_job(job: str) -> int | None` — inserts a `running` row; `None` on any DB problem.
  - `finish_job(job_id: int | None, status: str, *, failed_stages: list[str] | None = None, seconds: float | None = None, error: str | None = None) -> None`.
  - `record_skipped(job: str) -> None` — inserts a `skipped_locked` row.
  - `recent_runs(hours: float) -> list[dict]` — rows `{job,status,started_at,finished_at,failed_stages,error}` ordered by `started_at`; may raise (used only by checks).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_ledger.py
from __future__ import annotations

import unittest
from unittest.mock import patch

from community.health import ledger


class SummarizeTests(unittest.TestCase):
    def test_all_stages_ok(self):
        self.assertEqual(ledger.summarize({"scrape": {"inserted": 3}, "clean": {}}), ("ok", []))

    def test_failed_stage_degrades_the_run(self):
        status, failed = ledger.summarize({"scrape": {}, "enrich": {"error": "boom"}})
        self.assertEqual(status, "degraded")
        self.assertEqual(failed, ["enrich"])

    def test_non_dict_result_is_ok(self):
        self.assertEqual(ledger.summarize(None), ("ok", []))


class LedgerNeverRaisesTests(unittest.TestCase):
    def test_start_job_returns_none_when_db_is_down(self):
        with patch("community.store.db.one", side_effect=RuntimeError("db down")):
            self.assertIsNone(ledger.start_job("run-local"))

    def test_finish_job_swallows_db_errors(self):
        with patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            ledger.finish_job(5, "ok", seconds=1.2)  # must not raise

    def test_finish_job_with_no_id_is_a_noop(self):
        with patch("community.store.db.execute") as ex:
            ledger.finish_job(None, "ok")
        ex.assert_not_called()

    def test_record_skipped_swallows_db_errors(self):
        with patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            ledger.record_skipped("run-local")  # must not raise


class LedgerWritesTests(unittest.TestCase):
    def test_start_job_inserts_a_running_row(self):
        with patch("community.store.db.one", return_value={"id": 42}) as one:
            self.assertEqual(ledger.start_job("morning-build"), 42)
        sql, params = one.call_args[0]
        self.assertIn("INSERT INTO job_runs", sql)
        self.assertEqual(params, ("morning-build",))

    def test_finish_job_updates_status_and_failed_stages(self):
        with patch("community.store.db.execute") as ex:
            ledger.finish_job(7, "degraded", failed_stages=["enrich"], seconds=3.14)
        sql, params = ex.call_args[0]
        self.assertIn("UPDATE job_runs", sql)
        self.assertEqual(params[0], "degraded")
        self.assertEqual(params[1], ["enrich"])
        self.assertEqual(params[-1], 7)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_ledger.py -v`
Expected: FAIL (`cannot import name 'ledger'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/ledger.py
"""Job ledger — one job_runs row per cron invocation (spec §5).

Every writer here NEVER raises: a ledger problem must not fail, skip or slow a
pipeline run (same rule as community/llm/trace.py:record). The db module is
imported lazily so even an import problem cannot break the importing runner.
"""
from __future__ import annotations

from community.config.log import get_logger

log = get_logger("health.ledger")


def summarize(result) -> tuple[str, list[str]]:
    """("ok"|"degraded", failed stage names) from a run's all_stats dict."""
    if not isinstance(result, dict):
        return "ok", []
    failed = [name for name, stats in result.items()
              if isinstance(stats, dict) and "error" in stats]
    return ("degraded" if failed else "ok"), failed


def start_job(job: str) -> int | None:
    try:
        from community.store import db
        row = db.one(
            "INSERT INTO job_runs (job, status) VALUES (%s, 'running') RETURNING id",
            (job,))
        return row["id"]
    except Exception as e:  # noqa: BLE001 — ledger must never affect the run
        log.warning("job_runs start failed for %s (%s) — run unaffected", job, e)
        return None


def finish_job(job_id: int | None, status: str, *, failed_stages: list[str] | None = None,
               seconds: float | None = None, error: str | None = None) -> None:
    if job_id is None:
        return
    try:
        from community.store import db
        stats = db.jsonb({"seconds": seconds}) if seconds is not None else None
        db.execute(
            "UPDATE job_runs SET finished_at = now(), status = %s, "
            "failed_stages = %s::text[], stats = %s, error = %s WHERE id = %s",
            (status, failed_stages or [], stats, error, job_id))
    except Exception as e:  # noqa: BLE001
        log.warning("job_runs finish failed for id %s (%s) — run unaffected", job_id, e)


def record_skipped(job: str) -> None:
    try:
        from community.store import db
        db.execute(
            "INSERT INTO job_runs (job, status, finished_at) "
            "VALUES (%s, 'skipped_locked', now())", (job,))
    except Exception as e:  # noqa: BLE001
        log.warning("job_runs skip-record failed for %s (%s)", job, e)


def recent_runs(hours: float) -> list[dict]:
    """Runs started in the last `hours`, oldest first. Used by checks (may raise)."""
    from community.store import db
    return db.query(
        "SELECT job, status, started_at, finished_at, failed_stages, error FROM job_runs "
        "WHERE started_at > now() - (%s * interval '1 hour') ORDER BY started_at",
        (hours,))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_ledger.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/ledger.py tests/test_health_ledger.py
git commit -m "Health: never-raising job_runs ledger" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Record jobs from `runner.py` (the one live-path change)

**Files:**
- Modify: `runner.py` (`_with_pipeline_lock` at lines 76-84, `stage` at 94-105, `_run_local_inner` end at 159-160, `source` at 195-207)
- Test: `tests/test_health_runner.py`

**Interfaces:**
- Consumes: `ledger.start_job`, `ledger.finish_job`, `ledger.record_skipped`, `ledger.summarize` (Task 3).
- Produces: `_with_pipeline_lock(label: str, fn, job: str | None = None) -> None` (records under `job or label`; fn's return value is summarized); job names `run-local`, `morning-build`, `source:<name>`, `stage:<name>`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_runner.py
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import typer

import runner


class WithPipelineLockLedgerTests(unittest.TestCase):
    def test_lock_busy_records_a_skip_and_exits_zero(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=None), \
             patch("community.health.ledger.record_skipped") as skipped, \
             patch("community.health.ledger.start_job") as start:
            with self.assertRaises(typer.Exit) as ctx:
                runner._with_pipeline_lock("run-local", lambda: {"scrape": {}})
        self.assertEqual(ctx.exception.exit_code, 0)
        skipped.assert_called_once_with("run-local")
        start.assert_not_called()

    def test_clean_run_is_recorded_ok_and_lock_released(self):
        lock = MagicMock()
        with patch.object(runner, "_acquire_pipeline_lock", return_value=lock), \
             patch("community.health.ledger.start_job", return_value=7) as start, \
             patch("community.health.ledger.finish_job") as finish:
            runner._with_pipeline_lock("morning-build", lambda: {"scrape": {"inserted": 3}})
        start.assert_called_once_with("morning-build")
        self.assertEqual(finish.call_args.args, (7, "ok"))
        lock.close.assert_called_once()

    def test_failed_stage_marks_the_run_degraded(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.health.ledger.start_job", return_value=8), \
             patch("community.health.ledger.finish_job") as finish:
            runner._with_pipeline_lock("run-local", lambda: {"enrich": {"error": "x"}})
        self.assertEqual(finish.call_args.args, (8, "degraded"))
        self.assertEqual(finish.call_args.kwargs["failed_stages"], ["enrich"])

    def test_exception_is_recorded_failed_and_still_raised(self):
        lock = MagicMock()

        def boom():
            raise RuntimeError("pipeline exploded")

        with patch.object(runner, "_acquire_pipeline_lock", return_value=lock), \
             patch("community.health.ledger.start_job", return_value=9), \
             patch("community.health.ledger.finish_job") as finish:
            with self.assertRaises(RuntimeError):
                runner._with_pipeline_lock("run-local", boom)
        self.assertEqual(finish.call_args.args, (9, "failed"))
        self.assertIn("RuntimeError", finish.call_args.kwargs["error"])
        lock.close.assert_called_once()

    def test_explicit_job_name_overrides_the_label(self):
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.health.ledger.start_job", return_value=1) as start, \
             patch("community.health.ledger.finish_job"):
            runner._with_pipeline_lock("source-instagram", lambda: {}, job="source:instagram")
        start.assert_called_once_with("source:instagram")

    def test_a_broken_ledger_never_breaks_a_run(self):
        ran = []
        with patch.object(runner, "_acquire_pipeline_lock", return_value=MagicMock()), \
             patch("community.store.db.one", side_effect=RuntimeError("db down")), \
             patch("community.store.db.execute", side_effect=RuntimeError("db down")):
            runner._with_pipeline_lock("run-local", lambda: ran.append(1) or {})
        self.assertEqual(ran, [1])


class StageAndSourceCommandTests(unittest.TestCase):
    def test_stage_success_is_recorded(self):
        with patch.object(runner, "_run_stage", return_value={}), \
             patch("community.health.ledger.start_job", return_value=3) as start, \
             patch("community.health.ledger.finish_job") as finish:
            runner.stage("compose")
        start.assert_called_once_with("stage:compose")
        self.assertEqual(finish.call_args.args, (3, "ok"))

    def test_stage_failure_is_recorded_and_exits_1(self):
        with patch.object(runner, "_run_stage", side_effect=RuntimeError("bad")), \
             patch("community.health.ledger.start_job", return_value=4), \
             patch("community.health.ledger.finish_job") as finish:
            with self.assertRaises(SystemExit) as ctx:
                runner.stage("dispatch")
        self.assertEqual(ctx.exception.code, 1)
        self.assertEqual(finish.call_args.args, (4, "failed"))

    def test_source_command_passes_a_source_job_name_and_returns_stats(self):
        captured = {}

        def fake_lock(label, fn, job=None):
            captured["label"], captured["job"], captured["result"] = label, job, fn()

        with patch.object(runner, "_with_pipeline_lock", side_effect=fake_lock), \
             patch("community.scrape.extra_sources.run",
                   return_value={"instagram": {"inserted": 2}}):
            runner.source("instagram")
        self.assertEqual(captured["job"], "source:instagram")
        self.assertEqual(captured["result"], {"instagram": {"inserted": 2}})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_runner.py -v`
Expected: FAIL (`_with_pipeline_lock() got an unexpected keyword argument 'job'` / ledger never called).

- [ ] **Step 3: Edit `runner.py`**

Replace `_with_pipeline_lock` (currently lines 76-84):

```python
def _with_pipeline_lock(label: str, fn, job: str | None = None) -> None:
    """Run `fn` under the pipeline lock and record the outcome in job_runs
    (community/health/ledger.py — every ledger call swallows its own errors, so
    exit codes, locking and stage isolation are exactly as before)."""
    from community.health import ledger
    job = job or label
    lock = _acquire_pipeline_lock()
    if lock is None:
        ledger.record_skipped(job)
        typer.echo(f"[{label}] another pipeline run is active — skipping this run")
        raise typer.Exit(0)
    job_id = ledger.start_job(job)
    t0 = time.time()
    try:
        result = fn()
    except BaseException as exc:
        ledger.finish_job(job_id, "failed", seconds=round(time.time() - t0, 1),
                          error=f"{type(exc).__name__}: {str(exc)[:300]}")
        raise
    else:
        status, failed = ledger.summarize(result)
        ledger.finish_job(job_id, status, failed_stages=failed,
                          seconds=round(time.time() - t0, 1))
    finally:
        lock.close()  # releases the advisory lock
```

Replace the `stage` command body (currently lines 94-105):

```python
@app.command()
def stage(name: str) -> None:
    if name not in STAGE_MODULES:
        raise typer.BadParameter(f"unknown stage {name!r}; one of {list(STAGE_MODULES)}")
    from community.config.log import get_logger
    from community.health import ledger
    log = get_logger("runner")
    log.info("stage %s starting (single-stage run)", name)
    job_id = ledger.start_job(f"stage:{name}")
    t0 = time.time()
    try:
        _run_stage(name)
    except Exception as exc:  # noqa: BLE001
        log.exception("stage %s FAILED", name)
        ledger.finish_job(job_id, "failed", seconds=round(time.time() - t0, 1),
                          error=f"{type(exc).__name__}: {str(exc)[:300]}")
        raise SystemExit(1)
    ledger.finish_job(job_id, "ok", seconds=round(time.time() - t0, 1))
```

Make `_run_local_inner` return its stats: change its signature line to `def _run_local_inner(skip_scrape: bool, skip_enrich: bool) -> dict:` and add as the last line of the function (after the `for p in (all_stats.get("dispatch") ...` loop):

```python
    return all_stats
```

Replace the `source` command (currently lines 195-207):

```python
@app.command()
def source(name: str) -> None:
    """Run ONE add-on collector standalone (e.g. the 02:00 IST instagram+
    whisper slot — cadence: nightly sources). Takes the pipeline lock so it
    never overlaps a run-local/morning-build."""
    from community.scrape import extra_sources

    def _one() -> dict:
        out = extra_sources.run(daily=True, only=[name])
        stats = out.get(name, {"error": f"unknown source {name!r}"})
        typer.echo(json.dumps(stats, default=str))
        return {name: stats}

    _with_pipeline_lock(f"source-{name}", _one, job=f"source:{name}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_runner.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Local behaviour check (exit codes and output unchanged, ledger rows written)**

Run: `./cm run-local --skip-scrape --skip-enrich; echo "exit=$?"` — Expected: the same stage log lines as before and `exit=0`.
Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT job, status, failed_stages, started_at FROM job_runs ORDER BY id DESC LIMIT 3"` — Expected: a `run-local` row with status `ok` or `degraded`.

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add runner.py tests/test_health_runner.py
git commit -m "runner: record every job in job_runs (errors swallowed)" -m "_with_pipeline_lock, stage and source now write job_runs; exit codes, lock semantics and stage isolation unchanged.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 5: Expected-slot / missed-run logic (pure)

**Files:**
- Create: `community/health/schedule.py`
- Test: `tests/test_health_schedule.py`

**Interfaces:**
- Consumes: `community.config.log.IST`.
- Produces (in `community.health.schedule`):
  - `Run(job: str, status: str, started_at: datetime, finished_at: datetime | None = None)` frozen dataclass.
  - `slots_between(job_cfg: dict, start: datetime, end: datetime) -> list[datetime]` — IST-aware slot instants with `start <= slot <= end`; `job_cfg` keys: `hours: list[int]`, `minute: int` (default 0), `weekdays: list[int] | None` (Mon=0).
  - `trailing_missed(job: str, job_cfg: dict, runs: list[Run], now: datetime, *, epoch: datetime, lookback_hours: float = 48, exempt_min: float = 180) -> list[datetime]` — the **trailing** run of consecutive missed slots (a later satisfied slot resets it), only slots whose grace window has fully elapsed and that are `>= epoch`.

A slot is **due** once `slot + grace_min` has passed. It is **satisfied** when this job has an `ok|degraded|failed|running` run that started within `[slot - 2 min, slot + start_window_min]` (tight on purpose: a run at 10:00 must not excuse a missed 09:00), OR any other run (not `skipped_locked`) was holding the lock at the slot instant and had been running less than `exempt_min` minutes (so the 07:00 hourly queued behind the 06:00 morning build is excused, but a holder stuck for hours is not).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_schedule.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from community.config.log import IST
from community.health import schedule
from community.health.schedule import Run, slots_between, trailing_missed


def ist(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)  # 2026-10-05 is a Monday


RUN_LOCAL = {"hours": [0] + list(range(7, 24)), "minute": 0,
             "start_window_min": 10, "grace_min": 15}
MORNING = {"hours": [6], "minute": 0, "start_window_min": 10, "grace_min": 20}
WEEKLY = {"hours": [10], "minute": 0, "weekdays": [5],
          "start_window_min": 10, "grace_min": 15}


def local_runs(*hours, status="ok"):
    return [Run("run-local", status, ist(5, h), ist(5, h, 10)) for h in hours]


class SlotsTests(unittest.TestCase):
    def test_hourly_slots_for_one_day(self):
        slots = slots_between(RUN_LOCAL, ist(5, 0), ist(5, 23, 59))
        self.assertEqual([s.hour for s in slots], [0] + list(range(7, 24)))

    def test_weekday_filter_only_returns_saturday(self):
        slots = slots_between(WEEKLY, ist(5, 0), ist(11, 23))
        self.assertEqual(slots, [ist(10, 10)])  # Saturday 10 Oct

    def test_bounds_are_inclusive(self):
        self.assertEqual(slots_between(MORNING, ist(5, 6), ist(5, 6)), [ist(5, 6)])


class TrailingMissedTests(unittest.TestCase):
    def missed(self, runs, now, cfg=RUN_LOCAL, job="run-local", epoch=None, **kw):
        return trailing_missed(job, cfg, runs, now, epoch=epoch or ist(5, 0), **kw)

    def test_healthy_hourly_run_has_no_misses(self):
        self.assertEqual(self.missed(local_runs(7, 8, 9, 10, 11), ist(5, 12, 10)), [])

    def test_three_trailing_misses_are_reported(self):
        missed = self.missed(local_runs(7, 8), ist(5, 11, 30))
        self.assertEqual(missed, [ist(5, 9), ist(5, 10), ist(5, 11)])

    def test_a_later_run_resets_the_streak(self):
        self.assertEqual(self.missed(local_runs(7, 8, 10, 11), ist(5, 12, 10)), [])

    def test_a_run_at_the_next_slot_does_not_satisfy_the_previous_slot(self):
        runs = local_runs(10)
        window = timedelta(minutes=10)
        self.assertFalse(schedule._own_run_started(runs, "run-local", ist(5, 9), window))
        self.assertTrue(schedule._own_run_started(runs, "run-local", ist(5, 10), window))

    def test_slot_still_inside_its_grace_window_is_not_due(self):
        self.assertEqual(self.missed(local_runs(7, 8), ist(5, 9, 10)), [])

    def test_slots_before_the_epoch_are_ignored(self):
        self.assertEqual(self.missed([], ist(5, 12, 10), epoch=ist(5, 12)), [])

    def test_a_running_or_failed_run_still_counts_as_the_job_having_run(self):
        running = [Run("run-local", "running", ist(5, 7), None)]
        failed = [Run("run-local", "failed", ist(5, 7), ist(5, 7, 5))]
        self.assertEqual(self.missed(running, ist(5, 8, 10), epoch=ist(5, 7)), [])
        self.assertEqual(self.missed(failed, ist(5, 8, 10), epoch=ist(5, 7)), [])

    def test_hourly_slot_behind_the_morning_build_is_excused(self):
        # morning-build 06:00-07:25 holds the lock at 07:00, so 07:00 is excused
        # (slot 00:00 has no run and no holder: that earlier miss is reset by 07:00)
        runs = [Run("morning-build", "ok", ist(5, 6), ist(5, 7, 25))]
        self.assertEqual(self.missed(runs, ist(5, 8, 10)), [])

    def test_lock_busy_skip_alone_does_not_excuse_a_slot(self):
        runs = [Run("run-local", "skipped_locked", ist(5, 7), ist(5, 7))]
        self.assertEqual(self.missed(runs, ist(5, 8, 10), epoch=ist(5, 7)), [ist(5, 7)])

    def test_a_holder_stuck_for_hours_does_not_excuse_the_slot(self):
        runs = [Run("morning-build", "running", ist(5, 1), None)]  # 6 h old at 07:00
        missed = self.missed(runs, ist(5, 8, 10))
        self.assertIn(ist(5, 7), missed)

    def test_weekly_job_missed_on_saturday_only(self):
        self.assertEqual(self.missed([], ist(10, 11), cfg=WEEKLY, job="stage:compose"),
                         [ist(10, 10)])
        self.assertEqual(self.missed([], ist(9, 11), cfg=WEEKLY, job="stage:compose"), [])

    def test_morning_build_missed(self):
        self.assertEqual(self.missed([], ist(5, 8), cfg=MORNING, job="morning-build"),
                         [ist(5, 6)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_schedule.py -v`
Expected: FAIL (`cannot import name 'Run'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/schedule.py
"""Expected cron slots vs the job_runs ledger — pure functions, injected clock.

The slot list mirrors deploy/crontab.prod (registry `health.jobs`, IST). A slot
is "missed" only when its grace window has elapsed and nothing excuses it:
  - this job has a run that started in [slot - 2 min, slot + start_window_min]
    (tight: a run at the next slot must not excuse this one), or
  - another job was legitimately holding the pipeline lock at the slot instant
    (the 07:00 hourly queued behind the 06:00 morning build; `flock -n` skips
    leave no ledger row at all) and had been running < `exempt_min` minutes —
    a holder stuck for hours does NOT excuse anything.
A slot becomes due only after `slot + grace_min`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from community.config.log import IST

RAN = ("ok", "degraded", "failed", "running")  # the job process actually started


@dataclass(frozen=True)
class Run:
    job: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None


def slots_between(job_cfg: dict, start: datetime, end: datetime) -> list[datetime]:
    weekdays = job_cfg.get("weekdays")
    minute = job_cfg.get("minute", 0)
    day = start.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    last_day = end.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    while day <= last_day:
        if weekdays is None or day.weekday() in weekdays:
            for hour in job_cfg["hours"]:
                slot = day.replace(hour=hour, minute=minute)
                if start <= slot <= end:
                    out.append(slot)
        day += timedelta(days=1)
    return sorted(out)


def _own_run_started(runs: list[Run], job: str, slot: datetime, window: timedelta) -> bool:
    tolerance = timedelta(minutes=2)
    return any(r.job == job and r.status in RAN
               and slot - tolerance <= r.started_at <= slot + window for r in runs)


def _lock_holder_overlaps(runs: list[Run], slot: datetime, exempt_min: float) -> bool:
    for r in runs:
        if r.status == "skipped_locked" or r.started_at > slot:
            continue
        if r.finished_at is not None and r.finished_at < slot:
            continue
        if slot - r.started_at <= timedelta(minutes=exempt_min):
            return True
    return False


def trailing_missed(job: str, job_cfg: dict, runs: list[Run], now: datetime, *,
                    epoch: datetime, lookback_hours: float = 48,
                    exempt_min: float = 180) -> list[datetime]:
    grace = timedelta(minutes=job_cfg["grace_min"])
    window = timedelta(minutes=job_cfg.get("start_window_min", 10))
    start = max(now - timedelta(hours=lookback_hours), epoch)
    missed: list[datetime] = []
    for slot in slots_between(job_cfg, start, now - grace):
        if _own_run_started(runs, job, slot, window) \
                or _lock_holder_overlaps(runs, slot, exempt_min):
            missed = []  # recovered: only the trailing streak matters
        else:
            missed.append(slot)
    return missed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_schedule.py -v`
Expected: PASS (15 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/schedule.py tests/test_health_schedule.py
git commit -m "Health: pure expected-slot / missed-run logic" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Alert state machine and `health_state` persistence

**Files:**
- Create: `community/health/state.py`
- Test: `tests/test_health_state.py`

**Interfaces:**
- Consumes: `model.Result/OK/WARN/CRIT` (Task 2); table `health_state` (Task 1).
- Produces (in `community.health.state`):
  - `Row(key, level="ok", detail="", since=None, last_seen=None, last_alerted_at=None, consecutive_ok=0)` frozen dataclass.
  - `Decision(key, action, row, result, crit_since=None)` frozen dataclass; `action` in `"alert" | "remind" | "resolve" | "none"`.
  - `decide(prev: Row | None, res: Result, now: datetime, *, remind_hours: float = 6, resolve_after_ok: int = 2) -> Decision` (pure).
  - `load_states() -> dict[str, Row]`, `save(row: Row) -> None`, `get_epoch(now: datetime, create: bool = True) -> datetime` (with `create=False` it never writes: if no epoch is stored yet it just returns `now`; used by `--dry-run`).

Rules: warn/ok never alert. crit from non-crit → `alert`. crit persisting → `remind` only after `remind_hours` since `last_alerted_at`. A non-crit result after crit counts toward `resolve_after_ok` consecutive non-crit evaluations, then → `resolve` (flap guard).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_state.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from community.health import state
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Row, decide

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def row(level, *, since_h=1.0, alerted_h=None, ok=0, detail="d"):
    return Row("k", level, detail, NOW - timedelta(hours=since_h), NOW - timedelta(minutes=20),
               None if alerted_h is None else NOW - timedelta(hours=alerted_h), ok)


class DecideTests(unittest.TestCase):
    def test_new_critical_alerts(self):
        d = decide(None, Result("k", CRIT, "bad"), NOW)
        self.assertEqual(d.action, "alert")
        self.assertEqual((d.row.level, d.row.since, d.row.last_alerted_at), (CRIT, NOW, NOW))

    def test_critical_after_ok_or_warn_alerts(self):
        self.assertEqual(decide(row(OK), Result("k", CRIT, "x"), NOW).action, "alert")
        self.assertEqual(decide(row(WARN), Result("k", CRIT, "x"), NOW).action, "alert")

    def test_warn_and_ok_never_alert(self):
        self.assertEqual(decide(None, Result("k", WARN, "x"), NOW).action, "none")
        self.assertEqual(decide(row(OK), Result("k", WARN, "x"), NOW).action, "none")
        self.assertEqual(decide(row(WARN), Result("k", OK, "x"), NOW).action, "none")

    def test_warn_keeps_its_original_since(self):
        d = decide(row(WARN, since_h=30), Result("k", WARN, "still"), NOW)
        self.assertEqual(d.row.since, NOW - timedelta(hours=30))

    def test_level_change_resets_since(self):
        self.assertEqual(decide(row(OK, since_h=30), Result("k", WARN, "x"), NOW).row.since, NOW)

    def test_critical_inside_the_reminder_window_stays_quiet(self):
        prev = row(CRIT, alerted_h=2)
        d = decide(prev, Result("k", CRIT, "new detail"), NOW)
        self.assertEqual(d.action, "none")
        self.assertEqual(d.row.last_alerted_at, prev.last_alerted_at)
        self.assertEqual(d.row.detail, "new detail")

    def test_critical_past_the_reminder_window_reminds(self):
        prev = row(CRIT, since_h=10, alerted_h=6.5)
        d = decide(prev, Result("k", CRIT, "x"), NOW)
        self.assertEqual(d.action, "remind")
        self.assertEqual(d.row.last_alerted_at, NOW)
        self.assertEqual(d.crit_since, prev.since)

    def test_custom_remind_hours(self):
        prev = row(CRIT, alerted_h=2.5)
        self.assertEqual(decide(prev, Result("k", CRIT, "x"), NOW, remind_hours=2).action, "remind")

    def test_first_ok_after_critical_does_not_resolve_yet(self):
        d = decide(row(CRIT, alerted_h=1), Result("k", OK, "fine"), NOW)
        self.assertEqual(d.action, "none")
        self.assertEqual((d.row.level, d.row.consecutive_ok), (CRIT, 1))

    def test_second_consecutive_ok_resolves(self):
        prev = row(CRIT, since_h=3, alerted_h=1, ok=1)
        d = decide(prev, Result("k", OK, "fine"), NOW)
        self.assertEqual(d.action, "resolve")
        self.assertEqual(d.crit_since, prev.since)
        self.assertEqual((d.row.level, d.row.consecutive_ok), (OK, 0))

    def test_critical_again_resets_the_ok_streak(self):
        d = decide(row(CRIT, alerted_h=1, ok=1), Result("k", CRIT, "again"), NOW)
        self.assertEqual(d.row.consecutive_ok, 0)

    def test_drop_to_warn_after_critical_resolves_into_warn(self):
        prev = row(CRIT, alerted_h=1, ok=1)
        d = decide(prev, Result("k", WARN, "degraded"), NOW)
        self.assertEqual((d.action, d.row.level), ("resolve", WARN))


class PersistenceTests(unittest.TestCase):
    def test_load_states_maps_rows(self):
        db_rows = [{"check_key": "k", "level": "crit", "detail": None, "since": NOW,
                    "last_seen": NOW, "last_alerted_at": NOW, "consecutive_ok": 1}]
        with patch("community.store.db.query", return_value=db_rows):
            states = state.load_states()
        self.assertEqual(states["k"], Row("k", "crit", "", NOW, NOW, NOW, 1))

    def test_save_upserts_every_column(self):
        with patch("community.store.db.execute") as ex:
            state.save(Row("k", "warn", "d", NOW, NOW, None, 0))
        sql, params = ex.call_args[0]
        self.assertIn("ON CONFLICT (check_key) DO UPDATE", sql)
        self.assertEqual(params, ("k", "warn", "d", NOW, NOW, None, 0))

    def test_get_epoch_returns_existing_row(self):
        with patch("community.store.db.one", return_value={"since": NOW}), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW + timedelta(days=1)), NOW)
        ex.assert_not_called()

    def test_get_epoch_creates_it_on_first_run(self):
        with patch("community.store.db.one", return_value=None), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW), NOW)
        self.assertIn("_epoch", ex.call_args[0][0])

    def test_get_epoch_without_create_never_writes(self):
        with patch("community.store.db.one", return_value=None), \
             patch("community.store.db.execute") as ex:
            self.assertEqual(state.get_epoch(NOW, create=False), NOW)
        ex.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_state.py -v`
Expected: FAIL (`cannot import name 'state'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/state.py
"""Alert dedupe: per-check state in health_state and the pure transition rule.

ok/warn never alert. A check turning critical alerts once, reminds every
`remind_hours` while it stays critical, and resolves only after
`resolve_after_ok` consecutive non-critical evaluations (flap guard).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from community.health.model import CRIT, Result


@dataclass(frozen=True)
class Row:
    key: str
    level: str = "ok"
    detail: str = ""
    since: datetime | None = None
    last_seen: datetime | None = None
    last_alerted_at: datetime | None = None
    consecutive_ok: int = 0


@dataclass(frozen=True)
class Decision:
    key: str
    action: str  # alert | remind | resolve | none
    row: Row
    result: Result
    crit_since: datetime | None = None


def decide(prev: Row | None, res: Result, now: datetime, *,
           remind_hours: float = 6, resolve_after_ok: int = 2) -> Decision:
    if prev is None or prev.level != CRIT:
        if res.level == CRIT:
            return Decision(res.key, "alert",
                            Row(res.key, CRIT, res.detail, now, now, now, 0), res)
        same = prev is not None and prev.level == res.level and prev.since is not None
        since = prev.since if same else now
        alerted = prev.last_alerted_at if prev else None
        return Decision(res.key, "none",
                        Row(res.key, res.level, res.detail, since, now, alerted, 0), res)

    # prev is critical
    if res.level == CRIT:
        due = prev.last_alerted_at is None or \
            (now - prev.last_alerted_at) >= timedelta(hours=remind_hours)
        row = Row(res.key, CRIT, res.detail, prev.since, now,
                  now if due else prev.last_alerted_at, 0)
        return Decision(res.key, "remind" if due else "none", row, res,
                        crit_since=prev.since)
    oks = prev.consecutive_ok + 1
    if oks >= resolve_after_ok:
        row = Row(res.key, res.level, res.detail, now, now, prev.last_alerted_at, 0)
        return Decision(res.key, "resolve", row, res, crit_since=prev.since)
    row = Row(res.key, CRIT, prev.detail, prev.since, now, prev.last_alerted_at, oks)
    return Decision(res.key, "none", row, res, crit_since=prev.since)


def load_states() -> dict[str, Row]:
    from community.store import db
    return {r["check_key"]: Row(r["check_key"], r["level"], r["detail"] or "", r["since"],
                                r["last_seen"], r["last_alerted_at"], r["consecutive_ok"])
            for r in db.query("SELECT * FROM health_state")}


def save(row: Row) -> None:
    from community.store import db
    db.execute(
        """
        INSERT INTO health_state (check_key, level, detail, since, last_seen,
                                  last_alerted_at, consecutive_ok)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (check_key) DO UPDATE SET
            level = EXCLUDED.level, detail = EXCLUDED.detail, since = EXCLUDED.since,
            last_seen = EXCLUDED.last_seen, last_alerted_at = EXCLUDED.last_alerted_at,
            consecutive_ok = EXCLUDED.consecutive_ok
        """,
        (row.key, row.level, row.detail, row.since, row.last_seen,
         row.last_alerted_at, row.consecutive_ok))


def get_epoch(now: datetime, create: bool = True) -> datetime:
    """When monitoring began (first watchdog run). Scheduled slots before this
    are ignored so a fresh deploy cannot raise a false 'job overdue'."""
    from community.store import db
    existing = db.one("SELECT since FROM health_state WHERE check_key = '_epoch'")
    if existing:
        return existing["since"]
    if not create:
        return now
    db.execute("INSERT INTO health_state (check_key, level, since, last_seen) "
               "VALUES ('_epoch', 'ok', %s, %s) ON CONFLICT (check_key) DO NOTHING",
               (now, now))
    return now
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_state.py -v`
Expected: PASS (17 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/state.py tests/test_health_state.py
git commit -m "Health: alert state machine (alert/remind/resolve) + health_state persistence" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Slack notifier (dedicated alerts webhook) and `slack.send` webhook override

**Files:**
- Modify: `community/dispatch/slack.py:50-66` (`send` signature + URL selection)
- Create: `community/health/notify.py`
- Test: `tests/test_health_notify.py`

**Interfaces:**
- Consumes: `slack.send`, `model.Result`, config dict from `config.load()` (keys `slack_webhook_env`, `fallback_to_default_webhook`).
- Produces:
  - `slack.send(markdown: str, subject: str, webhook_env: str | None = None) -> str` (new optional arg; existing 2-arg callers unchanged).
  - `notify.fmt_alert(res: Result) -> str`, `notify.fmt_remind(res: Result, since: datetime, now: datetime) -> str`, `notify.fmt_resolved(key: str, since: datetime, now: datetime) -> str`.
  - `notify.post(text: str, subject: str, cfg: dict, dry_run: bool = False) -> str` — returns `"dry-run"`, `"skipped (no alerts webhook)"`, or `slack.send`'s status string (`"sent"`, `"skipped (...)"`, `"error: ..."`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_notify.py
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.dispatch import slack
from community.health import notify
from community.health.model import CRIT, Result

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CFG = {"slack_webhook_env": "SLACK_ALERTS_WEBHOOK_URL", "fallback_to_default_webhook": False}


def _settings(mode="prod"):
    return SimpleNamespace(mode=mode, registry={"delivery": {}})


class FormatTests(unittest.TestCase):
    def test_alert_has_tag_key_detail_and_hint(self):
        text = notify.fmt_alert(Result("disk", CRIT, "93% used", "free space on the VM"))
        self.assertTrue(text.startswith("[CRITICAL] disk: 93% used"))
        self.assertIn("What to check: free space on the VM", text)

    def test_alert_without_hint_is_one_line(self):
        self.assertNotIn("\n", notify.fmt_alert(Result("disk", CRIT, "93% used")))

    def test_messages_are_emoji_free_ascii(self):
        for text in (notify.fmt_alert(Result("a", CRIT, "d", "h")),
                     notify.fmt_remind(Result("a", CRIT, "d"), NOW - timedelta(hours=7), NOW),
                     notify.fmt_resolved("a", NOW - timedelta(minutes=45), NOW)):
            self.assertTrue(all(ord(c) < 128 for c in text), text)

    def test_remind_says_still_failing_with_duration(self):
        text = notify.fmt_remind(Result("a", CRIT, "d"), NOW - timedelta(hours=7), NOW)
        self.assertIn("still failing", text)
        self.assertIn("7 h", text)

    def test_resolved_reports_how_long(self):
        self.assertEqual(notify.fmt_resolved("a", NOW - timedelta(minutes=45), NOW),
                         "[RESOLVED] a (was critical for 45 min)")


class PostTests(unittest.TestCase):
    def test_alerts_webhook_is_used_when_configured(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}), \
             patch("community.health.notify.slack.send", return_value="sent") as send:
            self.assertEqual(notify.post("t", "s", CFG), "sent")
        send.assert_called_once_with("t", "s", webhook_env="SLACK_ALERTS_WEBHOOK_URL")

    def test_no_alerts_webhook_and_no_fallback_skips_without_touching_slack(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch("community.health.notify.slack.send") as send:
            self.assertEqual(notify.post("t", "s", CFG), "skipped (no alerts webhook)")
        send.assert_not_called()

    def test_fallback_uses_the_default_webhook_only_when_enabled(self):
        cfg = {**CFG, "fallback_to_default_webhook": True}
        with patch.dict(os.environ, {}, clear=True), \
             patch("community.health.notify.slack.send", return_value="sent") as send:
            notify.post("t", "s", cfg)
        send.assert_called_once_with("t", "s")

    def test_dry_run_never_sends(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}), \
             patch("community.health.notify.slack.send") as send:
            self.assertEqual(notify.post("t", "s", CFG, dry_run=True), "dry-run")
        send.assert_not_called()


class SlackSendWebhookTests(unittest.TestCase):
    def _send(self, env, **kw):
        with patch.dict(os.environ, env, clear=True), \
             patch("community.config.settings.settings", _settings()), \
             patch.object(slack, "settings", _settings()), \
             patch.object(slack.httpx, "post") as post:
            result = slack.send("hello", "Subject", **kw)
        return result, post

    def test_default_webhook_behaviour_is_unchanged(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default"})
        self.assertEqual(result, "sent")
        self.assertEqual(post.call_args.args[0], "https://hooks.test/default")

    def test_override_env_selects_the_alternate_webhook(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default",
                                   "SLACK_ALERTS_WEBHOOK_URL": "https://hooks.test/alerts"},
                                  webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertEqual(result, "sent")
        self.assertEqual(post.call_args.args[0], "https://hooks.test/alerts")

    def test_override_env_that_is_unset_skips_and_never_falls_back(self):
        result, post = self._send({"SLACK_WEBHOOK_URL": "https://hooks.test/default"},
                                  webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertEqual(result, "skipped (no creds)")
        post.assert_not_called()

    def test_local_mode_still_never_posts(self):
        with patch.dict(os.environ, {"SLACK_ALERTS_WEBHOOK_URL": "https://x"}, clear=True), \
             patch("community.config.settings.settings", _settings("local")), \
             patch.object(slack.httpx, "post") as post:
            result = slack.send("hello", "S", webhook_env="SLACK_ALERTS_WEBHOOK_URL")
        self.assertIn("skipped (local mode", result)
        post.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_notify.py -v`
Expected: FAIL (`cannot import name 'notify'`).

- [ ] **Step 3: Write the implementation**

Edit `community/dispatch/slack.py` — change the `send` signature, docstring and URL selection (existing lines 50-56):

```python
def send(markdown: str, subject: str, webhook_env: str | None = None) -> str:
    """Returns 'sent' | 'skipped (no creds)' | 'skipped (local mode)' | 'error: …'.

    webhook_env: name of an env var holding an alternate incoming-webhook URL
    (health alerts use their own channel). Unset/None = the delivery webhook.
    An alternate that is not set skips — it never falls back to the default."""
    from community.config.settings import settings
    if settings.mode != "prod":  # dump-restored laptops must never message the team
        return "skipped (local mode — archive only)"
    url = (os.getenv(webhook_env) or None) if webhook_env else _webhook()
    if not url:
        return "skipped (no creds)"
```

(The rest of the function — the `try:` block that converts, chunks and posts — is unchanged.)

Create `community/health/notify.py`:

```python
# community/health/notify.py
"""Alert text and delivery. Plain ASCII, emoji-free (locked decision).

Delivery goes through dispatch/slack.send (prod-only gate lives there) to the
dedicated alerts webhook. The default delivery webhook carries SSO access
approvals, so there is no fallback to it unless `fallback_to_default_webhook`.
"""
from __future__ import annotations

import os
from datetime import datetime

from community.dispatch import slack
from community.health.model import Result


def _dur(hours: float) -> str:
    if hours < 1:
        return f"{max(round(hours * 60), 1)} min"  # round: 40 min is 39.999... after float division
    if hours < 48:
        return f"{hours:.0f} h"
    return f"{hours / 24:.0f} d"


def fmt_alert(res: Result) -> str:
    text = f"[CRITICAL] {res.key}: {res.detail}"
    return text + (f"\n    What to check: {res.hint}" if res.hint else "")


def fmt_remind(res: Result, since: datetime, now: datetime) -> str:
    hours = (now - since).total_seconds() / 3600
    return f"[CRITICAL, still failing] {res.key}: {res.detail} (for {_dur(hours)})"


def fmt_resolved(key: str, since: datetime, now: datetime) -> str:
    hours = (now - since).total_seconds() / 3600
    return f"[RESOLVED] {key} (was critical for {_dur(hours)})"


def post(text: str, subject: str, cfg: dict, dry_run: bool = False) -> str:
    if dry_run:
        return "dry-run"
    env = cfg["slack_webhook_env"]
    if os.getenv(env):
        return slack.send(text, subject, webhook_env=env)
    if cfg["fallback_to_default_webhook"]:
        return slack.send(text, subject)
    return "skipped (no alerts webhook)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_notify.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Confirm existing Slack callers still work**

Run: `"$CM_PYTHON" -m pytest -q`
Expected: the whole suite passes (the only `slack.send` callers pass two positional arguments, so they are unaffected).

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add community/dispatch/slack.py community/health/notify.py tests/test_health_notify.py
git commit -m "Health: alerts notifier + optional webhook override on slack.send" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Resource collectors, samples and evaluators

**Files:**
- Create: `community/health/resources.py`
- Test: `tests/test_health_resources.py`

**Interfaces:**
- Consumes: `model.*`, config `cfg["resources"]`, table `resource_samples`.
- Produces (in `community.health.resources`):
  - `OUT_DIR` (`Path`, `<repo>/out`, i.e. `/app/out` in the container — a bind mount of the host's `./out`).
  - `parse_meminfo(text) -> dict[str, float]` (`mem_available_pct`, `swap_used_pct` when present), `parse_proc_start_epoch(stat_line, btime, hz) -> float | None`.
  - `collect_host(out_dir: Path = OUT_DIR, proc: str = "/proc") -> dict[str, float]` — keys `disk_used_pct, disk_free_gb, mem_available_pct, swap_used_pct, load_per_core, api_start_epoch, cron_log_mb, backup_age_h`; every metric that cannot be read (Windows, no `/proc`) is simply absent.
  - `collect_db() -> dict[str, float]` — `db_size_gb`, `pg_start_epoch`.
  - `record_samples(metrics: dict[str, float]) -> None`, `collect_and_record() -> dict[str, float]`, `history(metric: str, hours: float) -> list[tuple[datetime, float]]`, `top_tables(limit: int = 5) -> list[tuple[str, int]]`.
  - `eta_days(points: list[tuple[datetime, float]], min_span_h: float = 24, min_points: int = 12) -> float | None`.
  - Evaluators returning `Result`: `eval_disk(r, used_pct, free_hist)`, `eval_memory(r, values)`, `eval_load(r, values)`, `eval_swap(r, value)`, `eval_cron_log(r, mb)`, `eval_restarts(name, hist, now, r)`, `eval_backup(age_h, r)`; and `check_resources(cfg, now) -> list[Result]` with keys `disk, memory, load, swap, cron_log, restart:api, restart:postgres, backup`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_resources.py
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from community.health import resources
from community.health.model import CRIT, OK, WARN

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
R = {
    "disk_warn_pct": 80, "disk_crit_pct": 90, "disk_eta_warn_days": 21, "disk_eta_crit_days": 7,
    "mem_warn_pct": 20, "mem_crit_pct": 10, "mem_crit_samples": 3,
    "load_warn_per_core": 2.0, "swap_warn_pct": 50, "cron_log_warn_mb": 500,
    "backup_crit_hours": 30, "restart_crit_count": 2,
}


def free_series(start_gb, drop_per_day, days=3, step_h=1):
    n = int(days * 24 / step_h) + 1
    t0 = NOW - timedelta(days=days)
    return [(t0 + timedelta(hours=i * step_h), start_gb - drop_per_day * i * step_h / 24)
            for i in range(n)]


class ParseTests(unittest.TestCase):
    def test_meminfo_percentages(self):
        text = ("MemTotal:       16000000 kB\nMemFree:         1000 kB\n"
                "MemAvailable:    4000000 kB\nSwapTotal:       2000000 kB\n"
                "SwapFree:        1500000 kB\n")
        out = resources.parse_meminfo(text)
        self.assertAlmostEqual(out["mem_available_pct"], 25.0)
        self.assertAlmostEqual(out["swap_used_pct"], 25.0)

    def test_meminfo_without_swap_omits_the_swap_metric(self):
        out = resources.parse_meminfo("MemTotal: 100 kB\nMemAvailable: 50 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n")
        self.assertNotIn("swap_used_pct", out)

    def test_process_start_epoch_from_proc_stat(self):
        line = "1 (cm run) S 0 1 1 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 5000 12345 678"
        self.assertEqual(resources.parse_proc_start_epoch(line, 1_700_000_000.0, 100),
                         1_700_000_050.0)

    def test_process_name_with_parentheses_does_not_break_parsing(self):
        line = "1 (a) b) S 0 1 1 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 1 0 5000 12345 678"
        self.assertEqual(resources.parse_proc_start_epoch(line, 0.0, 100), 50.0)

    def test_garbage_returns_none(self):
        self.assertIsNone(resources.parse_proc_start_epoch("nonsense", 0.0, 100))


class CollectHostTests(unittest.TestCase):
    def test_reads_proc_files_and_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            proc, out = base / "proc", base / "out"
            (proc / "1").mkdir(parents=True)
            out.mkdir()
            (proc / "meminfo").write_text("MemTotal: 1000 kB\nMemAvailable: 250 kB\n")
            (proc / "loadavg").write_text("0.50 0.40 0.30 1/200 999\n")
            (proc / "stat").write_text("cpu 1 2 3\nbtime 1700000000\n")
            (proc / "1" / "stat").write_text("1 (cm) S 0 1 1 0 -1 0 0 0 0 0 0 0 0 0 20 0 1 0 5000 0 0")
            (out / "cron.log").write_bytes(b"x" * 2_000_000)
            (out / ".backup_ok").write_text("")
            m = resources.collect_host(out_dir=out, proc=str(proc))
        self.assertAlmostEqual(m["mem_available_pct"], 25.0)
        self.assertAlmostEqual(m["load_per_core"], 0.5 / (os.cpu_count() or 1))
        self.assertAlmostEqual(m["cron_log_mb"], 2.0)
        self.assertLess(m["backup_age_h"], 0.1)
        if hasattr(os, "sysconf"):
            self.assertIn("api_start_epoch", m)
        if hasattr(os, "statvfs"):
            self.assertIn("disk_used_pct", m)

    def test_missing_proc_and_files_are_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = resources.collect_host(out_dir=pathlib.Path(tmp) / "nope",
                                       proc=str(pathlib.Path(tmp) / "noproc"))
        self.assertNotIn("mem_available_pct", m)
        self.assertNotIn("cron_log_mb", m)
        self.assertNotIn("backup_age_h", m)


class EtaTests(unittest.TestCase):
    def test_linear_fill_rate_gives_days_left(self):
        self.assertAlmostEqual(resources.eta_days(free_series(100, 20)), 2.0, places=1)

    def test_flat_or_growing_free_space_has_no_eta(self):
        self.assertIsNone(resources.eta_days(free_series(100, 0)))
        self.assertIsNone(resources.eta_days(free_series(100, -5)))

    def test_not_enough_history_has_no_eta(self):
        self.assertIsNone(resources.eta_days(free_series(100, 20, days=0.5)))
        self.assertIsNone(resources.eta_days(free_series(100, 20)[:5]))


class EvaluatorTests(unittest.TestCase):
    def test_disk_levels_from_percentage(self):
        flat = free_series(100, 0)
        self.assertEqual(resources.eval_disk(R, 95, flat).level, CRIT)
        self.assertEqual(resources.eval_disk(R, 85, flat).level, WARN)
        self.assertEqual(resources.eval_disk(R, 50, flat).level, OK)

    def test_disk_levels_from_eta(self):
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 20)).level, CRIT)  # ~2 d
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 5)).level, WARN)   # ~17 d
        self.assertEqual(resources.eval_disk(R, 50, free_series(100, 2)).level, OK)     # ~47 d

    def test_memory_needs_sustained_low_samples_to_go_critical(self):
        self.assertEqual(resources.eval_memory(R, [30, 5, 5, 5]).level, CRIT)
        self.assertEqual(resources.eval_memory(R, [30, 5, 5]).level, WARN)  # only 2 low samples
        self.assertEqual(resources.eval_memory(R, [15]).level, WARN)
        self.assertEqual(resources.eval_memory(R, [50]).level, OK)

    def test_load_and_swap_and_cron_log_warn_only(self):
        self.assertEqual(resources.eval_load(R, [3, 3, 3]).level, WARN)
        self.assertEqual(resources.eval_load(R, [3, 1, 3]).level, OK)
        self.assertEqual(resources.eval_swap(R, 60).level, WARN)
        self.assertEqual(resources.eval_swap(R, 10).level, OK)
        self.assertEqual(resources.eval_cron_log(R, 600).level, WARN)
        self.assertEqual(resources.eval_cron_log(R, 10).level, OK)

    def test_single_restart_is_a_warning_two_in_an_hour_is_critical(self):
        one = [(NOW - timedelta(hours=3), 1000.0), (NOW - timedelta(hours=2), 1000.0),
               (NOW - timedelta(hours=1), 2000.0)]
        res = resources.eval_restarts("api", one, NOW, R)
        self.assertEqual((res.key, res.level), ("restart:api", WARN))
        loop = [(NOW - timedelta(minutes=50), 1.0), (NOW - timedelta(minutes=40), 100.0),
                (NOW - timedelta(minutes=30), 200.0)]
        self.assertEqual(resources.eval_restarts("api", loop, NOW, R).level, CRIT)

    def test_no_restart_and_clock_jitter_are_ok(self):
        steady = [(NOW - timedelta(hours=2), 1000.0), (NOW - timedelta(hours=1), 1002.0)]
        self.assertEqual(resources.eval_restarts("postgres", steady, NOW, R).level, OK)

    def test_backup_heartbeat(self):
        self.assertEqual(resources.eval_backup(None, R).level, WARN)  # file not created yet
        self.assertEqual(resources.eval_backup(5.0, R).level, OK)
        self.assertEqual(resources.eval_backup(31.0, R).level, CRIT)


class CheckResourcesTests(unittest.TestCase):
    def test_emits_one_result_per_metric_family(self):
        data = {
            "disk_used_pct": [(NOW, 40.0)], "disk_free_gb": free_series(100, 0),
            "mem_available_pct": [(NOW, 60.0)], "load_per_core": [(NOW, 0.2)],
            "swap_used_pct": [(NOW, 1.0)], "cron_log_mb": [(NOW, 3.0)],
            "api_start_epoch": [(NOW - timedelta(hours=2), 1.0), (NOW, 1.0)],
            "pg_start_epoch": [(NOW - timedelta(hours=2), 1.0), (NOW, 1.0)],
            "backup_age_h": [(NOW, 3.0)],
        }
        with patch.object(resources, "history", side_effect=lambda m, h: data.get(m, [])):
            results = resources.check_resources({"resources": R}, NOW)
        keys = {r.key for r in results}
        self.assertEqual(keys, {"disk", "memory", "load", "swap", "cron_log",
                                "restart:api", "restart:postgres", "backup"})
        self.assertTrue(all(r.level == OK for r in results))

    def test_no_samples_at_all_only_flags_the_missing_backup_heartbeat(self):
        with patch.object(resources, "history", return_value=[]):
            results = resources.check_resources({"resources": R}, NOW)
        self.assertEqual([(r.key, r.level) for r in results], [("backup", WARN)])


class SampleIoTests(unittest.TestCase):
    def test_record_samples_inserts_one_row_per_metric(self):
        with patch("community.store.db.executemany") as many:
            resources.record_samples({"a": 1.0, "b": 2.0})
        sql, rows = many.call_args[0]
        self.assertIn("INSERT INTO resource_samples", sql)
        self.assertEqual(sorted(rows), [("a", 1.0), ("b", 2.0)])

    def test_history_returns_ts_value_pairs(self):
        with patch("community.store.db.query", return_value=[{"ts": NOW, "value": 3.5}]):
            self.assertEqual(resources.history("disk_used_pct", 2), [(NOW, 3.5)])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_resources.py -v`
Expected: FAIL (`cannot import name 'resources'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/resources.py
"""Host + Postgres resource metrics (spec §8) — container-visible only.

Disk comes from statvfs on /app/out (a bind mount of the host's ./out, so it is
the host filesystem); memory/load from /proc (compose sets no limits, so these
are host values); restarts from the PID 1 start time (api) and
pg_postmaster_start_time() (postgres). Every collector tolerates a missing
source (Windows dev box, no /proc) by omitting that metric.
Known limit: if Docker's data root is on a different filesystem than ./out its
usage is not visible here.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from community.config.log import IST, get_logger
from community.config.settings import ROOT
from community.health.model import CRIT, OK, WARN, Result, owns

log = get_logger("health.resources")
OUT_DIR = ROOT / "out"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_meminfo(text: str) -> dict[str, float]:
    kv: dict[str, float] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            kv[name.strip()] = float(parts[0])
    out: dict[str, float] = {}
    if kv.get("MemTotal") and kv.get("MemAvailable") is not None:
        out["mem_available_pct"] = 100.0 * kv["MemAvailable"] / kv["MemTotal"]
    if kv.get("SwapTotal"):
        out["swap_used_pct"] = 100.0 * (kv["SwapTotal"] - kv.get("SwapFree", 0.0)) / kv["SwapTotal"]
    return out


def parse_proc_start_epoch(stat_line: str, btime: float, hz: int) -> float | None:
    """starttime is field 22 of /proc/<pid>/stat, in clock ticks since boot.
    The command name (field 2) may contain spaces/parens, so split after the
    LAST ')' — field 3 is then index 0, field 22 index 19."""
    try:
        rest = stat_line[stat_line.rindex(")") + 1:].split()
        return btime + float(rest[19]) / hz
    except (ValueError, IndexError):
        return None


def collect_host(out_dir: Path = OUT_DIR, proc: str = "/proc") -> dict[str, float]:
    m: dict[str, float] = {}
    try:
        st = os.statvfs(out_dir)
        used = st.f_blocks - st.f_bfree
        if used + st.f_bavail:
            m["disk_used_pct"] = 100.0 * used / (used + st.f_bavail)
        m["disk_free_gb"] = st.f_bavail * st.f_frsize / 1e9
    except (AttributeError, OSError):
        pass
    try:
        m.update(parse_meminfo(_read(f"{proc}/meminfo")))
    except (OSError, ValueError):
        pass
    try:
        load1 = float(_read(f"{proc}/loadavg").split()[0])
        m["load_per_core"] = load1 / (os.cpu_count() or 1)
    except (OSError, ValueError, IndexError):
        pass
    try:
        btime = next(float(line.split()[1]) for line in _read(f"{proc}/stat").splitlines()
                     if line.startswith("btime"))
        epoch = parse_proc_start_epoch(_read(f"{proc}/1/stat"), btime, os.sysconf("SC_CLK_TCK"))
        if epoch is not None:
            m["api_start_epoch"] = epoch
    except (OSError, StopIteration, ValueError, AttributeError):
        pass
    cron_log = Path(out_dir) / "cron.log"
    if cron_log.exists():
        m["cron_log_mb"] = cron_log.stat().st_size / 1e6
    heartbeat = Path(out_dir) / ".backup_ok"  # `touch`ed by the backup cron line
    if heartbeat.exists():
        m["backup_age_h"] = (time.time() - heartbeat.stat().st_mtime) / 3600
    return m


def collect_db() -> dict[str, float]:
    from community.store import db
    row = db.one("SELECT pg_database_size(current_database()) AS size, "
                 "extract(epoch FROM pg_postmaster_start_time()) AS started")
    return {"db_size_gb": row["size"] / 1e9, "pg_start_epoch": float(row["started"])}


def record_samples(metrics: dict[str, float]) -> None:
    from community.store import db
    db.executemany("INSERT INTO resource_samples (metric, value) VALUES (%s, %s)",
                   list(metrics.items()))


def collect_and_record() -> dict[str, float]:
    metrics = collect_host()
    try:
        metrics.update(collect_db())
    except Exception as e:  # noqa: BLE001 — host metrics are still worth recording
        log.warning("db resource metrics unavailable (%s)", e)
    record_samples(metrics)
    return metrics


def history(metric: str, hours: float) -> list[tuple[datetime, float]]:
    from community.store import db
    rows = db.query(
        "SELECT ts, value FROM resource_samples WHERE metric = %s "
        "AND ts > now() - (%s * interval '1 hour') ORDER BY ts", (metric, hours))
    return [(r["ts"], r["value"]) for r in rows]


def top_tables(limit: int = 5) -> list[tuple[str, int]]:
    from community.store import db
    rows = db.query(
        "SELECT c.relname AS name, pg_total_relation_size(c.oid) AS size "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY size DESC LIMIT %s", (limit,))
    return [(r["name"], int(r["size"])) for r in rows]


def eta_days(points: list[tuple[datetime, float]], min_span_h: float = 24,
             min_points: int = 12) -> float | None:
    """Days until free space (GB) reaches zero at the least-squares fill rate."""
    if len(points) < min_points:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [v for _, v in points]
    if xs[-1] < min_span_h / 24:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den  # GB per day
    return ys[-1] / -slope if slope < 0 else None


def eval_disk(r: dict, used_pct: float, free_hist: list[tuple[datetime, float]]) -> Result:
    eta = eta_days(free_hist)
    eta_txt = f", full in about {eta:.0f} days at the current rate" if eta is not None else ""
    detail = f"{used_pct:.0f}% used{eta_txt}"
    hint = "free space on the VM (docker images/logs, out/cron.log, old backups)"
    if used_pct >= r["disk_crit_pct"] or (eta is not None and eta < r["disk_eta_crit_days"]):
        return Result("disk", CRIT, detail, hint)
    if used_pct >= r["disk_warn_pct"] or (eta is not None and eta < r["disk_eta_warn_days"]):
        return Result("disk", WARN, detail, hint)
    return Result("disk", OK, detail)


def eval_memory(r: dict, values: list[float]) -> Result:
    latest = values[-1]
    n = r["mem_crit_samples"]
    if len(values) >= n and all(v < r["mem_crit_pct"] for v in values[-n:]):
        return Result("memory", CRIT, f"{latest:.0f}% memory available for {n}+ samples in a row",
                      "check docker stats; a heavy job may be starving the box")
    if latest < r["mem_warn_pct"]:
        return Result("memory", WARN, f"{latest:.0f}% memory available")
    return Result("memory", OK, f"{latest:.0f}% memory available")


def eval_load(r: dict, values: list[float]) -> Result:
    if len(values) >= 3 and all(v > r["load_warn_per_core"] for v in values[-3:]):
        return Result("load", WARN, f"load {values[-1]:.1f} per core for 3+ samples")
    return Result("load", OK, f"load {values[-1]:.1f} per core")


def eval_swap(r: dict, pct: float) -> Result:
    level = WARN if pct > r["swap_warn_pct"] else OK
    return Result("swap", level, f"{pct:.0f}% of swap in use")


def eval_cron_log(r: dict, mb: float) -> Result:
    level = WARN if mb > r["cron_log_warn_mb"] else OK
    return Result("cron_log", level, f"out/cron.log is {mb:.0f} MB",
                  "trim or rotate out/cron.log by hand" if level == WARN else "")


def eval_restarts(name: str, hist: list[tuple[datetime, float]], now: datetime, r: dict) -> Result:
    key = f"restart:{name}"
    events = [t for (t, v), (_, pv) in zip(hist[1:], hist[:-1])
              if abs(v - pv) > 5 and now - t <= timedelta(hours=24)]
    recent = [t for t in events if now - t <= timedelta(hours=1)]
    if len(recent) >= r["restart_crit_count"]:
        return Result(key, CRIT, f"{name} restarted {len(recent)} times in the last hour",
                      f"docker compose logs {'api' if name == 'api' else 'postgres'} --tail 100")
    if events:
        when = events[-1].astimezone(IST).strftime("%d %b %H:%M")
        return Result(key, WARN, f"{name} restarted at {when} IST")
    return Result(key, OK, f"no {name} restart in the last 24h")


def eval_backup(age_h: float | None, r: dict) -> Result:
    if age_h is None:
        return Result("backup", WARN, "no backup heartbeat file found (out/.backup_ok)",
                      "append '&& touch out/.backup_ok' to the backup cron line")
    if age_h > r["backup_crit_hours"]:
        return Result("backup", CRIT, f"last good backup was {age_h:.0f} h ago",
                      "run deploy/backup.sh by hand and check out/cron.log for the failure")
    return Result("backup", OK, f"last good backup {age_h:.0f} h ago")


@owns("disk", "memory", "load", "swap", "cron_log", "restart:", "backup")
def check_resources(cfg: dict, now: datetime) -> list[Result]:
    r = cfg["resources"]
    results: list[Result] = []
    used = history("disk_used_pct", 2)
    if used:
        results.append(eval_disk(r, used[-1][1], history("disk_free_gb", 24 * 7)))
    mem = history("mem_available_pct", 2)
    if mem:
        results.append(eval_memory(r, [v for _, v in mem]))
    load = history("load_per_core", 2)
    if load:
        results.append(eval_load(r, [v for _, v in load]))
    swap = history("swap_used_pct", 2)
    if swap:
        results.append(eval_swap(r, swap[-1][1]))
    cron = history("cron_log_mb", 2)
    if cron:
        results.append(eval_cron_log(r, cron[-1][1]))
    for name, metric in (("api", "api_start_epoch"), ("postgres", "pg_start_epoch")):
        hist = history(metric, 26)
        if hist:
            results.append(eval_restarts(name, hist, now, r))
    backup = history("backup_age_h", 2)
    results.append(eval_backup(backup[-1][1] if backup else None, r))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_resources.py -v`
Expected: PASS (21 tests). (`test_reads_proc_files_and_out_dir` skips the Linux-only assertions on Windows.)

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/resources.py tests/test_health_resources.py
git commit -m "Health: host/DB resource collectors, samples and evaluators" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 9: Job checks (overdue, slow, failed, stage-failing, heartbeat)

**Files:**
- Create: `community/health/checks_jobs.py`
- Test: `tests/test_health_checks_jobs.py`

**Interfaces:**
- Consumes: `ledger.recent_runs(hours)` rows (`job,status,started_at,finished_at,failed_stages,error`), `schedule.trailing_missed`, `schedule.Run`, `state.get_epoch(now, create)`, `state.Row`, config keys `jobs`, `lock_exempt_minutes`, `job_failing_runs`, `stage_failing_runs`; `cfg["_prev"]: dict[str, state.Row]` and `cfg["_dry_run"]: bool` (both injected by the engine; default empty / False).
- Produces (all `(cfg: dict, now: datetime) -> list[Result]`):
  - `check_jobs` — owns `job_overdue:`, `job_slow:`, `job_failed:`, `stage_failing:`; emits one `job_overdue:<job>`, `job_slow:<job>`, `job_failed:<job>` per configured job, plus `stage_failing:<stage>` (critical) for each stage that failed in each of the last `stage_failing_runs` finished `run-local` runs.
  - `check_recent_stage_failures` — owns `stage_recent:`; warnings only (digest).
  - `check_watchdog_heartbeat` — owns `watchdog_heartbeat`; warning if the watchdog never ran or last ran over 2 h ago.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_checks_jobs.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_jobs, config
from community.health.model import CRIT, OK, WARN
from community.health.state import Row


def ist(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)  # 2026-10-05 is a Monday


def row(job, status, start, finish=None, failed=(), error=None):
    return {"job": job, "status": status, "started_at": start, "finished_at": finish,
            "failed_stages": list(failed), "error": error}


def local(hour, status="ok", failed=()):
    return row("run-local", status, ist(5, hour), ist(5, hour, 8), failed)


def run_check(rows, now, epoch=ist(5, 0), cfg=None):
    cfg = cfg or {**config.load({}), "_prev": {}}
    with patch.object(checks_jobs.ledger, "recent_runs", return_value=rows), \
         patch.object(checks_jobs.state, "get_epoch", return_value=epoch):
        results = checks_jobs.check_jobs(cfg, now)
    return {r.key: r for r in results}


class OverdueTests(unittest.TestCase):
    def test_first_run_after_deploy_with_an_empty_ledger_raises_nothing(self):
        now = ist(5, 10, 30)
        res = run_check([], now, epoch=now)  # epoch == now: monitoring just began
        self.assertTrue(all(r.level == OK for r in res.values()), res)

    def test_three_missed_hourly_runs_is_critical(self):
        res = run_check([local(7), local(8)], ist(5, 11, 30))
        self.assertEqual(res["job_overdue:run-local"].level, CRIT)
        self.assertIn("3 scheduled run(s)", res["job_overdue:run-local"].detail)

    def test_one_missed_hourly_run_is_only_a_warning(self):
        res = run_check([local(7), local(8), local(9)], ist(5, 10, 30))
        self.assertEqual(res["job_overdue:run-local"].level, WARN)

    def test_healthy_hourly_runs_are_ok(self):
        res = run_check([local(h) for h in (7, 8, 9, 10, 11)], ist(5, 12, 10))
        self.assertEqual(res["job_overdue:run-local"].level, OK)

    def test_morning_build_that_never_started_is_critical(self):
        res = run_check([], ist(5, 7, 0))
        self.assertEqual(res["job_overdue:morning-build"].level, CRIT)


class SlowAndFailedTests(unittest.TestCase):
    def test_morning_build_still_running_after_90_minutes_is_critical(self):
        rows = [row("morning-build", "running", ist(5, 6))]
        self.assertEqual(run_check(rows, ist(5, 8, 0))["job_slow:morning-build"].level, CRIT)
        self.assertEqual(run_check(rows, ist(5, 7, 0))["job_slow:morning-build"].level, OK)

    def test_two_crashed_runs_in_a_row_is_critical(self):
        rows = [local(8, "failed"), local(9, "failed")]
        rows[0]["error"] = rows[1]["error"] = "RuntimeError: boom"
        res = run_check(rows, ist(5, 9, 30))
        self.assertEqual(res["job_failed:run-local"].level, CRIT)
        self.assertIn("RuntimeError: boom", res["job_failed:run-local"].detail)

    def test_one_crash_between_successes_is_ok(self):
        rows = [local(8, "ok"), local(9, "failed")]
        self.assertEqual(run_check(rows, ist(5, 9, 30))["job_failed:run-local"].level, OK)


class StageFailingTests(unittest.TestCase):
    def test_stage_failing_in_each_of_the_last_three_runs_is_critical(self):
        rows = [local(8, "degraded", ["enrich"]),
                local(9, "degraded", ["enrich", "scrape"]),
                local(10, "degraded", ["enrich"])]
        res = run_check(rows, ist(5, 10, 30))
        self.assertEqual(res["stage_failing:enrich"].level, CRIT)
        self.assertNotIn("stage_failing:scrape", res)

    def test_a_clean_run_in_the_window_clears_it(self):
        rows = [local(8, "degraded", ["enrich"]), local(9, "ok"), local(10, "degraded", ["enrich"])]
        self.assertNotIn("stage_failing:enrich", run_check(rows, ist(5, 10, 30)))

    def test_fewer_than_three_runs_reports_nothing(self):
        rows = [local(9, "degraded", ["enrich"]), local(10, "degraded", ["enrich"])]
        self.assertNotIn("stage_failing:enrich", run_check(rows, ist(5, 10, 30)))


class DigestOnlyChecksTests(unittest.TestCase):
    def test_recent_stage_failures_are_warnings_with_counts(self):
        rows = [local(8, "degraded", ["enrich"]), local(9, "degraded", ["enrich"])]
        with patch.object(checks_jobs.ledger, "recent_runs", return_value=rows):
            results = checks_jobs.check_recent_stage_failures({}, ist(5, 10))
        self.assertEqual([(r.key, r.level) for r in results], [("stage_recent:enrich", WARN)])
        self.assertIn("2 failure(s)", results[0].detail)

    def test_heartbeat_missing_stale_and_fresh(self):
        now = ist(5, 12)
        missing = checks_jobs.check_watchdog_heartbeat({"_prev": {}}, now)[0]
        stale = checks_jobs.check_watchdog_heartbeat(
            {"_prev": {"watchdog_heartbeat": Row("watchdog_heartbeat", "ok", "", now, now - timedelta(hours=3))}}, now)[0]
        fresh = checks_jobs.check_watchdog_heartbeat(
            {"_prev": {"watchdog_heartbeat": Row("watchdog_heartbeat", "ok", "", now, now - timedelta(minutes=10))}}, now)[0]
        self.assertEqual((missing.level, stale.level, fresh.level), (WARN, WARN, OK))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_jobs.py -v`
Expected: FAIL (`cannot import name 'checks_jobs'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/checks_jobs.py
"""Job-level checks from the job_runs ledger (spec §6).

Critical (watchdog): a scheduled run never started (job_overdue), a run is
still going past its limit (job_slow — this is how "morning build not
finished by 07:30" is enforced), a job crashed twice in a row (job_failed), or
the same stage failed in each of the last N run-local runs (stage_failing).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from community.config.log import IST
from community.health import ledger, schedule, state
from community.health.model import CRIT, OK, WARN, Result, owns

_FINISHED = ("ok", "degraded", "failed")


def _ist(ts: datetime) -> str:
    return ts.astimezone(IST).strftime("%d %b %H:%M")


def _overdue(job: str, jcfg: dict, runs: list, now: datetime, epoch: datetime, cfg: dict) -> Result:
    key = f"job_overdue:{job}"
    missed = schedule.trailing_missed(job, jcfg, runs, now, epoch=epoch,
                                      exempt_min=cfg["lock_exempt_minutes"])
    if not missed:
        return Result(key, OK, "on schedule")
    level = CRIT if len(missed) >= jcfg["crit_after_missed"] else WARN
    return Result(key, level,
                  f"{len(missed)} scheduled run(s) did not start, since {_ist(missed[0])} IST",
                  "check crontab -l, docker compose ps and out/cron.log; a stuck run can also hold the lock")


def _slow(job: str, jcfg: dict, rows: list[dict], now: datetime) -> Result:
    key = f"job_slow:{job}"
    limit = jcfg["max_run_min"]
    over = [r for r in rows if r["job"] == job and r["status"] == "running"
            and now - r["started_at"] > timedelta(minutes=limit)]
    if not over:
        return Result(key, OK, "no overlong run")
    mins = int((now - over[0]["started_at"]).total_seconds() / 60)
    return Result(key, CRIT,
                  f"started {_ist(over[0]['started_at'])} IST and still running after {mins} min (limit {limit})",
                  "the run may be hung and holding the pipeline lock: docker compose exec api ps aux")


def _failed(job: str, rows: list[dict], n: int) -> Result:
    key = f"job_failed:{job}"
    last = [r for r in rows if r["job"] == job and r["status"] in _FINISHED][-n:]
    if len(last) >= n and all(r["status"] == "failed" for r in last):
        return Result(key, CRIT, f"the last {n} runs crashed: {(last[-1].get('error') or '')[:120]}",
                      "see out/cron.log for the traceback")
    return Result(key, OK, "recent runs did not crash")


def _stage_failing(rows: list[dict], n: int) -> list[Result]:
    last = [r for r in rows if r["job"] == "run-local" and r["status"] in _FINISHED][-n:]
    if len(last) < n:
        return []
    common = set.intersection(*(set(r["failed_stages"] or []) for r in last))
    return [Result(f"stage_failing:{stage}", CRIT,
                   f"stage {stage} failed in each of the last {n} runs",
                   "see out/cron.log for the stage traceback")
            for stage in sorted(common)]


@owns("job_overdue:", "job_slow:", "job_failed:", "stage_failing:")
def check_jobs(cfg: dict, now: datetime) -> list[Result]:
    epoch = state.get_epoch(now, create=not cfg.get("_dry_run"))
    rows = ledger.recent_runs(48)
    runs = [schedule.Run(r["job"], r["status"], r["started_at"], r["finished_at"]) for r in rows]
    results: list[Result] = []
    for job, jcfg in cfg["jobs"].items():
        results.append(_overdue(job, jcfg, runs, now, epoch, cfg))
        results.append(_slow(job, jcfg, rows, now))
        results.append(_failed(job, rows, cfg["job_failing_runs"]))
    results.extend(_stage_failing(rows, cfg["stage_failing_runs"]))
    return results


@owns("stage_recent:")
def check_recent_stage_failures(cfg: dict, now: datetime) -> list[Result]:
    seen: dict[str, list[datetime]] = {}
    for r in ledger.recent_runs(24):
        for stage in r["failed_stages"] or []:
            seen.setdefault(stage, []).append(r["started_at"])
    return [Result(f"stage_recent:{stage}", WARN,
                   f"{len(times)} failure(s) in the last 24h, last at {_ist(max(times))} IST")
            for stage, times in sorted(seen.items())]


@owns("watchdog_heartbeat")
def check_watchdog_heartbeat(cfg: dict, now: datetime) -> list[Result]:
    row = cfg.get("_prev", {}).get("watchdog_heartbeat")
    if row is None or row.last_seen is None:
        return [Result("watchdog_heartbeat", WARN, "the watchdog has never run",
                       "install the */20 cron line for ./cm watchdog")]
    age_h = (now - row.last_seen).total_seconds() / 3600
    if age_h > 2:
        return [Result("watchdog_heartbeat", WARN, f"the watchdog last ran {age_h:.0f} h ago",
                       "check crontab -l and out/cron.log")]
    return [Result("watchdog_heartbeat", OK, "watchdog is running")]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_jobs.py -v`
Expected: PASS (13 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/checks_jobs.py tests/test_health_checks_jobs.py
git commit -m "Health: job overdue/slow/failed/stage-failing checks" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Data checks (partitions, freshness, enrichment backlog, sources)

**Files:**
- Create: `community/health/checks_data.py`
- Test: `tests/test_health_checks_data.py`

**Interfaces:**
- Consumes: `community.store.db` (`query`, `one`), `community.config.settings.settings.registry["sources"]`, config keys `partitions`, `sources`, `freshness`, `enrichment_backlog_warn`, `muted`.
- Produces (each `(cfg, now) -> list[Result]`):
  - `check_partitions` — owns `partitions:`; one result per table in `cfg["partitions"]["tables"]`; crit if the last partition's upper bound is under `crit_days` away, warn under `warn_days`.
  - `check_freshness` — owns `freshness:`; keys `freshness:topics`, `freshness:daily_roundup`, `freshness:weekly_roundup` (each only after its IST time), and always `freshness:enrich_backlog`. Warnings only.
  - `check_sources` — owns `source:`, `source_items:`; one `source:<name>` per enabled, un-muted source with a `pipeline_state` row or not; `source_items:<name>` for `volume_sources`. Warnings only. A source with no `pipeline_state` row never crashes the check.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_checks_data.py
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_data, config
from community.health.model import CRIT, OK, WARN

CFG = {**config.load({}), "_prev": {}}
UTC = timezone.utc


def by_key(results):
    return {r.key: r for r in results}


class PartitionTests(unittest.TestCase):
    def rows(self, upper):
        return [{"parent": t, "upper_bound": upper} for t in CFG["partitions"]["tables"]]

    def run_check(self, upper, now):
        with patch.object(checks_data.db, "query", return_value=self.rows(upper)):
            return by_key(checks_data.check_partitions(CFG, now))

    def test_prod_today_is_a_warning_with_days_left(self):
        res = self.run_check(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC))
        self.assertEqual(res["partitions:social_items"].level, WARN)
        self.assertIn("27 days", res["partitions:social_items"].detail)

    def test_ten_days_before_the_cliff_is_critical(self):
        res = self.run_check(datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 10, 25, tzinfo=UTC))
        self.assertEqual(res["partitions:item_enrichment"].level, CRIT)

    def test_plenty_of_future_partitions_is_ok(self):
        res = self.run_check(datetime(2027, 11, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC))
        self.assertTrue(all(r.level == OK for r in res.values()))

    def test_a_table_with_no_partitions_is_flagged_not_crashed(self):
        with patch.object(checks_data.db, "query", return_value=[]):
            res = by_key(checks_data.check_partitions(CFG, datetime(2026, 10, 5, tzinfo=UTC)))
        self.assertEqual(res["partitions:social_items"].level, WARN)


class FreshnessTests(unittest.TestCase):
    def run_check(self, now, topics=1, daily=True, weekly=True, backlog=0):
        def fake_one(sql, params=None):
            if "topic_daily" in sql:
                return {"n": topics}
            if "roundups" in sql:
                has = daily if "'daily'" in sql else weekly
                return {"x": 1} if has else None
            return {"n": backlog}
        with patch.object(checks_data.db, "one", side_effect=fake_one):
            return by_key(checks_data.check_freshness(CFG, now))

    def test_before_the_expected_times_only_the_backlog_is_checked(self):
        res = self.run_check(datetime(2026, 10, 5, 6, 0, tzinfo=IST))
        self.assertEqual(set(res), {"freshness:enrich_backlog"})

    def test_missing_topics_and_roundup_after_their_deadlines_warn(self):
        res = self.run_check(datetime(2026, 10, 5, 9, 0, tzinfo=IST), topics=0, daily=False)
        self.assertEqual(res["freshness:topics"].level, WARN)
        self.assertEqual(res["freshness:daily_roundup"].level, WARN)

    def test_weekly_roundup_is_only_expected_on_saturday_after_11(self):
        sat = self.run_check(datetime(2026, 10, 10, 11, 30, tzinfo=IST), weekly=False)
        self.assertEqual(sat["freshness:weekly_roundup"].level, WARN)
        mon = self.run_check(datetime(2026, 10, 5, 11, 30, tzinfo=IST), weekly=False)
        self.assertNotIn("freshness:weekly_roundup", mon)

    def test_enrichment_backlog_threshold(self):
        now = datetime(2026, 10, 5, 6, 0, tzinfo=IST)
        self.assertEqual(self.run_check(now, backlog=500)["freshness:enrich_backlog"].level, WARN)
        self.assertEqual(self.run_check(now, backlog=50)["freshness:enrich_backlog"].level, OK)


class SourceTests(unittest.TestCase):
    NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    REGISTRY = {"sources": {"twitter": {"enabled": True}, "reddit": {"enabled": True},
                            "youtube": {"enabled": True}, "github": {"enabled": False},
                            "app_reviews": {"enabled": True}}}

    def run_check(self, state_rows, newest_rows):
        def fake_query(sql, params=None):
            return state_rows if "pipeline_state" in sql else newest_rows
        with patch.object(checks_data, "settings", SimpleNamespace(registry=self.REGISTRY)), \
             patch.object(checks_data.db, "query", side_effect=fake_query):
            return by_key(checks_data.check_sources(CFG, self.NOW))

    def st(self, source, ok_h_ago=1.0, err=None, err_h_ago=None):
        return {"source": source, "last_success_at": self.NOW - timedelta(hours=ok_h_ago),
                "last_error": err,
                "last_error_at": None if err_h_ago is None else self.NOW - timedelta(hours=err_h_ago)}

    def test_healthy_sources_are_ok(self):
        res = self.run_check([self.st("twitter"), self.st("youtube", 5), self.st("app_review", 5)],
                             [{"source": "twitter", "newest": self.NOW - timedelta(hours=1)}])
        self.assertEqual(res["source:twitter"].level, OK)
        self.assertEqual(res["source:youtube"].level, OK)
        self.assertEqual(res["source_items:twitter"].level, OK)

    def test_muted_and_disabled_sources_produce_no_results(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertNotIn("source:reddit", res)   # muted by default
        self.assertNotIn("source:github", res)   # disabled in the registry

    def test_stale_daily_collector_warns(self):
        res = self.run_check([self.st("twitter"), self.st("youtube", ok_h_ago=40)], [])
        self.assertEqual(res["source:youtube"].level, WARN)
        self.assertIn("40 h", res["source:youtube"].detail)

    def test_a_failed_latest_run_warns_with_the_error(self):
        res = self.run_check([self.st("twitter"),
                              self.st("youtube", 2, err="HTTPError: 403 quota", err_h_ago=1)], [])
        self.assertEqual(res["source:youtube"].level, WARN)
        self.assertIn("403 quota", res["source:youtube"].detail)

    def test_enabled_source_with_no_state_row_does_not_crash(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertEqual(res["source:app_reviews"].level, WARN)
        self.assertIn("not recorded", res["source:app_reviews"].detail)

    def test_volume_source_with_no_recent_items_warns(self):
        res = self.run_check([self.st("twitter")], [])
        self.assertEqual(res["source_items:twitter"].level, WARN)
        res = self.run_check([self.st("twitter")],
                             [{"source": "twitter", "newest": self.NOW - timedelta(hours=30)}])
        self.assertEqual(res["source_items:twitter"].level, WARN)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_data.py -v`
Expected: FAIL (`cannot import name 'checks_data'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/checks_data.py
"""Data-layer checks: partition cliff, freshness, enrichment backlog, collectors.

`partitions` is the first check expected to fire: the month partitions of
social_items / item_enrichment / item_embeddings were created only through
2026-10 (migrations/0001_init.sql) and no partition job exists yet, so inserts
fail once the last partition ends. Source checks use pipeline_state.last_success_at
(the collector ran) — several daily sources can legitimately add zero new
items, so the "newest item" test applies only to the configured volume sources.
"""
from __future__ import annotations

from datetime import datetime

from community.config.log import IST
from community.config.settings import settings
from community.health.model import CRIT, OK, WARN, Result, owns
from community.store import db

_PARTITION_SQL = r"""
SELECT p.relname AS parent,
       max((regexp_match(pg_get_expr(c.relpartbound, c.oid), 'TO \(''([^'']+)''\)'))[1]::timestamptz)
         AS upper_bound
FROM pg_inherits i
JOIN pg_class c ON c.oid = i.inhrelid
JOIN pg_class p ON p.oid = i.inhparent
WHERE p.relname = ANY(%s)
GROUP BY p.relname
"""

_BACKLOG_SQL = """
SELECT count(*) AS n FROM social_items s
WHERE s.ingested_at > now() - interval '7 days'
  AND s.ingested_at < now() - interval '2 hours'
  AND s.duplicate_of IS NULL
  AND NOT EXISTS (SELECT 1 FROM item_enrichment e
                  WHERE e.item_id = s.item_id AND e.ingested_at = s.ingested_at)
"""


@owns("partitions:")
def check_partitions(cfg: dict, now: datetime) -> list[Result]:
    p = cfg["partitions"]
    bounds = {r["parent"]: r["upper_bound"] for r in db.query(_PARTITION_SQL, (p["tables"],))}
    hint = ("inserts fail once the last partition ends: create the next months' partitions "
            "(backlog P1: rolling partition job)")
    results = []
    for table in p["tables"]:
        key = f"partitions:{table}"
        upper = bounds.get(table)
        if upper is None:
            results.append(Result(key, WARN, "no partitions found for this table", hint))
            continue
        days = (upper - now).total_seconds() / 86400
        detail = f"partitions exist until {upper.astimezone(IST):%d %b %Y} ({days:.0f} days left)"
        if days < p["crit_days"]:
            results.append(Result(key, CRIT, detail, hint))
        elif days < p["warn_days"]:
            results.append(Result(key, WARN, detail, hint))
        else:
            results.append(Result(key, OK, detail))
    return results


@owns("freshness:")
def check_freshness(cfg: dict, now: datetime) -> list[Result]:
    f = cfg["freshness"]
    ist_now = now.astimezone(IST)
    hour = ist_now.hour + ist_now.minute / 60
    today = ist_now.date()
    results: list[Result] = []
    if hour >= f["topics_after_ist"]:
        n = db.one("SELECT count(*) AS n FROM topic_daily WHERE day = %s", (today,))["n"]
        results.append(Result("freshness:topics", OK if n else WARN,
                              f"{n} topic rows for today" if n else "no topic rollups for today yet",
                              "" if n else "the aggregate stage may be failing: see out/cron.log"))
    if hour >= f["daily_roundup_after_ist"]:
        have = db.one("SELECT 1 AS x FROM roundups WHERE period = 'daily' AND date = %s", (today,))
        results.append(Result("freshness:daily_roundup", OK if have else WARN,
                              "today's daily roundup exists" if have else "today's daily roundup is missing"))
    if ist_now.weekday() == 5 and hour >= f["weekly_roundup_after_ist"]:
        have = db.one("SELECT 1 AS x FROM roundups WHERE period = 'weekly' AND date = %s", (today,))
        results.append(Result("freshness:weekly_roundup", OK if have else WARN,
                              "this week's roundup exists" if have else "this Saturday's weekly roundup is missing"))
    backlog = db.one(_BACKLOG_SQL)["n"]
    results.append(Result("freshness:enrich_backlog",
                          WARN if backlog > cfg["enrichment_backlog_warn"] else OK,
                          f"{backlog} items waiting for enrichment (over 2 h old)"))
    return results


def _collector_result(name: str, row: dict | None, scfg: dict, now: datetime) -> Result:
    key = f"source:{name}"
    if row is None or row["last_success_at"] is None:
        return Result(key, WARN, "collector has not recorded a successful run")
    age_h = (now - row["last_success_at"]).total_seconds() / 3600
    limit = scfg["max_age_hours"].get(name, scfg["max_age_hours"]["default"])
    if age_h > limit:
        return Result(key, WARN, f"last successful run {age_h:.0f} h ago (allowed {limit} h)")
    if row["last_error"] and row["last_error_at"] and row["last_error_at"] > row["last_success_at"]:
        return Result(key, WARN, f"last run failed: {row['last_error'][:120]}")
    return Result(key, OK, f"last success {age_h:.0f} h ago")


@owns("source:", "source_items:")
def check_sources(cfg: dict, now: datetime) -> list[Result]:
    scfg = cfg["sources"]
    muted = set(cfg["muted"])
    configured = settings.registry.get("sources", {})
    rows = {r["source"]: r for r in db.query(
        "SELECT source, last_success_at, last_error, last_error_at "
        "FROM pipeline_state WHERE stage = 'ingest'")}
    results: list[Result] = []
    active: list[tuple[str, str]] = []
    for name, stored in scfg["map"].items():
        if name in muted or stored in muted:
            continue
        if not (configured.get(name) or {}).get("enabled", name in ("twitter", "reddit")):
            continue
        active.append((name, stored))
        results.append(_collector_result(name, rows.get(stored), scfg, now))
    volume = [(n, s) for n, s in active if n in scfg["volume_sources"]]
    if volume:
        newest = {r["source"]: r["newest"] for r in db.query(
            "SELECT source, max(ingested_at) AS newest FROM social_items "
            "WHERE ingested_at > now() - interval '3 days' AND source = ANY(%s) GROUP BY source",
            ([s for _, s in volume],))}
        for name, stored in volume:
            key = f"source_items:{name}"
            latest = newest.get(stored)
            if latest is None:
                results.append(Result(key, WARN, "no new items in the last 3 days"))
                continue
            age_h = (now - latest).total_seconds() / 3600
            limit = scfg["volume_max_age_hours"]
            results.append(Result(key, WARN if age_h > limit else OK,
                                  f"newest item arrived {age_h:.0f} h ago"
                                  + (f" (allowed {limit} h)" if age_h > limit else "")))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_data.py -v`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/checks_data.py tests/test_health_checks_data.py
git commit -m "Health: partition-cliff, freshness, enrichment-backlog and collector checks" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: LLM and credit checks

**Files:**
- Create: `community/health/checks_llm.py`
- Test: `tests/test_health_checks_llm.py`

**Interfaces:**
- Consumes: `community.store.db`, `settings.anthropic_api_key`, `settings.enrich_model`, config keys `credits`, `llm`; `cfg["_prev"]` (`state.Row` by key) and `cfg["_force"]` (bool; the digest sets it to skip the hourly gate).
- Produces:
  - `probe_due(cfg: dict, now: datetime, prev_level: str | None) -> bool` — true when `cfg["_force"]`, or the previous level is `crit`, or the watchdog is firing in minutes 0-19 IST (the `:00` run of the `*/20` cron).
  - `check_anthropic_key` — owns `anthropic_key`; returns `[]` when the probe is not due. Auth/credit errors are critical; network/5xx errors are only a warning.
  - `check_credits` — owns `credits:`; `credits:x` (critical when twitterapi.io returned 402 after the last success; read from `pipeline_state`, no paid call) and `credits:apify` (free `/users/me/limits`; hourly gate).
  - `check_llm_usage` — owns `llm:`; warnings only: `llm:calls`, `llm:spend`, `llm:unpriced`.
  - Module-level hooks tests patch: `_count_tokens_probe() -> None` and `_apify_usage() -> tuple[float, float] | None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_checks_llm.py
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from community.config.log import IST
from community.health import checks_llm, config
from community.health.model import CRIT, OK, WARN
from community.health.state import Row

CFG = {**config.load({}), "_prev": {}}
DUE = datetime(2026, 10, 5, 12, 5, tzinfo=IST)        # minute 5: the hourly probe slot
NOT_DUE = datetime(2026, 10, 5, 12, 40, tzinfo=IST)


class AuthenticationError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class BadRequestError(Exception):
    pass


def with_key(key="sk-test"):
    return patch.object(checks_llm, "settings", SimpleNamespace(anthropic_api_key=key, enrich_model="m"))


def crit_row(key):
    return Row(key, "crit", "x", DUE, DUE, DUE, 0)


class ProbeDueTests(unittest.TestCase):
    def test_gate(self):
        self.assertTrue(checks_llm.probe_due(CFG, DUE, None))
        self.assertFalse(checks_llm.probe_due(CFG, NOT_DUE, "ok"))
        self.assertTrue(checks_llm.probe_due(CFG, NOT_DUE, "crit"))      # re-check while failing
        self.assertTrue(checks_llm.probe_due({**CFG, "_force": True}, NOT_DUE, None))


class AnthropicKeyTests(unittest.TestCase):
    def test_skipped_outside_the_hourly_slot(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe") as probe:
            self.assertEqual(checks_llm.check_anthropic_key(CFG, NOT_DUE), [])
        probe.assert_not_called()

    def test_valid_key_is_ok(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe"):
            res = checks_llm.check_anthropic_key(CFG, DUE)
        self.assertEqual([(r.key, r.level) for r in res], [("anthropic_key", OK)])

    def test_missing_key_is_critical_without_calling_the_api(self):
        with with_key(""), patch.object(checks_llm, "_count_tokens_probe") as probe:
            res = checks_llm.check_anthropic_key(CFG, DUE)
        self.assertEqual(res[0].level, CRIT)
        probe.assert_not_called()

    def test_auth_error_and_exhausted_credit_are_critical(self):
        for exc in (AuthenticationError("invalid x-api-key"),
                    BadRequestError("Your credit balance is too low")):
            with with_key(), patch.object(checks_llm, "_count_tokens_probe", side_effect=exc):
                self.assertEqual(checks_llm.check_anthropic_key(CFG, DUE)[0].level, CRIT)

    def test_a_network_error_is_only_a_warning(self):
        with with_key(), patch.object(checks_llm, "_count_tokens_probe",
                                      side_effect=APIConnectionError("timeout")):
            self.assertEqual(checks_llm.check_anthropic_key(CFG, DUE)[0].level, WARN)

    def test_runs_every_time_while_already_critical(self):
        cfg = {**CFG, "_prev": {"anthropic_key": crit_row("anthropic_key")}}
        with with_key(), patch.object(checks_llm, "_count_tokens_probe") as probe:
            checks_llm.check_anthropic_key(cfg, NOT_DUE)
        probe.assert_called_once()


class CreditsTests(unittest.TestCase):
    def twitter_row(self, err, err_h_ago, ok_h_ago):
        now = DUE
        return {"last_error": err,
                "last_error_at": now - timedelta(hours=err_h_ago) if err else None,
                "last_success_at": now - timedelta(hours=ok_h_ago) if ok_h_ago is not None else None}

    def run_check(self, row, apify, now=DUE, cfg=CFG):
        with patch.object(checks_llm.db, "one", return_value=row), \
             patch.object(checks_llm, "_apify_usage", return_value=apify):
            return {r.key: r for r in checks_llm.check_credits(cfg, now)}

    def test_402_after_the_last_success_is_critical(self):
        res = self.run_check(self.twitter_row("HTTPStatusError 402", 1, 5), None)
        self.assertEqual(res["credits:x"].level, CRIT)

    def test_402_followed_by_a_success_is_ok(self):
        res = self.run_check(self.twitter_row("HTTPStatusError 402", 5, 1), None)
        self.assertEqual(res["credits:x"].level, OK)

    def test_other_errors_and_no_state_are_ok(self):
        self.assertEqual(self.run_check(self.twitter_row("timeout", 1, 5), None)["credits:x"].level, OK)
        self.assertEqual(self.run_check(None, None)["credits:x"].level, OK)

    def test_apify_usage_levels(self):
        self.assertEqual(self.run_check(None, (49.5, 50.0))["credits:apify"].level, CRIT)
        self.assertEqual(self.run_check(None, (40.0, 50.0))["credits:apify"].level, WARN)
        self.assertEqual(self.run_check(None, (10.0, 50.0))["credits:apify"].level, OK)

    def test_apify_not_probed_outside_the_hourly_slot_and_without_a_token(self):
        self.assertNotIn("credits:apify", self.run_check(None, (49.5, 50.0), now=NOT_DUE))
        self.assertNotIn("credits:apify", self.run_check(None, None))


class LlmUsageTests(unittest.TestCase):
    NOW = datetime(2026, 10, 5, 12, 0, tzinfo=IST)  # "yesterday" is 2026-10-04

    def run_check(self, calls=5, unpriced=0, yesterday=2.0, base=2.0):
        daily = [{"d": date(2026, 9, 27) + timedelta(days=i), "cost": base} for i in range(7)]
        daily += [{"d": date(2026, 10, 4), "cost": yesterday}, {"d": date(2026, 10, 5), "cost": 0.5}]

        def fake_one(sql, params=None):
            return {"n": unpriced if "cost_usd IS NULL" in sql else calls}

        with patch.object(checks_llm.db, "one", side_effect=fake_one), \
             patch.object(checks_llm.db, "query", return_value=daily):
            return {r.key: r for r in checks_llm.check_llm_usage(CFG, self.NOW)}

    def test_no_calls_in_24h_warns(self):
        self.assertEqual(self.run_check(calls=0)["llm:calls"].level, WARN)
        self.assertEqual(self.run_check(calls=3)["llm:calls"].level, OK)

    def test_spend_spike_over_three_times_the_median_warns(self):
        self.assertEqual(self.run_check(yesterday=9.0)["llm:spend"].level, WARN)
        self.assertEqual(self.run_check(yesterday=5.0)["llm:spend"].level, OK)

    def test_spend_floor_stops_tiny_baselines_from_alerting(self):
        self.assertEqual(self.run_check(yesterday=0.9, base=0.1)["llm:spend"].level, OK)
        self.assertEqual(self.run_check(yesterday=1.5, base=0.1)["llm:spend"].level, WARN)

    def test_unpriced_models_warn(self):
        self.assertEqual(self.run_check(unpriced=3)["llm:unpriced"].level, WARN)
        self.assertEqual(self.run_check(unpriced=0)["llm:unpriced"].level, OK)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_llm.py -v`
Expected: FAIL (`cannot import name 'checks_llm'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/checks_llm.py
"""LLM key/credit checks and LLM usage sanity.

The Anthropic probe is the free count_tokens call (same as `./cm doctor`) and
the Apify probe is the free limits endpoint, both run at most hourly (the
watchdog fires every 20 minutes; the probe slot is minutes 0-19) — or on every
run while already critical so recovery is noticed. X exhaustion is read from
the ingest error the collector already stored, so the watchdog never spends
twitterapi.io credits. llm_usage only records calls that returned, so LLM
outages show up as failed stages / missing rows, not as error rows.
"""
from __future__ import annotations

import os
import statistics
from datetime import datetime, timedelta

import httpx

from community.config.log import IST
from community.config.settings import settings
from community.health.model import CRIT, OK, WARN, Result, owns
from community.store import db


def probe_due(cfg: dict, now: datetime, prev_level: str | None) -> bool:
    return bool(cfg.get("_force")) or prev_level == CRIT or now.astimezone(IST).minute < 20


def _count_tokens_probe() -> None:
    from community.llm.client import client
    client().messages.count_tokens(model=settings.enrich_model,
                                   messages=[{"role": "user", "content": "ping"}])


def _classify_llm_error(exc: Exception) -> Result:
    name, msg = type(exc).__name__, str(exc)
    if name in ("AuthenticationError", "PermissionDeniedError") or "credit balance" in msg.lower():
        return Result("anthropic_key", CRIT, f"{name}: {msg[:150]}",
                      "check the key and the credit balance in the Anthropic console")
    return Result("anthropic_key", WARN, f"probe failed ({name}: {msg[:100]}), treated as transient")


@owns("anthropic_key")
def check_anthropic_key(cfg: dict, now: datetime) -> list[Result]:
    prev = cfg.get("_prev", {}).get("anthropic_key")
    if not probe_due(cfg, now, prev.level if prev else None):
        return []
    if not settings.anthropic_api_key:
        return [Result("anthropic_key", CRIT, "ANTHROPIC_API_KEY is not set",
                       "enrichment and drafts cannot run without it")]
    try:
        _count_tokens_probe()
    except Exception as exc:  # noqa: BLE001 — classify instead of crashing the watchdog
        return [_classify_llm_error(exc)]
    return [Result("anthropic_key", OK, "key valid")]


def _apify_usage() -> tuple[float, float] | None:
    token = os.getenv("APIFY_TOKEN")
    if not token:
        return None
    r = httpx.get("https://api.apify.com/v2/users/me/limits",
                  headers={"Authorization": f"Bearer {token}"}, timeout=12)
    r.raise_for_status()
    data = r.json().get("data", {})
    used = (data.get("current") or {}).get("monthlyUsageUsd")
    cap = (data.get("limits") or {}).get("maxMonthlyUsageUsd")
    return (float(used), float(cap)) if used is not None and cap else None


@owns("credits:")
def check_credits(cfg: dict, now: datetime) -> list[Result]:
    results: list[Result] = []
    row = db.one("SELECT last_error, last_error_at, last_success_at FROM pipeline_state "
                 "WHERE stage = 'ingest' AND source = 'twitter'")
    exhausted = bool(row and row["last_error"] and "402" in row["last_error"]
                     and (row["last_success_at"] is None
                          or (row["last_error_at"] and row["last_error_at"] > row["last_success_at"])))
    results.append(Result("credits:x", CRIT, "twitterapi.io returned 402: credits exhausted",
                          "top up the twitterapi.io plan") if exhausted
                   else Result("credits:x", OK, "no 402 from twitterapi.io"))
    prev = cfg.get("_prev", {}).get("credits:apify")
    if probe_due(cfg, now, prev.level if prev else None):
        usage = _apify_usage()
        if usage:
            used, cap = usage
            pct = 100.0 * used / cap
            c = cfg["credits"]
            level = CRIT if pct >= c["apify_crit_pct"] else WARN if pct >= c["apify_warn_pct"] else OK
            results.append(Result("credits:apify", level,
                                  f"${used:.2f} of ${cap:.0f} Apify credits used this cycle ({pct:.0f}%)",
                                  "top up or raise the Apify monthly cap" if level != OK else ""))
    return results


@owns("llm:")
def check_llm_usage(cfg: dict, now: datetime) -> list[Result]:
    c = cfg["llm"]
    results: list[Result] = []
    calls = db.one("SELECT count(*) AS n FROM llm_usage WHERE ts > now() - (%s * interval '1 hour')",
                   (c["no_calls_hours"],))["n"]
    results.append(Result("llm:calls", OK if calls else WARN,
                          f"{calls} LLM calls in the last {c['no_calls_hours']} h" if calls
                          else f"no LLM calls recorded in the last {c['no_calls_hours']} h",
                          "" if calls else "enrichment/drafts may be down: check the anthropic_key check and out/cron.log"))
    daily = db.query(
        "SELECT (ts AT TIME ZONE 'Asia/Kolkata')::date AS d, coalesce(sum(cost_usd), 0) AS cost "
        "FROM llm_usage WHERE ts > now() - interval '10 days' GROUP BY 1 ORDER BY 1")
    spend = {r["d"]: float(r["cost"]) for r in daily}
    yesterday = now.astimezone(IST).date() - timedelta(days=1)
    prior = [spend[yesterday - timedelta(days=i)] for i in range(1, 8)
             if (yesterday - timedelta(days=i)) in spend]
    if yesterday in spend and prior:
        median = statistics.median(prior)
        limit = max(c["spend_floor_usd"], c["spend_multiple"] * median)
        results.append(Result("llm:spend", WARN if spend[yesterday] > limit else OK,
                              f"yesterday ${spend[yesterday]:.2f} vs typical ${median:.2f}"
                              f" (alert above ${limit:.2f})"))
    unpriced = db.one("SELECT count(*) AS n FROM llm_usage WHERE cost_usd IS NULL "
                      "AND ts > now() - interval '7 days'")["n"]
    results.append(Result("llm:unpriced", WARN if unpriced else OK,
                          f"{unpriced} calls in 7 days used a model missing from the price table"
                          if unpriced else "all recent calls were priced"))
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_checks_llm.py -v`
Expected: PASS (16 tests).

- [ ] **Step 5: Commit (only if the user has asked you to commit)**

```bash
git add community/health/checks_llm.py tests/test_health_checks_llm.py
git commit -m "Health: Anthropic key, credits and LLM-usage checks" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---
### Task 12: Watchdog engine and `./cm watchdog`

**Files:**
- Create: `community/health/engine.py`
- Modify: `runner.py` (add the `watchdog` command after `doctor`, around line 114)
- Test: `tests/test_health_engine.py`

**Interfaces:**
- Consumes: everything from Tasks 2-11 (`config.load`, `state.*`, `notify.*`, `resources.*`, `checks_*` functions, `model.*`).
- Produces (in `community.health.engine`):
  - `CRITICAL_CHECKS: list` = `[checks_jobs.check_jobs, checks_data.check_partitions, checks_llm.check_anthropic_key, checks_llm.check_credits, resources.check_resources]`; `DIGEST_ONLY_CHECKS: list` = `[checks_data.check_sources, checks_data.check_freshness, checks_llm.check_llm_usage, checks_jobs.check_recent_stage_failures, checks_jobs.check_watchdog_heartbeat]`.
  - `DB_DOWN_FLAG: Path` (`<out>/.watchdog_db_down`).
  - `Plan(decisions: list[Decision], message: str)`.
  - `run_checks(checks, cfg, now) -> tuple[list[Result], list[str]]` — a crashing check becomes a `check_error:<fn>` warning and its owned prefixes are returned as "failed".
  - `build_plan(results, prev: dict[str, Row], failed_prefixes: list[str], cfg, now) -> Plan` (pure).
  - `run_watchdog(*, dry_run=False, test_message=False, now=None) -> dict` with keys `checked`, `critical`, `warnings`, `posted` (status string or None), `actions` (`{key: action}` for non-"none" decisions), `db_recovered`; or `{"test_message": status}`; or `{"db_unreachable": True, "posted": status}`.
  - Runner command `watchdog(dry_run: bool = False, test_message: bool = False, verbose: bool = False)`; prints a JSON summary only when `verbose`, `dry_run`, `test_message`, something was posted, or an action happened; exits 1 on an unexpected exception.

Behaviour rules the tests pin: a Slack post that fails (`"error: ..."`) leaves alert-bearing rows unsaved so the next run retries; a crashed check never resolves an open critical; `--dry-run` writes nothing and posts nothing; a missing alerts webhook is not an error.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_engine.py
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import runner
from community.health import engine
from community.health.model import CRIT, OK, WARN, Result, owns
from community.health.state import Row

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CFG = engine.config.load({})


def crit_prev(key="fake:x", ok=0, alerted_h=1.0):
    return Row(key, CRIT, "old", NOW - timedelta(hours=3), NOW - timedelta(minutes=20),
               NOW - timedelta(hours=alerted_h), ok)


@owns("fake:")
def check_fake_crit(cfg, now):
    return [Result("fake:x", CRIT, "boom", "look here")]


@owns("fake:")
def check_fake_ok(cfg, now):
    return [Result("fake:x", OK, "fine")]


@owns("fake:")
def check_fake_crashes(cfg, now):
    raise RuntimeError("kaput")


@owns("other:")
def check_other_warn(cfg, now):
    return [Result("other:y", WARN, "meh")]


class RunChecksTests(unittest.TestCase):
    def test_a_crashing_check_becomes_a_warning_and_the_rest_still_run(self):
        results, failed = engine.run_checks([check_fake_crashes, check_other_warn], CFG, NOW)
        keys = {r.key: r for r in results}
        self.assertEqual(keys["check_error:check_fake_crashes"].level, WARN)
        self.assertIn("kaput", keys["check_error:check_fake_crashes"].detail)
        self.assertIn("other:y", keys)
        self.assertEqual(failed, ["fake:"])


class BuildPlanTests(unittest.TestCase):
    def plan(self, results, prev=None, failed=()):
        return engine.build_plan(results, prev or {}, list(failed), CFG, NOW)

    def test_new_critical_produces_an_alert_line(self):
        plan = self.plan([Result("fake:x", CRIT, "boom", "look here")])
        self.assertEqual([d.action for d in plan.decisions], ["alert"])
        self.assertTrue(plan.message.startswith("[CRITICAL] fake:x: boom"))

    def test_warnings_never_produce_a_message(self):
        self.assertEqual(self.plan([Result("other:y", WARN, "meh")]).message, "")

    def test_a_vanished_critical_resolves_after_two_clean_evaluations(self):
        self.assertEqual(self.plan([], {"fake:x": crit_prev(ok=0)}).message, "")  # first clean pass
        plan = self.plan([], {"fake:x": crit_prev(ok=1)})                          # second
        self.assertIn("[RESOLVED] fake:x", plan.message)

    def test_a_check_that_crashed_does_not_resolve_its_open_critical(self):
        plan = self.plan([], {"fake:x": crit_prev(ok=1)}, failed=["fake:"])
        self.assertEqual(plan.decisions, [])
        self.assertEqual(plan.message, "")

    def test_alerts_are_listed_before_resolves(self):
        plan = self.plan([Result("fake:new", CRIT, "bad")], {"fake:old": crit_prev("fake:old", ok=1)})
        lines = plan.message.splitlines()
        self.assertTrue(lines[0].startswith("[CRITICAL] fake:new"))
        self.assertTrue(lines[-1].startswith("[RESOLVED] fake:old"))


class WatchdogRunTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.flag = pathlib.Path(tmp.name) / ".watchdog_db_down"
        self.saved: list[Row] = []
        for p in (patch.object(engine, "DB_DOWN_FLAG", self.flag),
                  patch.object(engine, "_db_up", return_value=True),
                  patch.object(engine.resources, "collect_and_record", return_value={}),
                  patch.object(engine.state, "load_states", return_value={}),
                  patch.object(engine.state, "save", side_effect=self.saved.append)):
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, checks, post="sent", **kw):
        with patch.object(engine, "CRITICAL_CHECKS", checks), \
             patch.object(engine.notify, "post", return_value=post) as post_mock:
            summary = engine.run_watchdog(now=NOW, **kw)
        return summary, post_mock

    def saved_keys(self):
        return [r.key for r in self.saved]

    def test_new_critical_is_posted_and_its_state_saved(self):
        summary, post = self.run_with([check_fake_crit])
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].startswith("[CRITICAL] fake:x"))
        self.assertEqual(summary["posted"], "sent")
        self.assertEqual(summary["critical"], ["fake:x"])
        self.assertEqual(summary["actions"], {"fake:x": "alert"})
        self.assertIn("fake:x", self.saved_keys())
        self.assertIn("watchdog_heartbeat", self.saved_keys())

    def test_a_failed_slack_post_leaves_the_alert_unsaved_so_it_retries(self):
        summary, _ = self.run_with([check_fake_crit], post="error: HTTPStatusError: 500")
        self.assertTrue(summary["posted"].startswith("error"))
        self.assertNotIn("fake:x", self.saved_keys())
        self.assertIn("watchdog_heartbeat", self.saved_keys())

    def test_nothing_to_report_posts_nothing(self):
        summary, post = self.run_with([check_fake_ok])
        post.assert_not_called()
        self.assertIsNone(summary["posted"])
        self.assertIn("fake:x", self.saved_keys())

    def test_a_crashed_check_does_not_resolve_an_open_critical(self):
        engine.state.load_states.return_value = {"fake:x": crit_prev(ok=1)}
        summary, post = self.run_with([check_fake_crashes])
        post.assert_not_called()
        self.assertNotIn("fake:x", self.saved_keys())

    def test_dry_run_writes_and_posts_nothing(self):
        with patch.object(engine, "CRITICAL_CHECKS", [check_fake_crit]):
            summary = engine.run_watchdog(dry_run=True, now=NOW)
        self.assertEqual(summary["posted"], "dry-run")
        self.assertEqual(self.saved, [])
        engine.resources.collect_and_record.assert_not_called()

    def test_test_message_posts_without_touching_the_database(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_watchdog(test_message=True, now=NOW)
        self.assertEqual(summary, {"test_message": "sent"})
        self.assertTrue(post.call_args.args[0].startswith("[TEST]"))
        engine._db_up.assert_not_called()

    def test_database_down_posts_once_then_stays_quiet_inside_the_reminder_window(self):
        engine._db_up.return_value = False
        with patch.object(engine.notify, "post", return_value="sent") as post:
            first = engine.run_watchdog(now=NOW)
            second = engine.run_watchdog(now=NOW)
            old = time.time() - 7 * 3600
            os.utime(self.flag, (old, old))
            third = engine.run_watchdog(now=NOW)
        self.assertTrue(first["db_unreachable"])
        self.assertEqual(post.call_count, 2)  # first + after the 6 h reminder window
        self.assertIsNone(second["posted"])
        self.assertEqual(third["posted"], "sent")
        self.assertIn("[CRITICAL] db_unreachable", post.call_args_list[0].args[0])

    def test_database_back_up_posts_resolved_and_clears_the_flag(self):
        self.flag.touch()
        summary, post = self.run_with([check_fake_ok])
        self.assertTrue(summary["db_recovered"])
        self.assertIn("[RESOLVED] db_unreachable", post.call_args_list[0].args[0])
        self.assertFalse(self.flag.exists())


class WatchdogCommandTests(unittest.TestCase):
    def call(self, summary, **kw):
        with patch("community.health.engine.run_watchdog", return_value=summary), \
             patch.object(runner.typer, "echo") as echo:
            runner.watchdog(**{"dry_run": False, "test_message": False, "verbose": False, **kw})
        return echo

    def test_silent_when_nothing_happened(self):
        self.call({"posted": None, "actions": {}}).assert_not_called()

    def test_prints_when_something_was_posted_or_verbose(self):
        self.call({"posted": "sent", "actions": {"a": "alert"}}).assert_called_once()
        self.call({"posted": None, "actions": {}}, verbose=True).assert_called_once()

    def test_unexpected_exception_exits_one(self):
        with patch("community.health.engine.run_watchdog", side_effect=RuntimeError("x")):
            with self.assertRaises(SystemExit) as ctx:
                runner.watchdog(dry_run=False, test_message=False, verbose=False)
        self.assertEqual(ctx.exception.code, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_engine.py -v`
Expected: FAIL (`cannot import name 'engine'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/engine.py
"""Run checks, decide, post, persist (spec §3, §7).

Watchdog (cron */20, critical checks only): silent unless a check turns
critical, stays critical past the reminder window, or recovers. Safety rules:
a failed Slack post leaves the alert unsaved (it retries next run); a crashed
check never resolves an open critical; a database outage is reported straight
to Slack with a file-based throttle (the DB-backed state is unavailable).
Queries run with a 20 s statement timeout (PGOPTIONS, process-local).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from community.config.log import get_logger
from community.config.settings import settings
from community.health import checks_data, checks_jobs, checks_llm, config, notify, resources, state
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Decision, Row

log = get_logger("health.engine")

CRITICAL_CHECKS = [checks_jobs.check_jobs, checks_data.check_partitions,
                   checks_llm.check_anthropic_key, checks_llm.check_credits,
                   resources.check_resources]
DIGEST_ONLY_CHECKS = [checks_data.check_sources, checks_data.check_freshness,
                      checks_llm.check_llm_usage, checks_jobs.check_recent_stage_failures,
                      checks_jobs.check_watchdog_heartbeat]
DB_DOWN_FLAG = resources.OUT_DIR / ".watchdog_db_down"
_ORDER = {"alert": 0, "remind": 1, "resolve": 2, "none": 3}
_ALERT_SUBJECT = "Beacon alert"


@dataclass(frozen=True)
class Plan:
    decisions: list[Decision]
    message: str


def run_checks(checks: list, cfg: dict, now: datetime) -> tuple[list[Result], list[str]]:
    results: list[Result] = []
    failed: list[str] = []
    for fn in checks:
        try:
            results.extend(fn(cfg, now))
        except Exception as exc:  # noqa: BLE001 — one broken check never kills the run
            log.exception("check %s crashed", fn.__name__)
            failed.extend(getattr(fn, "PREFIXES", ()))
            results.append(Result(f"check_error:{fn.__name__}", WARN,
                                  f"{type(exc).__name__}: {str(exc)[:150]}"))
    return results, failed


def _line(d: Decision, now: datetime) -> str:
    if d.action == "alert":
        return notify.fmt_alert(d.result)
    if d.action == "remind":
        return notify.fmt_remind(d.result, d.crit_since or now, now)
    return notify.fmt_resolved(d.key, d.crit_since or now, now)


def build_plan(results: list[Result], prev: dict[str, Row], failed_prefixes: list[str],
               cfg: dict, now: datetime) -> Plan:
    by_key = {r.key: r for r in results}
    for key, row in prev.items():
        # A critical key that is no longer reported means the problem cleared,
        # unless the check that owns it crashed this run (then we know nothing).
        if row.level == CRIT and key not in by_key \
                and not any(key.startswith(p) for p in failed_prefixes):
            by_key[key] = Result(key, OK, "no longer reported")
    decisions = [state.decide(prev.get(k), res, now, remind_hours=cfg["remind_hours"],
                              resolve_after_ok=cfg["resolve_after_ok"])
                 for k, res in by_key.items()]
    decisions.sort(key=lambda d: _ORDER[d.action])
    lines = [_line(d, now) for d in decisions if d.action != "none"]
    return Plan(decisions, "\n".join(lines))


def _db_up() -> bool:
    try:
        import psycopg
        psycopg.connect(settings.db_url, connect_timeout=10).close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _db_down(cfg: dict, now: datetime, dry_run: bool) -> dict:
    flag = DB_DOWN_FLAG
    due = (not flag.exists()
           or (time.time() - flag.stat().st_mtime) >= cfg["remind_hours"] * 3600)
    status = None
    if due:
        status = notify.post(
            "[CRITICAL] db_unreachable: the watchdog cannot connect to Postgres.\n"
            "    What to check: docker compose ps; docker compose logs postgres --tail 100",
            _ALERT_SUBJECT, cfg, dry_run)
        if not dry_run and not str(status).startswith("error"):
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.touch()
    return {"db_unreachable": True, "posted": status}


def _db_recovered(cfg: dict, dry_run: bool) -> bool:
    if not DB_DOWN_FLAG.exists():
        return False
    if not dry_run:
        notify.post("[RESOLVED] db_unreachable (Postgres is reachable again)", _ALERT_SUBJECT, cfg)
        DB_DOWN_FLAG.unlink(missing_ok=True)
    return True


def run_watchdog(*, dry_run: bool = False, test_message: bool = False,
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cfg = config.load()
    os.environ.setdefault("PGOPTIONS", "-c statement_timeout=20000")
    if test_message:
        status = notify.post("[TEST] Beacon watchdog test message. If you can read this, "
                             "critical alerts reach this channel.", "Beacon alert test", cfg, dry_run)
        return {"test_message": status}
    if not _db_up():
        return _db_down(cfg, now, dry_run)
    recovered = _db_recovered(cfg, dry_run)
    if not dry_run:
        resources.collect_and_record()
    prev = state.load_states()
    cfg["_prev"] = prev
    cfg["_dry_run"] = dry_run
    results, failed = run_checks(CRITICAL_CHECKS, cfg, now)
    plan = build_plan(results, prev, failed, cfg, now)
    status = notify.post(plan.message, _ALERT_SUBJECT, cfg, dry_run) if plan.message else None
    post_failed = bool(status) and status.startswith("error")
    if not dry_run:
        for d in plan.decisions:
            if post_failed and d.action != "none":
                continue  # not delivered: keep the old row so the next run retries
            state.save(d.row)
        state.save(Row("watchdog_heartbeat", OK, "", now, now, None, 0))
    return {
        "checked": len(results),
        "critical": [r.key for r in results if r.level == CRIT],
        "warnings": [r.key for r in results if r.level == WARN],
        "posted": status,
        "actions": {d.key: d.action for d in plan.decisions if d.action != "none"},
        "db_recovered": recovered,
    }
```

Add the command to `runner.py`, directly after the `doctor` command (after line 113, before `run-local`):

```python
@app.command()
def watchdog(dry_run: bool = False, test_message: bool = False, verbose: bool = False) -> None:
    """Critical health checks (cron every 20 min). Posts to the Slack alerts
    channel only when a check turns critical, stays critical (reminder) or
    recovers; silent otherwise. --dry-run prints instead of posting/saving;
    --test-message sends one [TEST] line to prove the webhook works."""
    from community.config.log import get_logger
    from community.health.engine import run_watchdog

    try:
        summary = run_watchdog(dry_run=dry_run, test_message=test_message)
    except Exception:  # noqa: BLE001
        get_logger("runner").exception("watchdog FAILED")
        raise SystemExit(1)
    if verbose or dry_run or test_message or summary.get("posted") or summary.get("actions"):
        typer.echo(json.dumps(summary, default=str))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_engine.py -v`
Expected: PASS (17 tests).

- [ ] **Step 5: Smoke-test against the local dev DB**

Run: `./cm watchdog --dry-run`
Expected: one JSON line with `"posted": "dry-run"`, a `checked` count, and `critical`/`warnings` lists (on a fresh local DB you will see `partitions:*` fine, `backup` warn, and possibly `credits`/`anthropic_key` entries). No rows are written: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT count(*) FROM health_state"` is unchanged.

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add community/health/engine.py runner.py tests/test_health_engine.py
git commit -m "Health: watchdog engine and ./cm watchdog" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Morning digest and `./cm health-digest`

**Files:**
- Create: `community/health/digest.py`
- Modify: `community/health/engine.py` (import `digest`; add `run_digest`), `runner.py` (add the `health-digest` command after `watchdog`)
- Test: `tests/test_health_digest.py`

**Interfaces:**
- Consumes: `Result` list, config, `resources.history/top_tables`, `community.diagnostics._live_probe(name) -> dict` (returns `{"live": "ok"|"no_key"|"http_<code>"|"unreachable"|"blocked_or_down"|"no_probe", "detail"?: str}`, never raises).
- Produces:
  - `digest.collect_context(cfg, now, live=True) -> dict` with keys `jobs` (latest non-skipped row per job), `llm` (`{day, calls, cost}` for yesterday IST), `resources` (latest values), `top_tables` (`[(name, bytes)]`), `live` (`{source: probe dict}`).
  - `digest.live_results(ctx) -> list[Result]` — a `live_probe:<name>` warning for every probe whose `live` value is not `ok`/`no_probe`; `no_key` becomes "the source is enabled but its API key is not set" (the old `source_health` "needs key" state; only enabled, un-muted sources are probed).
  - `digest.render(results, ctx, cfg, now) -> str` — plain text, ASCII, problems first.
  - `engine.run_digest(*, dry_run=False, live=True, now=None) -> dict` with `checks`, `critical`, `warnings`, `posted`, `text` (only when `dry_run`); sets `cfg["_force"] = True` so probes are not hourly-gated; saves only `digest_heartbeat`.
  - Runner command `health-digest(dry_run: bool = False, no_live: bool = False)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_health_digest.py
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import runner
from community.health import config, digest, engine
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Row

NOW = datetime(2026, 10, 5, 1, 35, tzinfo=timezone.utc)  # 07:05 IST
CFG = config.load({})
CTX = {
    "jobs": [{"job": "run-local", "status": "ok", "started_at": NOW - timedelta(minutes=40),
              "finished_at": NOW - timedelta(minutes=30)}],
    "llm": {"day": date(2026, 10, 4), "calls": 143, "cost": 0.82},
    "resources": {"disk_used_pct": 63.2, "disk_free_gb": 41.0, "mem_available_pct": 54.0,
                  "load_per_core": 0.3, "db_size_gb": 2.14, "cron_log_mb": 12.0},
    "top_tables": [("social_items_y2026m09", 1_200_000_000)],
    "live": {"twitter": {"live": "ok"}},
}


class RenderTests(unittest.TestCase):
    def test_all_healthy_headline_mentions_muted_sources(self):
        text = digest.render([Result("a", OK, "fine"), Result("b", OK, "fine")], CTX, CFG, NOW)
        self.assertEqual(text.splitlines()[0],
                         "Beacon health: all 2 checks healthy (muted, known broken: reddit)")

    def test_problems_come_first_with_counts_and_hints(self):
        results = [Result("ok1", OK, "fine"),
                   Result("partitions:social_items", WARN, "27 days left"),
                   Result("disk", CRIT, "93% used", "free space on the VM")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertIn("3 checks, 1 critical, 1 warnings", text.splitlines()[0])
        self.assertLess(text.index("*Critical*"), text.index("*Warnings*"))
        self.assertLess(text.index("*Warnings*"), text.index("*Jobs*"))
        self.assertIn("- disk: 93% used", text)
        self.assertIn("What to check: free space on the VM", text)

    def test_sections_show_jobs_llm_resources_and_sources(self):
        results = [Result("source:twitter", OK, "last success 1 h ago"),
                   Result("source_items:twitter", OK, "newest item arrived 1 h ago")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertIn("- run-local: ok, last run 40 min ago", text)
        self.assertIn("- morning-build: no run recorded yet", text)
        self.assertIn("143 calls", text)
        self.assertIn("$0.82", text)
        self.assertIn("disk 63% used (41 GB free)", text)
        self.assertIn("database 2.1 GB", text)
        self.assertIn("social_items_y2026m09", text)
        self.assertIn("- twitter: last success 1 h ago", text)
        self.assertIn("live probe ok", text)

    def test_text_is_plain_ascii(self):
        results = [Result("disk", CRIT, "93% used", "free space")]
        self.assertTrue(all(ord(c) < 128 for c in digest.render(results, CTX, CFG, NOW)))

    def test_missing_context_pieces_do_not_crash(self):
        empty = {"jobs": [], "llm": {"day": date(2026, 10, 4), "calls": 0, "cost": 0.0},
                 "resources": {}, "top_tables": [], "live": {}}
        self.assertIn("Beacon health", digest.render([], empty, CFG, NOW))


class LiveResultsTests(unittest.TestCase):
    def test_only_real_probe_problems_become_warnings(self):
        ctx = {"live": {"twitter": {"live": "ok"}, "youtube": {"live": "http_403"},
                        "instagram": {"live": "no_key"}, "reddit": {"live": "blocked_or_down"},
                        "app_reviews": {"live": "no_probe"}}}
        res = {r.key: r for r in digest.live_results(ctx)}
        self.assertEqual(sorted(res), ["live_probe:instagram", "live_probe:reddit",
                                       "live_probe:youtube"])
        self.assertTrue(all(r.level == WARN for r in res.values()))
        self.assertIn("API key is not set", res["live_probe:instagram"].detail)
        self.assertIn("http_403", res["live_probe:youtube"].detail)


class RunDigestTests(unittest.TestCase):
    def setUp(self):
        self.saved: list[Row] = []
        self.seen_cfg: dict = {}

        def capture_cfg(cfg, now):
            self.seen_cfg.update(cfg)
            return []
        capture_cfg.PREFIXES = ()
        self.capture_cfg = capture_cfg
        for p in (patch.object(engine, "_db_up", return_value=True),
                  patch.object(engine.state, "load_states", return_value={}),
                  patch.object(engine.state, "save", side_effect=self.saved.append),
                  patch.object(engine.digest, "collect_context", return_value=CTX),
                  patch.object(engine, "CRITICAL_CHECKS", [engine.checks_jobs.check_watchdog_heartbeat]),
                  patch.object(engine, "DIGEST_ONLY_CHECKS", [])):
            p.start()
            self.addCleanup(p.stop)

    def test_posts_the_rendered_message_and_saves_only_the_heartbeat(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].startswith("Beacon health:"))
        self.assertEqual(summary["posted"], "sent")
        self.assertEqual([r.key for r in self.saved], ["digest_heartbeat"])

    def test_dry_run_returns_the_text_and_saves_nothing(self):
        summary = engine.run_digest(dry_run=True, now=NOW)
        self.assertEqual(summary["posted"], "dry-run")
        self.assertIn("Beacon health:", summary["text"])
        self.assertEqual(self.saved, [])

    def test_probes_are_forced_so_the_hourly_gate_is_bypassed(self):
        with patch.object(engine, "CRITICAL_CHECKS", [self.capture_cfg]), \
             patch.object(engine.notify, "post", return_value="sent"):
            engine.run_digest(now=NOW)
        self.assertTrue(self.seen_cfg["_force"])

    def test_live_probe_failures_appear_as_warnings(self):
        ctx = {**CTX, "live": {"youtube": {"live": "http_403"}}}
        with patch.object(engine.digest, "collect_context", return_value=ctx), \
             patch.object(engine.notify, "post", return_value="sent") as post:
            engine.run_digest(now=NOW)
        self.assertIn("live_probe:youtube", post.call_args.args[0])

    def test_database_down_sends_a_short_critical_instead_of_crashing(self):
        engine._db_up.return_value = False
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        self.assertTrue(summary["db_unreachable"])
        self.assertIn("could not run", post.call_args.args[0])


class DigestCommandTests(unittest.TestCase):
    def test_dry_run_prints_the_text_then_a_summary(self):
        summary = {"checks": 3, "critical": [], "warnings": [], "posted": "dry-run", "text": "Beacon health: ok"}
        with patch("community.health.engine.run_digest", return_value=summary) as run, \
             patch.object(runner.typer, "echo") as echo:
            runner.health_digest(dry_run=True, no_live=True)
        run.assert_called_once_with(dry_run=True, live=False)
        self.assertEqual(echo.call_args_list[0].args[0], "Beacon health: ok")
        self.assertNotIn("Beacon health: ok", echo.call_args_list[1].args[0])

    def test_unexpected_exception_exits_one(self):
        with patch("community.health.engine.run_digest", side_effect=RuntimeError("x")):
            with self.assertRaises(SystemExit) as ctx:
                runner.health_digest(dry_run=False, no_live=False)
        self.assertEqual(ctx.exception.code, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_digest.py -v`
Expected: FAIL (`cannot import name 'digest'`).

- [ ] **Step 3: Write the implementation**

```python
# community/health/digest.py
"""The morning status message: problems first, then jobs, sources, LLM, resources.

Plain ASCII, no emoji (locked decision). `collect_context` gathers the numbers
that are not check results; `render` is pure so it is easy to test.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from community.config.log import IST
from community.health import resources
from community.health.model import CRIT, WARN, Result

_PROBE_NAMES = ("twitter", "youtube", "github", "broker_communities", "app_reviews", "instagram")
_PROBE_OK = ("ok", "no_probe")


def _live_probes(cfg: dict) -> dict:
    from community.config.settings import settings
    from community.diagnostics import _live_probe  # same probes as ./cm doctor (never raise)
    muted = set(cfg["muted"])
    configured = settings.registry.get("sources", {})
    out = {}
    for name in _PROBE_NAMES:
        if name in muted or not (configured.get(name) or {}).get("enabled", False):
            continue
        out[name] = _live_probe(name)
    return out


def collect_context(cfg: dict, now: datetime, live: bool = True) -> dict:
    from community.store import db
    ctx: dict = {}
    ctx["jobs"] = db.query(
        "SELECT DISTINCT ON (job) job, status, started_at, finished_at FROM job_runs "
        "WHERE status <> 'skipped_locked' ORDER BY job, started_at DESC")
    day = now.astimezone(IST).date() - timedelta(days=1)
    row = db.one("SELECT count(*) AS calls, coalesce(sum(cost_usd), 0) AS cost FROM llm_usage "
                 "WHERE (ts AT TIME ZONE 'Asia/Kolkata')::date = %s", (day,))
    ctx["llm"] = {"day": day, "calls": row["calls"], "cost": float(row["cost"])}
    latest: dict[str, float] = {}
    for metric in ("disk_used_pct", "disk_free_gb", "mem_available_pct",
                   "load_per_core", "db_size_gb", "cron_log_mb"):
        hist = resources.history(metric, 3)
        if hist:
            latest[metric] = hist[-1][1]
    ctx["resources"] = latest
    ctx["top_tables"] = resources.top_tables()
    ctx["live"] = _live_probes(cfg) if live else {}
    return ctx


def live_results(ctx: dict) -> list[Result]:
    out = []
    for name, probe in sorted(ctx.get("live", {}).items()):
        value = probe.get("live")
        if value == "no_key":  # only enabled sources are probed, so this is a real gap
            out.append(Result(f"live_probe:{name}", WARN,
                              "the source is enabled but its API key is not set"))
        elif value not in _PROBE_OK:
            extra = f" ({probe['detail']})" if probe.get("detail") else ""
            out.append(Result(f"live_probe:{name}", WARN, f"live probe {value}{extra}"))
    return out


def _ago(ts: datetime | None, now: datetime) -> str:
    if ts is None:
        return "never"
    hours = (now - ts).total_seconds() / 3600
    if hours < 1:
        return f"{max(round(hours * 60), 1)} min ago"  # round: 40 min is 39.999... after float division
    if hours < 48:
        return f"{hours:.0f} h ago"
    return f"{hours / 24:.0f} d ago"


def _resource_line(r: dict) -> str:
    bits = []
    if "disk_used_pct" in r:
        free = f" ({r['disk_free_gb']:.0f} GB free)" if "disk_free_gb" in r else ""
        bits.append(f"disk {r['disk_used_pct']:.0f}% used{free}")
    if "mem_available_pct" in r:
        bits.append(f"memory {r['mem_available_pct']:.0f}% available")
    if "load_per_core" in r:
        bits.append(f"load {r['load_per_core']:.1f} per core")
    if "db_size_gb" in r:
        bits.append(f"database {r['db_size_gb']:.1f} GB")
    if "cron_log_mb" in r:
        bits.append(f"cron.log {r['cron_log_mb']:.0f} MB")
    return ", ".join(bits)


def _problem_block(title: str, rows: list[Result]) -> list[str]:
    if not rows:
        return []
    lines = [f"*{title}*"]
    for r in rows:
        lines.append(f"- {r.key}: {r.detail}")
        if r.hint:
            lines.append(f"    What to check: {r.hint}")
    return lines + [""]


def render(results: list[Result], ctx: dict, cfg: dict, now: datetime) -> str:
    crit = sorted((r for r in results if r.level == CRIT), key=lambda r: r.key)
    warn = sorted((r for r in results if r.level == WARN), key=lambda r: r.key)
    total = len(results)
    head = (f"Beacon health: all {total} checks healthy" if not crit and not warn
            else f"Beacon health: {total} checks, {len(crit)} critical, {len(warn)} warnings")
    if cfg["muted"]:
        head += f" (muted, known broken: {', '.join(cfg['muted'])})"
    lines = [head, ""]
    lines += _problem_block("Critical", crit)
    lines += _problem_block("Warnings", warn)

    last = {j["job"]: j for j in ctx.get("jobs", [])}
    lines.append("*Jobs*")
    for job in cfg["jobs"]:
        j = last.get(job)
        lines.append(f"- {job}: {j['status']}, last run {_ago(j['started_at'], now)}" if j
                     else f"- {job}: no run recorded yet")
    lines.append("")

    by_key = {r.key: r for r in results}
    source_lines = []
    for name in cfg["sources"]["map"]:
        res = by_key.get(f"source:{name}")
        if res is None:
            continue
        bits = [res.detail]
        items = by_key.get(f"source_items:{name}")
        if items:
            bits.append(items.detail)
        probe = ctx.get("live", {}).get(name)
        if probe:
            bits.append(f"live probe {probe.get('live')}")
        source_lines.append(f"- {name}: {'; '.join(bits)}")
    if source_lines:
        lines += ["*Sources*"] + source_lines + [""]

    llm = ctx["llm"]
    lines += ["*LLM*", f"- {llm['day']:%d %b}: {llm['calls']} calls, ${llm['cost']:.2f}", ""]

    res_line = _resource_line(ctx.get("resources", {}))
    tables = ctx.get("top_tables", [])
    if res_line or tables:
        lines.append("*Resources*")
        if res_line:
            lines.append(f"- {res_line}")
        if tables:
            lines.append("- largest tables: " + ", ".join(
                f"{name} {size / 1e9:.1f} GB" for name, size in tables))
        lines.append("")
    lines.append(f"Generated {now.astimezone(IST):%d %b %H:%M} IST")
    return "\n".join(lines)
```

Edit `community/health/engine.py`: change the import line to include `digest`, and add `IST`:

```python
from community.config.log import IST, get_logger
from community.config.settings import settings
from community.health import (checks_data, checks_jobs, checks_llm, config, digest,
                              notify, resources, state)
```

Append to `community/health/engine.py`:

```python
def run_digest(*, dry_run: bool = False, live: bool = True,
               now: datetime | None = None) -> dict:
    """Daily status message (cron 07:05 IST). Evaluates every check, saves no
    alert state (only its own heartbeat), and runs probes unconditionally."""
    now = now or datetime.now(timezone.utc)
    cfg = config.load()
    os.environ.setdefault("PGOPTIONS", "-c statement_timeout=20000")
    if not _db_up():
        status = notify.post("[CRITICAL] health digest could not run: Postgres is unreachable.",
                             "Beacon health", cfg, dry_run)
        return {"db_unreachable": True, "posted": status}
    prev = state.load_states()
    cfg.update({"_prev": prev, "_force": True, "_dry_run": dry_run})
    results, _failed = run_checks(CRITICAL_CHECKS + DIGEST_ONLY_CHECKS, cfg, now)
    ctx = digest.collect_context(cfg, now, live=live)
    results = results + digest.live_results(ctx)
    text = digest.render(results, ctx, cfg, now)
    status = notify.post(text, f"Beacon health - {now.astimezone(IST):%d %b %Y}", cfg, dry_run)
    if not dry_run:
        state.save(Row("digest_heartbeat", OK, "", now, now, None, 0))
    return {
        "checks": len(results),
        "critical": [r.key for r in results if r.level == CRIT],
        "warnings": [r.key for r in results if r.level == WARN],
        "posted": status,
        "text": text if dry_run else None,
    }
```

Add the command to `runner.py`, directly after the `watchdog` command:

```python
@app.command("health-digest")
def health_digest(dry_run: bool = False, no_live: bool = False) -> None:
    """Daily health status message for Slack (cron 07:05 IST): problems first,
    then jobs, sources, LLM, resources. --dry-run prints the message instead of
    posting; --no-live skips the per-source live reachability probes."""
    from community.config.log import get_logger
    from community.health.engine import run_digest

    try:
        summary = run_digest(dry_run=dry_run, live=not no_live)
    except Exception:  # noqa: BLE001
        get_logger("runner").exception("health-digest FAILED")
        raise SystemExit(1)
    if dry_run:
        typer.echo(summary["text"])
    typer.echo(json.dumps({k: v for k, v in summary.items() if k != "text"}, default=str))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_digest.py tests/test_health_engine.py -v`
Expected: PASS (all digest tests plus the 17 engine tests; the engine tests must still pass after the import edit).

- [ ] **Step 5: Smoke-test against the local dev DB**

Run: `./cm health-digest --dry-run --no-live`
Expected: the full message is printed (first line `Beacon health: ...`, sections `*Jobs*`, `*LLM*`, ...) followed by one JSON line with `"posted": "dry-run"`. Confirm there is no emoji and that `partitions:*` appears as a warning or ok depending on the dev DB's partitions.

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add community/health/digest.py community/health/engine.py runner.py tests/test_health_digest.py
git commit -m "Health: morning digest and ./cm health-digest" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Registry block, env var, crontabs, runbook

**Files:**
- Modify: `community/config/registry.yaml` (append the `health:` block at the end of the file), `community/config/env.example`, `deploy/crontab.prod`, `deploy/crontab.prod.utc`, `deploy/README-prod.md`, `CLAUDE.md`
- Test: `tests/test_health_config.py` (add one test)

**Interfaces:**
- Consumes: `config.DEFAULTS` (every key written to the registry block must already exist there).
- Produces: nothing for later code; this is the operator-facing wiring.

- [ ] **Step 1: Write the failing test** (append to `ConfigTests` in `tests/test_health_config.py`)

```python
    def test_registry_health_block_only_uses_known_keys(self):
        import pathlib

        import yaml
        registry_path = pathlib.Path(config.__file__).parent.parent / "config" / "registry.yaml"
        reg = yaml.safe_load(registry_path.read_text())
        self.assertIn("health", reg, "registry.yaml must carry the health: block")

        def check(over, base, path="health"):
            for key, value in over.items():
                self.assertIn(key, base, f"unknown key {path}.{key}")
                if isinstance(value, dict):
                    check(value, base[key], f"{path}.{key}")

        check(reg["health"], config.DEFAULTS)
        merged = config.load(reg)  # the real registry must merge cleanly
        self.assertEqual(merged["muted"], reg["health"]["muted"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `"$CM_PYTHON" -m pytest tests/test_health_config.py -v`
Expected: FAIL (`registry.yaml must carry the health: block`).

- [ ] **Step 3: Make the edits**

Append to the end of `community/config/registry.yaml` (after the Groww landscape entry):

```yaml

health:                            # Slack health alerts: docs/superpowers/specs/2026-10-05-slack-health-alerts-design.md
  # Every key here has an in-code default (community/health/config.py). The prod
  # VM bind-mounts ITS OWN copy of this file over the image's, so a release
  # cannot assume this block exists there; edit it only to tune.
  muted: [reddit]                  # known broken (parked, commit 9f3134e): digest line only, never alerts
  remind_hours: 6                  # re-post a still-critical alert this often
  fallback_to_default_webhook: false   # true = also use SLACK_WEBHOOK_URL (SSO approvals channel) if SLACK_ALERTS_WEBHOOK_URL is unset
  enrichment_backlog_warn: 200     # items waiting >2h for enrichment (uncalibrated 2026-10-05)
  resources:
    disk_warn_pct: 80
    disk_crit_pct: 90
    disk_eta_crit_days: 7
    mem_crit_pct: 10
    cron_log_warn_mb: 500
    backup_crit_hours: 30
```

In `community/config/env.example`, find the Slack lines (`grep -n -i slack community/config/env.example`) and add this block directly after them:

```
# ── Health alerts (Slack) ────────────────────────────────────────────────────
# Dedicated incoming webhook for the alerts channel. NOT SLACK_WEBHOOK_URL (that
# channel carries SSO access approvals). Unset = no health alerts are sent.
SLACK_ALERTS_WEBHOOK_URL=
```

In `deploy/crontab.prod`, change the backup line to touch the heartbeat on success:

```
30 4 * * * cd $APP_DIR && ./deploy/backup.sh >> out/cron.log 2>&1 && touch out/.backup_ok
```

and append at the end of the file:

```

# Health alerts (needs the release that carries ./cm watchdog / health-digest).
# Watchdog: critical checks only, silent unless a check changes state. Read-only,
# so deliberately NOT under flock (it must never queue behind a pipeline run).
*/20 * * * * cd $APP_DIR && docker compose exec -T api ./cm watchdog >> out/cron.log 2>&1
# 07:05 daily health status message to Slack
5 7 * * * cd $APP_DIR && docker compose exec -T api ./cm health-digest >> out/cron.log 2>&1
```

In `deploy/crontab.prod.utc`, change the backup line to:

```
0 23 * * * cd $APP_DIR && ./deploy/backup.sh >> out/cron.log 2>&1 && touch out/.backup_ok
```

and append at the end of the file:

```

# Health alerts (needs the release that carries ./cm watchdog / health-digest).
# Read-only, deliberately NOT under flock.
*/20 * * * * cd $APP_DIR && docker compose exec -T api ./cm watchdog >> out/cron.log 2>&1
# 07:05 IST daily health status message = 01:35 UTC
35 1 * * * cd $APP_DIR && docker compose exec -T api ./cm health-digest >> out/cron.log 2>&1
```

Append this section to the end of `deploy/README-prod.md`:

```markdown

## Health alerts (Slack)

Design: `docs/superpowers/specs/2026-10-05-slack-health-alerts-design.md`. Everything
ships in the image; the VM needs these one-time manual edits, in this order:

1. `.env`: set the new `RELEASE_TAG` and add `SLACK_ALERTS_WEBHOOK_URL=<incoming webhook
   for the alerts channel>` (NOT the SSO approvals webhook).
2. `make pull-prod` (the `migrate` service creates `job_runs`, `health_state`,
   `resource_samples` before `api` starts).
3. AFTER step 2 (a cron line added earlier fails against the old image): add the
   `*/20 ... ./cm watchdog` and `07:05 IST ... ./cm health-digest` lines from
   `crontab.prod` / `crontab.prod.utc` (UTC box: digest is `35 1 * * *`), and append
   `&& touch out/.backup_ok` to the backup line.
4. Prove the webhook: `docker compose exec api ./cm watchdog --test-message`.
5. Optional: copy the `health:` block from `community/config/registry.yaml` into the
   VM's own `registry.yaml` to tune thresholds (defaults apply without it).

Useful: `./cm watchdog --dry-run` / `./cm health-digest --dry-run` print what would be
sent without posting or saving. The watchdog is silent when everything is healthy.
If you roll back to an older `RELEASE_TAG`, comment out the two health cron lines: the
old image has no `watchdog` command and the failure would only appear in `out/cron.log`.
```

In `CLAUDE.md`, directly after the "Run:" bullet (the one ending ``(deps live in `.venv/`).``), add a bullet:

```
- Health alerts to Slack: `./cm watchdog` (cron */20, critical only) · `./cm health-digest`
  (cron 07:05 IST) — spec `docs/superpowers/specs/2026-10-05-slack-health-alerts-design.md`;
  needs `SLACK_ALERTS_WEBHOOK_URL` (separate channel from the SSO-approvals webhook).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `"$CM_PYTHON" -m pytest tests/test_health_config.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Confirm the YAML and the crontabs are well-formed**

Run: `"$CM_PYTHON" -c "import yaml,sys; d=yaml.safe_load(open('community/config/registry.yaml')); print(sorted(d['health']))"`
Expected: prints the health keys without error.
Run: `grep -n "watchdog\|health-digest\|backup_ok" deploy/crontab.prod deploy/crontab.prod.utc`
Expected: each file shows the two new cron lines and the touched backup line.

- [ ] **Step 6: Commit (only if the user has asked you to commit)**

```bash
git add community/config/registry.yaml community/config/env.example deploy/crontab.prod deploy/crontab.prod.utc deploy/README-prod.md CLAUDE.md tests/test_health_config.py
git commit -m "Health alerts: registry block, env var, cron lines, runbook" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 15: End-to-end verification and calibration (no new code unless a check below fails)

**Files:**
- Modify only if a verification below shows a mismatch: `community/health/config.py` (`DEFAULTS`), with a matching test.

- [ ] **Step 1: Whole test suite**

Run: `"$CM_PYTHON" -m pytest -q`
Expected: all tests pass, including the pre-existing `tests/test_extra_sources.py` and `tests/test_social_recommendations.py`.

- [ ] **Step 2: `./cm doctor` before/after parity**

Run: `./cm doctor` and compare with the baseline taken in Prerequisites.
Expected: identical PASS/FAIL/SKIP lines (this work does not touch doctor).

- [ ] **Step 3: Pipeline behaviour unchanged, ledger populated**

Run: `./cm run-local --skip-scrape --skip-enrich; echo "exit=$?"`
Expected: same stage log lines as before, `exit=0`.
Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT job,status,failed_stages,stats FROM job_runs ORDER BY id DESC LIMIT 3"`
Expected: a `run-local` row, `ok` or `degraded`, with `stats` like `{"seconds": 12.3}`.
Run a second `./cm run-local` while the first is still going (two terminals): the second prints "another pipeline run is active", exits 0, and a `skipped_locked` row appears.

- [ ] **Step 4: Dry-runs are read-only**

Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT (SELECT count(*) FROM health_state) hs, (SELECT count(*) FROM resource_samples) rs"` and note the numbers.
Run: `./cm watchdog --dry-run` and `./cm health-digest --dry-run --no-live`.
Run the count query again.
Expected: both counts unchanged; no Slack post (local `MODE` is not `prod`, and `--dry-run` never sends).

- [ ] **Step 5: Real source names and weekly-roundup date semantics**

Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT DISTINCT source FROM pipeline_state WHERE stage='ingest' ORDER BY 1"`
Compare with `DEFAULTS["sources"]["map"]` values (`twitter, reddit, youtube, github, community_forum, app_review, instagram, linkedin`). If a collector writes a different `pipeline_state.source`, fix the map in `config.py` (and add an assertion to `tests/test_health_config.py`).
Run: `docker compose exec -T postgres psql -U community -d nubra_community -c "SELECT period, date, created_at FROM roundups ORDER BY created_at DESC LIMIT 6"`
Confirm a `weekly` row's `date` is the day the Saturday job runs (the check looks for `date = today (IST)` on Saturdays after 11:00). If the weekly date is a different convention (for example the week start), change the query in `checks_data.check_freshness` and its test.

- [ ] **Step 6: Calibrate the enrichment backlog threshold**

Run the backlog query from `checks_data._BACKLOG_SQL` against restored prod data if you have a dump (`make restore-local DUMP=...`); otherwise against the dev DB.
Expected: a typical value well below 200. If the normal backlog is higher, raise `enrichment_backlog_warn` in `DEFAULTS` and the registry block, and note the measured value in the registry comment.

- [ ] **Step 7: Prove Slack delivery to a THROWAWAY channel only**

Create a throwaway incoming webhook (never the production approvals webhook). Then:

```bash
MODE=prod SLACK_ALERTS_WEBHOOK_URL=<throwaway-webhook-url> ./cm watchdog --test-message
MODE=prod SLACK_ALERTS_WEBHOOK_URL=<throwaway-webhook-url> ./cm health-digest --no-live
```

Expected: `{"test_message": "sent"}`, and the digest message appears in the throwaway channel: plain text, emoji-free, problems first. (Local DBs restored from prod must never be pointed at the production webhooks.)

- [ ] **Step 8: Alert lifecycle on the dev DB**

With `MODE=prod` and the throwaway webhook, force a critical (for example `UPDATE job_runs SET status='running', finished_at=NULL, started_at=now()-interval '5 hours' WHERE id=(SELECT max(id) FROM job_runs WHERE job='run-local')` makes `job_slow:run-local` critical) and run `./cm watchdog` three times, 20 s apart.
Expected: one `[CRITICAL] job_slow:run-local ...` message on the first run and none on the next two. Then restore the row (`UPDATE job_runs SET status='ok', finished_at=now() WHERE id=...`) and run the watchdog twice: a single `[RESOLVED] job_slow:run-local` appears after the second clean run.

- [ ] **Step 9: Review the diff**

Run: `git status --short` and `git diff --stat`
Expected: only the files listed in "File Structure" (plus the spec and this plan). No other file touched. `git diff runner.py community/dispatch/slack.py` shows only the changes described in Tasks 4, 7, 12 and 13.

- [ ] **Step 10: Report**

Write up for the user: what was verified, the calibration results, anything that differs from the spec, and the release sequence (push image, update `.env`, `make pull-prod`, then the cron lines, then `--test-message`). Mention that the first morning digest will show `partitions:*` as warnings until the partition job exists, and that critical starts 10 days before the cliff.

---

## Execution amendments (2026-10-05, made while executing and after the final review)

The plan's code was executed as written, then changed in these places. The spec was updated to match.

1. **Digest at 08:05 IST (02:35 UTC), not 07:05.** The freshness deadlines (daily roundup 07:45, topics 08:00) fall after 07:05, so those checks could never run then.
2. **Freshness:** weekly roundup = the most recent Saturday's row, judged from Saturday 11:00 IST through Monday; topics = any `topic_daily` row since yesterday (UTC date). Both pinned by tests in `test_health_checks_data.py`.
3. **`credits:x` is symptom-based.** The plan read a 402 from `pipeline_state.last_error`, which nothing ever writes (`ingest` degrades every X failure to a note and stamps `last_success_at`). It now fires when no new twitter item arrived for `credits.x_stalled_hours` (12) while the scraper ran in the last 3 h.
4. **Abandoned `running` rows** (process killed by OOM, restart or release) are marked failed by the next pipeline run (`ledger.reap_pipeline_runs`, called after the lock is won; `stage:*` jobs reap only their own rows older than 60 min). `job_slow` reports "died without finishing" when the pipeline lock is free and "still running" when it is held (`ledger.pipeline_lock_held`).
5. **`slack.send` scrubs URLs** from error strings: httpx put the webhook secret in the exception text, which the commands print into `out/cron.log`.
6. **Resource sampling failures no longer stop the watchdog**, and the Anthropic probe uses `timeout=15, max_retries=0`; a transient probe error while the key check is critical keeps it critical instead of counting toward a resolve.
7. **Deferred minors (not fixed):** `skipped (no alerts webhook)` counts as delivered; weekly jobs resolve after the 48 h lookback and `job_failed:stage:*` cannot fire; `stage:*` rows can excuse a missed slot as "lock holders"; disk ETA can go critical on one large step with short history; no warn/critical hysteresis; `_db_recovered` ignores a failed post; the enrichment-backlog SQL is not bounded on `item_enrichment` partitions.
