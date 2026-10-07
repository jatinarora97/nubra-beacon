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

from datetime import datetime, timedelta, timezone

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
    # compose/aggregate write UTC calendar dates (roundup.run: datetime.now(utc).date()).
    # topic_daily.day follows item created_at, and the digest runs 08:05 IST = 02:35 UTC,
    # so only 2.5 h of the new UTC day exist: judge topics over today AND yesterday.
    today = now.astimezone(timezone.utc).date()
    results: list[Result] = []
    if hour >= f["topics_after_ist"]:
        n = db.one("SELECT count(*) AS n FROM topic_daily WHERE day >= %s",
                   (today - timedelta(days=1),))["n"]
        results.append(Result("freshness:topics", OK if n else WARN,
                              f"{n} topic rows since yesterday" if n
                              else "no topic rollups for today or yesterday",
                              "" if n else "the aggregate stage may be failing: see out/cron.log"))
    if hour >= f["daily_roundup_after_ist"]:
        have = db.one("SELECT 1 AS x FROM roundups WHERE period = 'daily' AND date = %s", (today,))
        results.append(Result("freshness:daily_roundup", OK if have else WARN,
                              "today's daily roundup exists" if have else "today's daily roundup is missing"))
    # The weekly roundup is composed Saturday 10:00 IST, after the digest has run, so judge
    # the MOST RECENT Saturday's row from Saturday 11:00 IST through Monday's digest.
    days_since_sat = (ist_now.weekday() - 5) % 7
    if days_since_sat in (1, 2) or (days_since_sat == 0 and hour >= f["weekly_roundup_after_ist"]):
        last_sat = ist_now.date() - timedelta(days=days_since_sat)
        have = db.one("SELECT 1 AS x FROM roundups WHERE period = 'weekly' AND date = %s", (last_sat,))
        results.append(Result("freshness:weekly_roundup", OK if have else WARN,
                              f"the {last_sat:%d %b} weekly roundup exists" if have
                              else f"the {last_sat:%d %b} weekly roundup is missing"))
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
