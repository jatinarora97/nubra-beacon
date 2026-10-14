# community/health/digest.py
"""The morning status message: overall status and top actions first, then the detail.

Slack-only emoji from icons.py (user decision 2026-10-09; the plain text stays readable without
them). `collect_context` gathers the numbers that are not check results; `render` and the
helpers below are pure so they are easy to test.

Layout: Overall line, Top actions (max 3), Critical, Warnings, Changes since yesterday,
Jobs, Sources, LLM, Resources (with day-over-day trends), previous-digest footer.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from community.config.log import IST
from community.health import icons, resources
from community.health.model import CRIT, OK, RANK, WARN, Result

_PROBE_NAMES = ("twitter", "youtube", "github", "broker_communities", "app_reviews", "instagram",
                "reddit_apify")
_PROBE_OK = ("ok", "no_probe")

# What to fix first: lower index = more urgent (prefix match on the check key).
_PRIORITY = ("stage_failing:", "job_", "digest_stale", "stage_recent:", "credits:",
             "anthropic_key", "partitions:", "backup", "disk", "memory", "swap",
             "restart:", "source")
_RESOURCE_METRICS = ("disk_used_pct", "disk_free_gb", "mem_available_pct", "swap_used_pct",
                     "load_per_core", "db_size_gb", "cron_log_mb")
_MAX_LISTED = 8


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


def llm_summary(rows: list[dict], day: date) -> dict:
    """Yesterday's calls/cost plus the average daily cost of the (up to 7) days before it."""
    by_day = {r["d"]: r for r in rows}
    y = by_day.get(day)
    prior = [float(by_day[day - timedelta(days=i)]["cost"]) for i in range(1, 8)
             if (day - timedelta(days=i)) in by_day]
    return {"day": day,
            "calls": int(y["calls"]) if y else 0,
            "cost": float(y["cost"]) if y else 0.0,
            "avg7": sum(prior) / len(prior) if prior else None}


def nearest_previous(hist: list[tuple[datetime, float]], now: datetime,
                     hours: float = 24, tolerance_h: float = 3) -> float | None:
    """The sample closest to `hours` ago, if one exists within `tolerance_h` of that time."""
    target = now - timedelta(hours=hours)
    best: tuple[float, float] | None = None
    for ts, value in hist:
        distance = abs((ts - target).total_seconds())
        if distance <= tolerance_h * 3600 and (best is None or distance < best[0]):
            best = (distance, value)
    return best[1] if best else None


def collect_context(cfg: dict, now: datetime, live: bool = True) -> dict:
    from community.store import db
    ctx: dict = {}
    ctx["jobs"] = db.query(
        "SELECT DISTINCT ON (job) job, status, started_at, finished_at FROM job_runs "
        "WHERE status <> 'skipped_locked' ORDER BY job, started_at DESC")
    day = now.astimezone(IST).date() - timedelta(days=1)
    rows = db.query(
        "SELECT (ts AT TIME ZONE 'Asia/Kolkata')::date AS d, count(*) AS calls, "
        "coalesce(sum(cost_usd), 0) AS cost FROM llm_usage "
        "WHERE ts > now() - interval '10 days' GROUP BY 1 ORDER BY 1")
    ctx["llm"] = llm_summary(rows, day)
    latest: dict[str, float] = {}
    before: dict[str, float] = {}
    for metric in _RESOURCE_METRICS:
        hist = resources.history(metric, 26)
        if hist and (now - hist[-1][0]) <= timedelta(hours=3):
            latest[metric] = hist[-1][1]
            yesterday = nearest_previous(hist, now)
            if yesterday is not None:
                before[metric] = yesterday
    ctx["resources"] = latest
    ctx["resources_prev"] = before
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


def overall(results: list[Result]) -> str:
    if any(r.level == CRIT for r in results):
        return "CRITICAL"
    if any(r.level == WARN for r in results):
        return "DEGRADED"
    return "HEALTHY"


def _rank(key: str) -> int:
    for i, prefix in enumerate(_PRIORITY):
        if key.startswith(prefix):
            return i
    return len(_PRIORITY)


def top_actions(results: list[Result], limit: int = 3) -> list[Result]:
    """Criticals first, then warnings, each ordered by what is most urgent to fix."""
    crit = sorted((r for r in results if r.level == CRIT), key=lambda r: (_rank(r.key), r.key))
    warn = sorted((r for r in results if r.level == WARN), key=lambda r: (_rank(r.key), r.key))
    return (crit + warn)[:limit]


