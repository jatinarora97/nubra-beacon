"""Read-only data-staleness report for the two social sources (Twitter and Reddit).

Answers "how fresh is what is actually in the database, and why": when the newest row ARRIVED (ingested_at)
versus how old the newest row IS (created_at, source time), where the rows come from (CSV backfill vs live X
API; old scraper vs Apify for Reddit), which days had no arrivals, how old content is when it arrives, which
watched subreddits are silent, and how far the downstream stages (enrichment, conversations, opportunities,
topics) have kept up. Nothing here writes. Run it on the box:

    docker compose exec -T api python scripts/data_staleness.py            # 30-day picture
    docker compose exec -T api python scripts/data_staleness.py --days 14 --json
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from community.config.log import IST
from community.config.settings import settings
from community.health import config as health_config
from community.health.checks_data import _PARTITION_SQL
from community.store import db

SOURCES = ("twitter", "reddit")
SOURCE_STALE_HOURS = 48          # arrivals can be fresh while the CONTENT is old (e.g. a CSV re-import)

# Where a row came from. Twitter: the one-off CSV backfill vs the capped live API fetch. Reddit: `via`.
_CHANNEL = """CASE WHEN source = 'twitter' THEN
                   CASE WHEN raw->>'backfill' IS NOT NULL THEN 'csv_backfill'
                        WHEN raw->>'live' = 'true' THEN 'live_api' ELSE 'other' END
              ELSE COALESCE(raw->>'via', '(none)') END"""

_SUMMARY = """
SELECT source, count(*) AS total,
       count(*) FILTER (WHERE ingested_at > now() - interval '1 day')   AS last_24h,
       count(*) FILTER (WHERE ingested_at > now() - interval '7 days')  AS last_7d,
       count(*) FILTER (WHERE ingested_at > now() - interval '30 days') AS last_30d,
       max(ingested_at) AS newest_ingested, min(ingested_at) AS oldest_ingested,
       max(created_at)  AS newest_created,  min(created_at)  AS oldest_created
FROM social_items WHERE source = ANY(%s) GROUP BY source
"""
_CHANNELS = f"""
SELECT source, {_CHANNEL} AS channel, count(*) AS rows,
       min(ingested_at) AS first_ingested, max(ingested_at) AS last_ingested, max(created_at) AS newest_created
FROM social_items WHERE source = ANY(%s) GROUP BY 1, 2 ORDER BY 1, last_ingested DESC
"""
# IST is a fixed +05:30 (no DST): an offset needs no tz database, which not every Postgres build ships
_DAILY = f"""
SELECT ((ingested_at AT TIME ZONE 'UTC') + interval '5 hours 30 minutes')::date AS day, source,
       {_CHANNEL} AS channel,
       source_type, count(*) AS n
FROM social_items WHERE source = ANY(%s) AND ingested_at > now() - (%s * interval '1 day')
GROUP BY 1, 2, 3, 4 ORDER BY 1
"""
_LAG = """
SELECT source, count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM (ingested_at - created_at)) / 3600) AS median_h,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM (ingested_at - created_at)) / 3600) AS p90_h
FROM social_items WHERE source = ANY(%s) AND ingested_at > now() - interval '7 days' GROUP BY source
"""
_REDDIT_SUBS = """
SELECT lower(raw->>'subreddit') AS sub, max(raw->>'subreddit') AS name, max(raw->>'category') AS category,
       count(*) FILTER (WHERE source_type = 'post')    AS posts,
       count(*) FILTER (WHERE source_type = 'comment') AS comments
