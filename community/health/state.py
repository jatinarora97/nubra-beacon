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