def snapshot(results: list[Result]) -> dict[str, str]:
    """Open issues only ({key: level}); stored after each digest to diff against the next."""
    return {r.key: r.level for r in results if r.level != OK}


def parse_snapshot(text: str | None) -> dict[str, str] | None:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def diff_snapshot(prev: dict[str, str] | None, results: list[Result]) -> dict | None:
    """What is new / resolved since the previous digest; None when there is nothing to compare."""
    if prev is None:
        return None
    cur = snapshot(results)
    worse = {k for k, lvl in cur.items() if k not in prev or RANK.get(lvl, 0) > RANK.get(prev[k], 0)}
    return {"new": sorted(f"{k} ({cur[k]})" for k in worse),
            "resolved": sorted(k for k in prev if k not in cur),
            "unchanged": sum(1 for k in cur if k in prev and k not in worse)}


def _ago(ts: datetime | None, now: datetime) -> str:
    if ts is None:
        return "never"
    hours = (now - ts).total_seconds() / 3600
    if hours < 1:
        return f"{max(round(hours * 60), 1)} min ago"  # round: 40 min is 39.999... after float division
    if hours < 48:
        return f"{hours:.0f} h ago"
    return f"{hours / 24:.0f} d ago"


def _pct_trend(cur: float, prev: float | None) -> str:
    if prev is None:
        return ""
    diff = cur - prev
    if abs(diff) < 1.0:
        return ", steady since yesterday"
    return f", {'up' if diff > 0 else 'down'} from {prev:.0f}% yesterday"


def _rel_trend(cur: float, prev: float | None) -> str:
    if not prev:
        return ""
    change = (cur - prev) / prev * 100
    if abs(change) < 1.0:
        return ", steady since yesterday"
    return f", {'up' if change > 0 else 'down'} {abs(change):.0f}% since yesterday"


def _resource_lines(r: dict, before: dict) -> list[str]:
    lines = []
    if "disk_used_pct" in r:
        free = f" ({r['disk_free_gb']:.0f} GB free)" if "disk_free_gb" in r else ""
        lines.append(f"- disk {r['disk_used_pct']:.0f}% used{free}"
                     f"{_pct_trend(r['disk_used_pct'], before.get('disk_used_pct'))}")
    if "mem_available_pct" in r:
        lines.append(f"- memory {r['mem_available_pct']:.0f}% available"
                     f"{_pct_trend(r['mem_available_pct'], before.get('mem_available_pct'))}")
    if "swap_used_pct" in r:
        lines.append(f"- swap {r['swap_used_pct']:.0f}% in use"
                     f"{_pct_trend(r['swap_used_pct'], before.get('swap_used_pct'))}")
    if "load_per_core" in r:
        lines.append(f"- load {r['load_per_core']:.1f} per core")
    if "db_size_gb" in r:
        lines.append(f"- database {r['db_size_gb']:.1f} GB"
                     f"{_rel_trend(r['db_size_gb'], before.get('db_size_gb'))}")
    if "cron_log_mb" in r:
        lines.append(f"- cron.log {r['cron_log_mb']:.0f} MB")
    return lines


def _listed(items: list[str]) -> str:
    shown = ", ".join(items[:_MAX_LISTED])
    return shown + (f" (+{len(items) - _MAX_LISTED} more)" if len(items) > _MAX_LISTED else "")


_STATUS_ICON = {"HEALTHY": icons.HEALTHY, "DEGRADED": icons.DEGRADED, "CRITICAL": icons.CRITICAL_STATUS}
_LEVEL_ICON = {OK: icons.OK, WARN: icons.WARNING, CRIT: icons.CRITICAL}
_JOB_ICON = {"ok": icons.OK, "degraded": icons.WARNING, "failed": icons.CRITICAL,
             "running": icons.RUNNING}


def _problem_block(title: str, rows: list[Result], icon: str) -> list[str]:
    if not rows:
        return []
    lines = [f"{icon} *{title}*"]
    for r in rows:
        lines.append(f"- {r.key}: {r.detail}")
        if r.hint:
            lines.append(f"    What to check: {r.hint}")
    return lines + [""]


