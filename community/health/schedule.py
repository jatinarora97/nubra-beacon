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
