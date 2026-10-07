# Slack health alerts: design spec

Date: 2026-10-05 · Branch: jatin/beacon-updates · Status: DRAFT for review (nothing implemented)

## 1. Goal

Know whether Beacon is working without looking at it. Slack tells us, in two ways:

1. **Morning status message** (daily, about 08:05 IST): one message that says either "all
   healthy" or lists what is wrong. It doubles as a heartbeat: if it does not arrive, something is
   wrong with the box, cron or Slack.
2. **Immediate critical alerts**: a watchdog runs every 20 minutes and posts only when a critical
   check changes state (broke, still broken reminder, recovered).

Covers: daily/hourly jobs, scrapers, LLM calls, data freshness, resources (disk, memory, DB size),
and the month-partition cliff (section 6, check P1).

Success criteria:
- A cron run that never happens, a stage that keeps failing, a dead API key, exhausted X/Apify
  credits, a stale backup, a filling disk and missing DB partitions each produce a Slack message
  within about 20 minutes (critical) or by the next morning message (warning).
- No message storms: one alert per incident, a reminder every 6 hours, one "recovered".
- Nothing that works today changes behaviour (section 9).

## 2. Constraints that shape the design

- **Delivery is image-only.** Release flow is `make push-prod` then, on the VM, edit `RELEASE_TAG`
  in `.env` and `make pull-prod`. The image carries only `cm`, `runner.py`, `community/`,
  `migrations/`, `scripts/`, `data/` (Dockerfile.api). `deploy/`, `docker-compose.yml`, the crontab
  and `.env` are NOT updated by a release. So all logic lives in the image; the VM needs a few
  one-time manual edits (section 10).
- **`registry.yaml` is bind-mounted from the VM** (docker-compose.yml:80) and shadows the image's
  copy. New `health:` settings must therefore have in-code defaults; the VM file is only edited to
  tune.
- **The existing `SLACK_WEBHOOK_URL` channel carries SSO access approvals** (Approve/Reject
  buttons, `read_api.py:1646`). Health alerts must not land there by default. They use a separate
  `SLACK_ALERTS_WEBHOOK_URL`; there is no automatic fallback to the approvals webhook (a registry
  switch `health.fallback_to_default_webhook`, default false, exists for those who want it).
- **Locked decisions respected:** emoji-free system chrome (messages use plain text tags such as
  `[CRITICAL]`), prod-only sending (the existing `MODE=prod` gate in `slack.send`), one codebase.
- `delivery.slack_digests: off` gates only the roundup/heads-up call sites in
  `dispatch/local.py`; health alerts call the sender directly and are not affected by it.
- **Retention:** the 180-day purge job does not exist yet (backlog P1). The three new tables are
  small; they must be included when that job is written (noted in the migration comment).

## 3. Architecture

```
cron (VM, manual one-time)           image (ships with release)
  */20  ./cm watchdog   ----------->  community/health/
  08:05 ./cm health-digest ---------    checks.py   check functions -> Result(key, level, detail)
                                        state.py    transition logic over health_state
                                        resources.py  statvfs, /proc, pg sizes -> resource_samples
                                        schedule.py expected job slots vs job_runs (pure, testable)
                                        digest.py   renders the morning message
                                        notify.py   Slack via dispatch/slack.py (alerts webhook)
  runner.py: _with_pipeline_lock + stage record every job into job_runs
  migrations/0023_health_monitoring.sql: job_runs, health_state, resource_samples
```

Principles: additive; read-only against pipeline data; never takes the pipeline lock; every
failure inside health code is contained (a broken check shows as a warning, never kills the
watchdog, never affects a pipeline run).

## 4. Data model (migration 0023, create-table only)

- `job_runs(id, job text, started_at, finished_at, status, failed_stages text[], stats jsonb, error text)`
  status in `running | ok | degraded | failed | skipped_locked`. Index `(job, started_at desc)`.
- `health_state(check_key text PK, level text, detail text, since, last_seen, last_alerted_at, consecutive_ok int)`
  level in `ok | warn | crit`. Holds alert dedupe state and the watchdog heartbeat row.
- `resource_samples(ts, metric text, value double precision)` index `(metric, ts)`. Metrics:
  `disk_used_pct, disk_free_gb, mem_available_pct, swap_used_pct, load_per_core, db_size_gb,
  cron_log_mb, api_start_epoch, pg_start_epoch`.

No existing table is altered. `./cm migrate --dry-run` previews it.

## 5. Recording job outcomes (the one live-path change)

Today `run_local` stage failures are only logged (`runner.py:150`), and a run that finds the lock
held exits 0 with no record. Change points, all in `runner.py`:

