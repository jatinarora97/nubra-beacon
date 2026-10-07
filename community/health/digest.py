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
