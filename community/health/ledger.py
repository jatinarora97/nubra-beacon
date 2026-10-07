# community/health/ledger.py
"""Job ledger — one job_runs row per cron invocation (spec §5).

Every writer here NEVER raises: a ledger problem must not fail, skip or slow a
pipeline run (same rule as community/llm/trace.py:record). The db module is
imported lazily so even an import problem cannot break the importing runner.
"""
from __future__ import annotations

from community.config.log import get_logger

log = get_logger("health.ledger")

_PIPELINE_LOCK_KEY = 0x6E756272  # keep in sync with runner._PIPELINE_LOCK_KEY


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


def reap_pipeline_runs() -> int:
    """Mark leftover 'running' rows (except stage:* jobs) as failed.

    Call ONLY while holding the pipeline lock: nobody else can be running then, so
    any such row belongs to a process that died before finishing (killed by an OOM,
    a container restart or a release). Without this an orphan stays 'running'
    forever and raises a false job_slow alert for the whole lookback window."""
    try:
        from community.store import db
        return db.execute(
            "UPDATE job_runs SET status = 'failed', finished_at = now(), "
            "error = 'abandoned: the process died before finishing (killed, OOM or restart)' "
            "WHERE status = 'running' AND job NOT LIKE 'stage:%'")
    except Exception as e:  # noqa: BLE001
        log.warning("job_runs reap failed (%s) — run unaffected", e)
        return 0


def reap_stale_stage(job: str, older_than_min: int = 60) -> int:
    """`stage:*` jobs take no lock, so only reap THIS stage's rows that are old
    enough that the process cannot still be working on them."""
    try:
        from community.store import db
        return db.execute(
            "UPDATE job_runs SET status = 'failed', finished_at = now(), "
            "error = 'abandoned: the process died before finishing (killed, OOM or restart)' "
            "WHERE status = 'running' AND job = %s "
            "AND started_at < now() - (%s * interval '1 minute')", (job, older_than_min))
    except Exception as e:  # noqa: BLE001
        log.warning("job_runs stage reap failed for %s (%s) — run unaffected", job, e)
        return 0


def pipeline_lock_held() -> bool | None:
    """True if some process holds the pipeline advisory lock right now, False if it is
    free, None if that cannot be determined."""
    try:
        from community.store import db
        row = db.one(
            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
            "AND classid = 0 AND objid = %s AND objsubid = 1) AS held", (_PIPELINE_LOCK_KEY,))
        return bool(row["held"])
    except Exception as e:  # noqa: BLE001
        log.warning("pipeline lock probe failed (%s)", e)
        return None


def recent_runs(hours: float) -> list[dict]:
    """Runs started in the last `hours`, oldest first. Used by checks (may raise)."""
    from community.store import db
    return db.query(
        "SELECT job, status, started_at, finished_at, failed_stages, error FROM job_runs "
        "WHERE started_at > now() - (%s * interval '1 hour') ORDER BY started_at",
        (hours,))