- `_with_pipeline_lock(label, fn)` records: `skipped_locked` when the lock is busy; otherwise a
  `running` row at start, updated to `ok`, `degraded` (any returned stage stats contain `"error"`;
  failed stage names stored) or `failed` (exception). `_run_local_inner` returns `all_stats`
  (today it returns None); `run_morning_build` already returns it.
- The `stage` command (used by the Saturday weekly line) records `stage:<name>` the same way.

Safety rule (same as `llm/trace.py:record`): every recording call is wrapped so a DB problem is
logged and swallowed. Exit codes, lock behaviour and stage isolation are unchanged. A test
asserts a pipeline run still succeeds when the ledger write raises.

## 6. Checks

Severity: **crit** posts to Slack immediately (watchdog). **warn** appears in the morning message
only. Thresholds live in a new `health:` block in `registry.yaml` with in-code defaults.

### Critical (watchdog, every 20 min)

| Key | Condition |
|---|---|
| `job_overdue:<job>` | A scheduled slot plus grace has passed with no `ok`/`degraded` run started in it. Schedule declared in `health.jobs` (IST), mirroring the crontab: `run-local` hourly 07:00-23:00 and 00:00 (grace 60 min, crit after 3 missed slots), `morning-build` 06:00 (grace 90 min), `source instagram` 02:00 (grace 150 min), `stage:compose` and `stage:dispatch` Saturday 10:00. A `skipped_locked` run satisfies a slot only if another job's row legitimately holds the lock then (the 07:00 hourly skipping behind the morning build is expected). |
| `stage_failing:<stage>` | The same stage failed in the last 3 finished `run-local` runs. |
| `anthropic_key` | Free `count_tokens` probe fails with an auth/credit error. Re-probed at most hourly, every run while failing (to detect recovery). |
| `credits:x`, `credits:apify` | X: no new twitter item for 12 h while the scraper ran in the last 3 h (ingest degrades every X failure, 402 included, to a note, so exhaustion can only be seen by its symptom; no paid probe in the watchdog). Apify: free `/users/me/limits` shows usage at cap. |
| `partitions` (P1) | Latest partition upper bound of `social_items`, `item_enrichment`, `item_embeddings` is under 10 days away (warn under 35). Partitions exist only through 2026-10-31 and no partition job exists; inserts fail from 2026-11-01. This is the first check expected to fire. |
| `disk` | Used >= 90%, or projected full in under 7 days (linear fit over the last 7 days of samples; needs 24h+ of history). |
| `memory` | Available < 10% for 3 consecutive samples (the 02:30 IST whisper run spikes by design; one sample never alerts). |
| `crash_loop` | api or Postgres start time changed 2+ times within an hour. A single restart (every release) is only a morning-message note. |
| `backup` | `out/.backup_ok` exists and is older than 30 hours. If the file does not exist: warn only (until the one-time cron edit is made). |
| `db_unreachable` | Watchdog cannot connect to Postgres: posts directly, bypassing the DB-backed state. |

### Warning (morning message)

- Source stale: newest `ingested_at` per source older than its allowance (hourly sources 10h to
  cover the overnight gap; daily/nightly sources 30h; reddit follows `fetch_every_hours`).
- `source_health()` states `error` / `needs_key` / `enabled_not_run`, plus the existing live probes.
- Any failed stage in the last 24h. (A `running` job past its `max_run_min` is critical `job_slow`: "died without finishing" when the pipeline lock is free, "still running" when it is held. The next pipeline run marks orphaned `running` rows failed.)
- Enrichment backlog: items ingested more than 2h ago with no `item_enrichment` row (7-day window).
- LLM: no `llm_usage` rows in 24h; yesterday's spend above 3x the trailing 7-day median (floor
  USD 1); rows with NULL `cost_usd` (model missing from the price table). `llm_usage` only records
  calls that returned, so failures show up as absence plus failed stages.
- Freshness: no `topic_daily` rows since yesterday (UTC date) after 08:00 IST; no daily `roundups` row
  for today after 07:45 IST; the most recent Saturday's weekly roundup missing (judged from Saturday
  11:00 IST through Monday, because the digest runs at 08:05 IST, before the Saturday 10:00 compose).
- Resources: disk >= 80% or ETA under 21 days; memory < 20%; swap heavily used; load per core > 2
  sustained; `out/cron.log` over 500 MB; DB size and top 5 tables by size; any restart noted.
- Watchdog heartbeat older than 2h (the watchdog itself stopped).
- Muted checks (`health.muted`, default `[reddit]`, parked per commit 9f3134e) show as one
  "muted (known broken)" line and never alert.

## 7. Alert behaviour and messages

