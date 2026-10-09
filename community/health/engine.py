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

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from community.config.log import IST, get_logger
from community.config.settings import settings
from community.health import (checks_data, checks_jobs, checks_llm, config, digest, icons,
                              notify, resources, state)
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Decision, Row

log = get_logger("health.engine")

CRITICAL_CHECKS = [checks_jobs.check_jobs, checks_data.check_partitions,
                   checks_llm.check_anthropic_key, checks_llm.check_credits,
                   resources.check_resources, checks_jobs.check_digest_stale]
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
            f"{icons.CRITICAL} [CRITICAL] db_unreachable: the watchdog cannot connect to Postgres.\n"
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
        notify.post(f"{icons.OK} [RESOLVED] db_unreachable (Postgres is reachable again)",
                    _ALERT_SUBJECT, cfg)
        DB_DOWN_FLAG.unlink(missing_ok=True)
    return True


def run_watchdog(*, dry_run: bool = False, test_message: bool = False,
                 now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cfg = config.load()
    os.environ.setdefault("PGOPTIONS", "-c statement_timeout=20000")
    if test_message:
        status = notify.post(f"{icons.TEST} [TEST] Beacon watchdog test message. If you can read this, "
                             "critical alerts reach this channel.", "Beacon alert test", cfg, dry_run)
        return {"test_message": status}
    if not _db_up():
        return _db_down(cfg, now, dry_run)
    recovered = _db_recovered(cfg, dry_run)
    if not dry_run:
        try:
            resources.collect_and_record()
        except Exception:  # noqa: BLE001 — sampling must never stop alerts (DB trouble is when they matter)
            log.exception("resource sampling failed; running the checks anyway")
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


def run_digest(*, dry_run: bool = False, live: bool = True,
               now: datetime | None = None) -> dict:
    """Daily status message (cron 08:05 IST). Evaluates every check, saves no
    alert state (only its own heartbeat), and runs probes unconditionally."""
    now = now or datetime.now(timezone.utc)
    cfg = config.load()
    os.environ.setdefault("PGOPTIONS", "-c statement_timeout=20000")
    if not _db_up():
        status = notify.post(f"{icons.CRITICAL} [CRITICAL] health digest could not run: Postgres is unreachable.",
                             "Beacon health", cfg, dry_run)
        return {"db_unreachable": True, "posted": status}
    prev = state.load_states()
    cfg.update({"_prev": prev, "_force": True, "_dry_run": dry_run})
    results, _failed = run_checks(CRITICAL_CHECKS + DIGEST_ONLY_CHECKS, cfg, now)
    ctx = dict(digest.collect_context(cfg, now, live=live))  # copy: never mutate the caller's dict
    results = results + digest.live_results(ctx)
    snap_row = prev.get("digest_snapshot")
    ctx["changes"] = digest.diff_snapshot(
        digest.parse_snapshot(snap_row.detail) if snap_row else None, results)
    last = prev.get("digest_heartbeat")
    ctx["prev_digest"] = {"last_seen": last.last_seen, "detail": last.detail} if last else None
    text = digest.render(results, ctx, cfg, now)
    status = notify.post(text, f"{icons.DIGEST} Beacon health - {now.astimezone(IST):%d %b %Y}",
                         cfg, dry_run)
    crit = [r.key for r in results if r.level == CRIT]
    warn = [r.key for r in results if r.level == WARN]
    if not dry_run:
        state.save(Row("digest_heartbeat", OK,
                       f"posted={status}; critical={len(crit)}; warnings={len(warn)}",
                       now, now, None, 0))
        state.save(Row("digest_snapshot", OK, json.dumps(digest.snapshot(results), sort_keys=True),
                       now, now, None, 0))
    return {
        "checks": len(results),
        "critical": crit,
        "warnings": warn,
        "posted": status,
        "text": text if dry_run else None,
    }