FROM social_items WHERE source = 'reddit' AND ingested_at > now() - (%s * interval '1 day')
GROUP BY 1 ORDER BY posts DESC
"""
_REDDIT_NEWEST_POST = """
SELECT lower(raw->>'subreddit') AS sub, max(created_at) AS newest_post
FROM social_items WHERE source = 'reddit' AND source_type = 'post' GROUP BY 1
"""
_WATCHED_SUBS = "SELECT value, category FROM watch_sources WHERE kind = 'subreddit' AND active ORDER BY value"
_WATCHED_X = ("SELECT kind, count(*) AS n FROM watch_sources WHERE active AND kind IN "
              "('x_hashtag', 'x_handle', 'x_query') GROUP BY kind ORDER BY kind")
_PIPELINE = ("SELECT stage, source, watermark, last_success_at, last_error, last_error_at, items_last_run "
             "FROM pipeline_state ORDER BY stage, source")
_ENRICH = """
SELECT s.source, count(*) AS items, count(e.item_id) AS enriched,
       min(s.ingested_at) FILTER (WHERE e.item_id IS NULL AND s.ingested_at < now() - interval '2 hours')
           AS oldest_unenriched,
       max(e.enriched_at) AS newest_enriched
FROM social_items s
LEFT JOIN item_enrichment e ON e.item_id = s.item_id AND e.ingested_at = s.ingested_at
WHERE s.source = ANY(%s) AND s.ingested_at > now() - interval '7 days' AND s.duplicate_of IS NULL
GROUP BY s.source
"""
_CONVERSATIONS = """
SELECT source, count(*) AS threads, max(last_seen) AS newest_last_seen,
       count(*) FILTER (WHERE last_seen > now() - interval '7 days') AS active_7d
FROM conversations WHERE source = ANY(%s) GROUP BY source
"""
_OPPORTUNITIES = """
SELECT source, count(*) AS total, max(created_at) AS newest_created,
       count(*) FILTER (WHERE status = 'suggested') AS suggested,
       count(*) FILTER (WHERE created_at > now() - interval '7 days') AS last_7d
