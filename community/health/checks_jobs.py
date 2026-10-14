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
from community.config.settings import settings
from community.health import ledger, schedule, state
from community.health.model import CRIT, OK, WARN, Result, owns

_FINISHED = ("ok", "degraded", "failed")


def _ist(ts: datetime) -> str:
    return ts.astimezone(IST).strftime("%d %b %H:%M")


def _expected_slots(jcfg: dict) -> str:
    """"01:00 IST = 19:30 UTC": a UTC box's crontab must be written in UTC (IST = UTC+5:30), and a line copied
    from the IST version fires at the wrong hour. Omitted for jobs with too many slots to read."""
    hours, minute = jcfg["hours"], jcfg.get("minute", 0)
    if len(hours) > 4:
        return ""
    ist = ", ".join(f"{h:02d}:{minute:02d}" for h in hours)
    utc = ", ".join("{:02d}:{:02d}".format(*divmod((h * 60 + minute - 330) % 1440, 60)) for h in hours)
    return f"expected {ist} IST = {utc} UTC"


def _overdue(job: str, jcfg: dict, runs: list, now: datetime, epoch: datetime, cfg: dict) -> Result:
    key = f"job_overdue:{job}"
    missed = schedule.trailing_missed(job, jcfg, runs, now, epoch=epoch,
                                      exempt_min=cfg["lock_exempt_minutes"])
    if not missed:
        return Result(key, OK, "on schedule")
    level = CRIT if len(missed) >= jcfg["crit_after_missed"] else WARN
    return Result(key, level,
                  f"{len(missed)} scheduled run(s) did not start, since {_ist(missed[0])} IST",
                  "check crontab -l" + (f" ({_expected_slots(jcfg)}; on a UTC box write the line in UTC)"
                                        if _expected_slots(jcfg) else "")
                  + ", docker compose ps and out/cron.log; a stuck run can also hold the lock")


def _slow(job: str, jcfg: dict, rows: list[dict], now: datetime) -> Result:
    key = f"job_slow:{job}"
    limit = jcfg["max_run_min"]
    over = [r for r in rows if r["job"] == job and r["status"] == "running"
            and now - r["started_at"] > timedelta(minutes=limit)]
    if not over:
        return Result(key, OK, "no overlong run")
    mins = int((now - over[0]["started_at"]).total_seconds() / 60)
    started = f"started {_ist(over[0]['started_at'])} IST"
    # stage:* jobs take no pipeline lock; for the others a FREE lock means the process
    # is gone (killed by an OOM, a restart or a release) and left its row behind
    held = None if job.startswith("stage:") else ledger.pipeline_lock_held()
    if held is False:
        return Result(key, CRIT, f"{started} and died without finishing (the pipeline lock is free)",
                      "the process was probably killed (OOM, restart or release): check out/cron.log and "
                      "docker compose logs api; the next run clears this")
    return Result(key, CRIT, f"{started} and still running after {mins} min (limit {limit})",
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
    sources = settings.registry.get("sources", {})
    for job, jcfg in cfg["jobs"].items():
        # opt-in jobs (a cadence: nightly source) are expected only while their source is enabled ...
        enabled_by = jcfg.get("enabled_by")
        if enabled_by and not (sources.get(enabled_by) or {}).get("enabled", False):
            continue
        job_epoch = epoch
        if jcfg.get("since_first_run"):
            # ... and only from the first time they ran: enabling the source mid-day (or releasing the
            # image before the cron line exists) must not count the slots already behind us as missed
            first = ledger.first_run_at(job)
            if first is None:
                results.append(Result(f"job_overdue:{job}", OK, "enabled; waiting for its first run"))
                results.append(_slow(job, jcfg, rows, now))
                results.append(_failed(job, rows, cfg["job_failing_runs"]))
                continue
            job_epoch = max(epoch, first)
        results.append(_overdue(job, jcfg, runs, now, job_epoch, cfg))
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


@owns("digest_stale")
def check_digest_stale(cfg: dict, now: datetime) -> list[Result]:
    """The watchdog watches the daily digest: a silently dead 08:05 cron would otherwise
    only be noticed by a person missing the message. digest_heartbeat is written by every
    successful `./cm health-digest` run."""
    limit = cfg["digest_stale_hours"]
    hint = "check the health-digest cron line (crontab -l) and the cron log for errors"
    row = cfg.get("_prev", {}).get("digest_heartbeat")
    if row is None or row.last_seen is None:
        epoch = state.get_epoch(now, create=not cfg.get("_dry_run"))
        waited_h = (now - epoch).total_seconds() / 3600
        if waited_h > limit:
            return [Result("digest_stale", CRIT,
                           f"the daily health digest has never run (monitoring started {waited_h:.0f} h ago)",
                           hint)]
        return [Result("digest_stale", OK, "waiting for the first daily digest")]
    age_h = (now - row.last_seen).total_seconds() / 3600
    if age_h > limit:
        return [Result("digest_stale", CRIT,
                       f"the daily health digest last ran {age_h:.0f} h ago (expected every 24 h)", hint)]
    return [Result("digest_stale", OK, f"last digest {age_h:.0f} h ago")]