def _top_actions_block(results: list[Result]) -> list[str]:
    actions = top_actions(results)
    if not actions:
        return []
    lines = [f"{icons.ACTIONS} *Top actions*"]
    for i, r in enumerate(actions, 1):
        lines.append(f"{i}. {r.key}: {r.detail}")
        if r.hint:
            lines.append(f"   What to check: {r.hint}")
    return lines + [""]


def _changes_block(changes: dict | None) -> list[str]:
    if changes is None:
        return []
    lines = [f"{icons.CHANGES} *Changes since yesterday*"]
    if not changes["new"] and not changes["resolved"]:
        lines.append(f"- No changes ({changes['unchanged']} open issues)")
    else:
        if changes["new"]:
            lines.append("- New: " + _listed(changes["new"]))
        if changes["resolved"]:
            lines.append("- Resolved: " + _listed(changes["resolved"]))
        lines.append(f"- Unchanged: {changes['unchanged']} open issues")
    return lines + [""]


def render(results: list[Result], ctx: dict, cfg: dict, now: datetime) -> str:
    crit = sorted((r for r in results if r.level == CRIT), key=lambda r: r.key)
    warn = sorted((r for r in results if r.level == WARN), key=lambda r: r.key)
    total = len(results)
    status = overall(results)
    head = (f"{_STATUS_ICON[status]} Overall: HEALTHY - all {total} checks healthy" if status == "HEALTHY"
            else f"{_STATUS_ICON[status]} Overall: {status} - {total} checks, "
                 f"{len(crit)} critical, {len(warn)} warnings")
    if cfg["muted"]:
        head += f" (muted, known broken: {', '.join(cfg['muted'])})"
    lines = [head, ""]
    lines += _top_actions_block(results)
    lines += _problem_block("Critical", crit, icons.CRITICAL)
    lines += _problem_block("Warnings", warn, icons.WARNING)
    lines += _changes_block(ctx.get("changes"))

    last = {j["job"]: j for j in ctx.get("jobs", [])}
    lines.append(f"{icons.JOBS} *Jobs*")
    for job in cfg["jobs"]:
        j = last.get(job)
        lines.append(f"- {_JOB_ICON.get(j['status'], icons.NONE)} {job}: {j['status']}, "
                     f"last run {_ago(j['started_at'], now)}" if j
                     else f"- {icons.NONE} {job}: no run recorded yet")
    lines.append("")

    by_key = {r.key: r for r in results}
    source_lines = []
    for name in cfg["sources"]["map"]:
        res = by_key.get(f"source:{name}")
        if res is None:
            continue
        bits = [res.detail]
        worst = res.level
        items = by_key.get(f"source_items:{name}")
        if items:
            bits.append(items.detail)
            worst = max((worst, items.level), key=RANK.get)
        probe = ctx.get("live", {}).get(name)
        if probe:
            bits.append(f"live probe {probe.get('live')}")
        source_lines.append(f"- {_LEVEL_ICON[worst]} {name}: {'; '.join(bits)}")
    if source_lines:
        lines += [f"{icons.SOURCES} *Sources*"] + source_lines + [""]

    llm = ctx["llm"]
    avg = f" (7-day average ${llm['avg7']:.2f})" if llm.get("avg7") is not None else ""
    lines += [f"{icons.LLM} *LLM*", f"- {llm['day']:%d %b}: {llm['calls']} calls, ${llm['cost']:.2f}{avg}", ""]

    res_lines = _resource_lines(ctx.get("resources", {}), ctx.get("resources_prev", {}))
    tables = ctx.get("top_tables", [])
    if res_lines or tables:
        lines.append(f"{icons.RESOURCES} *Resources*")
        lines += res_lines
        if tables:
            lines.append("- largest tables: " + ", ".join(
                f"{name} {size / 1e9:.1f} GB" for name, size in tables))
        lines.append("")

    prev = ctx.get("prev_digest")
    if prev and prev.get("last_seen"):
        lines.append(f"Previous digest: {prev['last_seen'].astimezone(IST):%d %b %H:%M} IST "
                     f"({prev.get('detail') or 'no details'})")
    else:
        lines.append("Previous digest: none recorded")
    lines.append(f"Generated {now.astimezone(IST):%d %b %H:%M} IST")
    return "\n".join(lines)