FROM opportunities WHERE source = ANY(%s) GROUP BY source
"""
_TOPICS = "SELECT max(day) AS newest_day FROM topic_daily"


# ── pure helpers (tested without a database) ──────────────────────────────

def fmt_ts(ts: datetime | None) -> str:
    return "never" if ts is None else ts.astimezone(IST).strftime("%Y-%m-%d %H:%M IST")


def fmt_age(ts: datetime | None, now: datetime) -> str:
    if ts is None:
        return "never"
    hours = (now - ts).total_seconds() / 3600
    if hours < 0:
        return "in the future"
    if hours < 1:
        return f"{hours * 60:.0f} min ago"
    if hours < 48:
        return f"{hours:.1f} h ago"
    return f"{hours / 24:.1f} d ago"


def age_hours(ts: datetime | None, now: datetime) -> float | None:
    return None if ts is None else (now - ts).total_seconds() / 3600


def freshness_limit_hours(source: str, cfg: dict, registry: dict | None = None) -> float:
    """How old the newest arrival may be before the source counts as stale: the health monitor's limit, with
    Reddit judged by the nightly Apify cadence once that collector is enabled."""
    reg = settings.registry if registry is None else registry
    limits = cfg["sources"]["max_age_hours"]
    if source == "reddit" and ((reg.get("sources", {}).get("reddit_apify")) or {}).get("enabled"):
        return float(limits.get("reddit_apify", limits["default"]))
    return float(limits.get(source, limits["default"]))


def verdict(source: str, row: dict | None, now: datetime, limit_h: float, live_last: datetime | None = None) -> dict:
    """One line per source: is it fresh, and if not, which kind of stale."""
    if not row or not row["total"]:
        return {"source": source, "status": "EMPTY", "why": "no rows at all"}
    arrival = age_hours(row["newest_ingested"], now)
    content = age_hours(row["newest_created"], now)
    reasons = []
    status = "ok"
    if arrival > limit_h:
        status = "STALE"
        reasons.append(f"newest arrival {fmt_age(row['newest_ingested'], now)} (allowed {limit_h:.0f} h)")
    elif content is not None and content > SOURCE_STALE_HOURS:
        status = "OLD-CONTENT"
        reasons.append(f"rows are still arriving but the newest one is {fmt_age(row['newest_created'], now)} "
                       f"(source time) - a re-import or a source that went quiet")
    if source == "twitter":
        if live_last is None:
            reasons.append("the live X API has never produced a row (all data is the CSV backfill)")
            status = "STALE" if status == "ok" else status
        else:
            live = age_hours(live_last, now)
            if live > limit_h:
                reasons.append(f"live X API last delivered {fmt_age(live_last, now)}")
                status = "STALE"
    return {"source": source, "status": status,
            "why": "; ".join(reasons) if reasons else
                   f"newest arrival {fmt_age(row['newest_ingested'], now)}, newest content {fmt_age(row['newest_created'], now)}"}


def fill_days(rows: list[dict], days: int, today: date) -> list[dict]:
    """One entry per IST day over the window, zeros included: a day with nothing is the finding."""
    by_day: dict[date, dict] = {}
    for r in rows:
        d = by_day.setdefault(r["day"], {"twitter_live": 0, "twitter_csv": 0, "twitter_other": 0,
                                         "reddit_posts": 0, "reddit_comments": 0})
        n = int(r["n"])
        if r["source"] == "twitter":
            key = {"live_api": "twitter_live", "csv_backfill": "twitter_csv"}.get(r["channel"], "twitter_other")
            d[key] += n
        elif r["source_type"] == "comment":
            d["reddit_comments"] += n
        else:
            d["reddit_posts"] += n
    out = []
    for i in range(days, -1, -1):
        day = today - timedelta(days=i)
        d = by_day.get(day, {"twitter_live": 0, "twitter_csv": 0, "twitter_other": 0,
                             "reddit_posts": 0, "reddit_comments": 0})
        out.append({"day": day, **d})
    return out


def silent_watched(watched: list[dict], subs: list[dict], newest: dict[str, datetime]) -> list[dict]:
    """Every watched subreddit with its window counts and its newest post ever; sorted silent-first."""
    seen = {s["sub"]: s for s in subs if s["sub"]}
    out = []
    for w in watched:
        key = w["value"].lower()
        s = seen.get(key)
        out.append({"sub": w["value"], "category": w["category"],
                    "posts": int(s["posts"]) if s else 0, "comments": int(s["comments"]) if s else 0,
                    "newest_post": newest.get(key)})
    out.sort(key=lambda r: (r["posts"] > 0, r["posts"], r["sub"].lower()))
    return out


# ── collection ────────────────────────────────────────────────────────────

def _safe(label: str, fn, errors: dict):
    """One failing query must not hide the rest of the picture."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        errors[label] = f"{type(e).__name__}: {str(e)[:160]}"
        return None