- ok to crit: post `[CRITICAL] <check>: <detail>. Since <time>. <one-line hint>`.
- Still crit: reminder every 6 hours (`health.remind_hours`).
- crit to ok: post `[RESOLVED] <check> after <duration>`, only after 2 consecutive ok evaluations
  (flap guard).
- warn never posts on its own.
- The watchdog prints nothing when everything is fine, so the 72 runs a day add no lines to
  `out/cron.log`.
- Morning message: first line `Beacon health: N checks, X critical, Y warnings, Z muted`, then
  Critical, Warnings, Jobs (each job: last status and age), Sources, LLM, Resources, Freshness.
  Problems first. Plain text, no emoji.

## 8. Resource collection (container-visible only, no Docker socket)

- Disk: `os.statvfs` on the `/app/out` bind mount (the host's `./out`, so the host filesystem).
- Memory/load: `/proc/meminfo`, `/proc/loadavg` with `os.cpu_count()` (compose sets no limits, so
  these are host values).
- Postgres: `pg_database_size`, `pg_total_relation_size` for the largest tables,
  `pg_postmaster_start_time()`.
- API restarts: change in the process start time of PID 1 between samples.
- `out/cron.log` size via `os.stat`; backup heartbeat via mtime of `out/.backup_ok`.
- Known limit: if Docker's data root (Postgres volume, container logs) is on a different
  filesystem from `./out`, its usage is not seen. Verify with `df -h` on the VM (open item).

## 9. Not breaking what works

- New files only, plus small backward-compatible edits: `runner.py` (section 5), `slack.py`
  (optional `webhook_env` argument, default behaviour unchanged), `registry.yaml` (new block,
  read with defaults), `env.example` and the crontab/README docs.
- Watchdog/digest are read-only on pipeline data, take no pipeline lock, use no `flock`, run each
  query with a 5s statement timeout, and bound total runtime.
- Verification before calling it done: `./cm doctor` before and after; existing tests plus new
  ones (state machine, schedule/overdue with injected clock, each threshold with fake rows,
  ledger-failure-does-not-break-run); local `./cm run-local --skip-scrape --skip-enrich` shows
  `job_runs` rows with unchanged exit codes; `./cm watchdog --dry-run` and `./cm health-digest
  --dry-run` against the local DB; after deploy, `./cm watchdog --test-message`.

## 10. Rollout (manual steps on the VM)

1. Dev machine: new `RELEASE_TAG`, `make push-prod`.
2. VM: in `.env` set the new `RELEASE_TAG` and add `SLACK_ALERTS_WEBHOOK_URL`; `make pull-prod`
   (the `migrate` service applies 0023 before `api` starts).
3. AFTER step 2, add cron lines (a line added earlier fails against the old image):
   - IST crontab: `*/20 * * * * cd $APP_DIR && docker compose exec -T api ./cm watchdog >> out/cron.log 2>&1`
     and `5 8 * * * cd $APP_DIR && docker compose exec -T api ./cm health-digest >> out/cron.log 2>&1`
   - UTC crontab (current VM): watchdog line identical; digest `35 2 * * * ...` (08:05 IST).
   - Backup line: append `&& touch out/.backup_ok` after `./deploy/backup.sh >> out/cron.log 2>&1`.
4. Run `docker compose exec api ./cm watchdog --test-message`; confirm it lands in the alerts channel.
5. Optional: copy the `health:` block into the VM's `registry.yaml` to tune.

Rollback: set the older `RELEASE_TAG`. The new tables stay (harmless). The old image has no
`watchdog` command, so the cron lines then fail silently into `cron.log` and alerting is off:
comment out the two cron lines when rolling back.

## 11. Out of scope

- Trimming `out/cron.log` (user decision 2026-10-05; only a warning at 500 MB).
- Docker-socket checks (exact OOMKilled flags, `docker system df`), `backups/` directory size.
- An external dead-man's switch for "whole VM or cron daemon is dead" (both watchdog and digest
  would be silent). Possible follow-up (for example Healthchecks.io).
- Building the rolling partition job and 180-day purge (backlog P1). This spec only alerts on the
  partition cliff; the job itself is separate work and is time-critical (see check `partitions`).

## 12. Open items to confirm during review

1. `health.muted` defaults to reddit. Correct?
2. `health.jobs` duplicates the crontab schedule and can drift from it; accepted trade-off since
   the crontab is not visible inside the container.
3. `df -h` on the VM: is Docker's data root on the same filesystem as the app directory?
4. Critical vs warning split in section 6 is my proposal; move items as needed.
5. Alerts webhook: separate channel assumed (no fallback to the SSO approvals channel).