def collect(days: int = 30, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cfg = health_config.load()
    src = list(SOURCES)
    errors: dict[str, str] = {}
    q = lambda sql, params=None: db.query(sql, params)  # noqa: E731

    summary = {r["source"]: r for r in _safe("summary", lambda: q(_SUMMARY, (src,)), errors) or []}
    channels = _safe("channels", lambda: q(_CHANNELS, (src,)), errors) or []
    daily = _safe("daily", lambda: q(_DAILY, (src, days)), errors) or []
    lag = {r["source"]: r for r in _safe("lag", lambda: q(_LAG, (src,)), errors) or []}
    subs = _safe("subreddits", lambda: q(_REDDIT_SUBS, (days,)), errors) or []
    newest = {r["sub"]: r["newest_post"] for r in _safe("newest_posts", lambda: q(_REDDIT_NEWEST_POST), errors) or []
              if r["sub"]}
    watched = _safe("watched_subs", lambda: q(_WATCHED_SUBS), errors) or []
    watched_x = _safe("watched_x", lambda: q(_WATCHED_X), errors) or []
    pipeline = _safe("pipeline", lambda: q(_PIPELINE), errors) or []
    enrich = {r["source"]: r for r in _safe("enrichment", lambda: q(_ENRICH, (src,)), errors) or []}
    conv = {r["source"]: r for r in _safe("conversations", lambda: q(_CONVERSATIONS, (src,)), errors) or []}
    opp = {r["source"]: r for r in _safe("opportunities", lambda: q(_OPPORTUNITIES, (src,)), errors) or []}
    topics = _safe("topics", lambda: db.one(_TOPICS), errors)
    parts = _safe("partitions", lambda: q(_PARTITION_SQL, (cfg["partitions"]["tables"],)), errors) or []

    live_last = next((c["last_ingested"] for c in channels
                      if c["source"] == "twitter" and c["channel"] == "live_api"), None)
    verdicts = [verdict(s, summary.get(s), now, freshness_limit_hours(s, cfg), live_last if s == "twitter" else None)
                for s in src]
    return {"now": now, "days": days, "errors": errors, "summary": summary, "channels": channels,
            "verdicts": verdicts, "daily": fill_days(daily, days, now.astimezone(IST).date()), "lag": lag,
            "subreddits": silent_watched(watched, subs, newest), "other_subreddits": [
                s for s in subs if s["sub"] and s["sub"] not in {w["value"].lower() for w in watched}],
            "watched_x": watched_x, "pipeline": pipeline, "enrichment": enrich, "conversations": conv,
            "opportunities": opp, "topics_newest_day": (topics or {}).get("newest_day"), "partitions": parts}


# ── rendering ─────────────────────────────────────────────────────────────

def render(rep: dict) -> str:
    now = rep["now"]
    out: list[str] = []
    add = out.append
    add(f"DATA STALENESS REPORT  (generated {fmt_ts(now)}, window {rep['days']} days)")
    add("=" * 78)
    add("\n1. VERDICT")
    for v in rep["verdicts"]:
        add(f"  {v['source']:<8} {v['status']:<12} {v['why']}")

    add("\n2. ARRIVAL vs SOURCE TIME  (arrival = ingested_at, source time = created_at)")
    for s in SOURCES:
        r = rep["summary"].get(s)
        if not r:
            add(f"  {s}: no rows")
            continue
        add(f"  {s}: {r['total']:,} rows | last 24h {r['last_24h']:,} | 7d {r['last_7d']:,} | 30d {r['last_30d']:,}")
        add(f"      newest arrival  {fmt_ts(r['newest_ingested'])}  ({fmt_age(r['newest_ingested'], now)})")
        add(f"      newest content  {fmt_ts(r['newest_created'])}  ({fmt_age(r['newest_created'], now)})")
        add(f"      oldest arrival  {fmt_ts(r['oldest_ingested'])}   oldest content {fmt_ts(r['oldest_created'])}")
        lg = rep["lag"].get(s)
        if lg and lg["median_h"] is not None:
            add(f"      content age at arrival, last 7d: median {lg['median_h']:.1f} h, p90 {lg['p90_h']:.1f} h "
                f"({lg['n']:,} rows)")

    add("\n3. WHERE THE ROWS COME FROM")
    add(f"  {'source':<8} {'channel':<22} {'rows':>8}  {'first arrival':<20} {'last arrival':<20} newest content")
    for c in rep["channels"]:
        add(f"  {c['source']:<8} {c['channel']:<22} {c['rows']:>8,}  {fmt_ts(c['first_ingested']):<20} "
            f"{fmt_ts(c['last_ingested']):<20} {fmt_ts(c['newest_created'])}")

    add(f"\n4. ARRIVALS PER DAY, IST  (days with nothing are marked)")
    add(f"  {'day':<11} {'tw live':>8} {'tw csv':>8} {'rd posts':>9} {'rd comments':>12}")
    for d in rep["daily"]:
        none = "   <- nothing from either source" if not (d["twitter_live"] + d["twitter_csv"] + d["twitter_other"]
                                                         + d["reddit_posts"] + d["reddit_comments"]) else (
               "   <- no reddit" if not (d["reddit_posts"] + d["reddit_comments"]) else (
               "   <- no twitter" if not (d["twitter_live"] + d["twitter_csv"] + d["twitter_other"]) else ""))
        add(f"  {d['day']!s:<11} {d['twitter_live']:>8} {d['twitter_csv']:>8} {d['reddit_posts']:>9} "
            f"{d['reddit_comments']:>12}{none}")

    add(f"\n5. WATCHED SUBREDDITS  (silent first; window {rep['days']} days)")
    silent = [s for s in rep["subreddits"] if s["posts"] == 0]
    add(f"  {len(silent)} of {len(rep['subreddits'])} watched subreddits produced no posts in the window")
    add(f"  {'subreddit':<22} {'category':<15} {'posts':>6} {'comments':>9}  newest post ever")
    for s in rep["subreddits"]:
        add(f"  {s['sub']:<22} {str(s['category'] or ''):<15} {s['posts']:>6} {s['comments']:>9}  "
            f"{fmt_ts(s['newest_post'])}" + ("  (" + fmt_age(s['newest_post'], now) + ")" if s["newest_post"] else ""))
    others = rep["other_subreddits"]
    if others:
        add(f"  + {len(others)} unwatched subreddits arrived via keyword search "
            f"({sum(int(o['posts']) for o in others)} posts)")

    add("\n6. TWITTER WATCH LIST")
    add("  active in watch_sources: " + (", ".join(f"{w['kind']} {w['n']}" for w in rep["watched_x"]) or "none"))

    add("\n7. PIPELINE STATE  (stage/source: last success, last error)")
    for p in rep["pipeline"]:
        err = ""
        if p["last_error"]:
            err = f" | LAST ERROR {fmt_age(p['last_error_at'], now)}: {p['last_error'][:90]}"
        items = "" if p["items_last_run"] is None else f" | items last run {p['items_last_run']}"
        add(f"  {p['stage'] + '/' + (p['source'] or '-'):<28} success {fmt_age(p['last_success_at'], now):<16}"
            f"{items}{err}")

    add("\n8. DOWNSTREAM  (does the rest of the pipeline keep up with what arrives?)")
    for s in SOURCES:
        e, c, o = rep["enrichment"].get(s), rep["conversations"].get(s), rep["opportunities"].get(s)
        if e:
            pct = 100 * e["enriched"] / e["items"] if e["items"] else 0
            add(f"  {s}: last 7d {e['items']:,} canonical items, {e['enriched']:,} enriched ({pct:.0f}%), "
                f"oldest unenriched {fmt_age(e['oldest_unenriched'], now)}, newest enrichment "
                f"{fmt_age(e['newest_enriched'], now)}")
        else:
            add(f"  {s}: nothing arrived in the last 7 days to enrich")
        if c:
            add(f"      conversations {c['threads']:,} ({c['active_7d']:,} active 7d), newest activity "
                f"{fmt_age(c['newest_last_seen'], now)}")
        if o:
            add(f"      opportunities {o['total']:,} ({o['suggested']:,} suggested, {o['last_7d']:,} in 7d), newest "
                f"{fmt_age(o['newest_created'], now)}")
    add(f"  topic_daily newest day: {rep['topics_newest_day'] or 'never'}")

    add("\n9. HARD STOP AHEAD  (partitions: inserts fail once the last one ends)")
    for p in rep["partitions"]:
        ub = p["upper_bound"]
        left = "?" if ub is None else f"{(ub - now).total_seconds() / 86400:.0f} days"
        add(f"  {p['parent']:<18} last partition ends {fmt_ts(ub)}  -> {left} left")

    if rep["errors"]:
        add("\nQUERIES THAT FAILED (the rest of the report is still valid)")
        for k, v in rep["errors"].items():
            add(f"  {k}: {v}")
    return "\n".join(out)
