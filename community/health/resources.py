# community/health/resources.py
"""Host + Postgres resource metrics (spec §8) — container-visible only.

Disk comes from statvfs on /app/out (a bind mount of the host's ./out, so it is
the host filesystem); memory/load from /proc (compose sets no limits, so these
are host values); restarts from the PID 1 start time (api) and
pg_postmaster_start_time() (postgres). Every collector tolerates a missing
source (Windows dev box, no /proc) by omitting that metric.
Known limit: if Docker's data root is on a different filesystem than ./out its
usage is not visible here.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from community.config.log import IST, get_logger
from community.config.settings import ROOT
from community.health.model import CRIT, OK, WARN, Result, owns

log = get_logger("health.resources")
OUT_DIR = ROOT / "out"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def parse_meminfo(text: str) -> dict[str, float]:
    kv: dict[str, float] = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        parts = rest.split()
        if parts:
            kv[name.strip()] = float(parts[0])
    out: dict[str, float] = {}
    if kv.get("MemTotal") and kv.get("MemAvailable") is not None:
        out["mem_available_pct"] = 100.0 * kv["MemAvailable"] / kv["MemTotal"]
    if kv.get("SwapTotal"):
        out["swap_used_pct"] = 100.0 * (kv["SwapTotal"] - kv.get("SwapFree", 0.0)) / kv["SwapTotal"]
    return out


def parse_proc_start_epoch(stat_line: str, btime: float, hz: int) -> float | None:
    """starttime is field 22 of /proc/<pid>/stat, in clock ticks since boot.
    The command name (field 2) may contain spaces/parens, so split after the
    LAST ')' — field 3 is then index 0, field 22 index 19."""
    try:
        rest = stat_line[stat_line.rindex(")") + 1:].split()
        return btime + float(rest[19]) / hz
    except (ValueError, IndexError):
        return None


def collect_host(out_dir: Path = OUT_DIR, proc: str = "/proc") -> dict[str, float]:
    m: dict[str, float] = {}
    try:
        st = os.statvfs(out_dir)
        used = st.f_blocks - st.f_bfree
        if used + st.f_bavail:
            m["disk_used_pct"] = 100.0 * used / (used + st.f_bavail)
        m["disk_free_gb"] = st.f_bavail * st.f_frsize / 1e9
    except (AttributeError, OSError):
        pass
    try:
        m.update(parse_meminfo(_read(f"{proc}/meminfo")))
    except (OSError, ValueError):
        pass
    try:
        load1 = float(_read(f"{proc}/loadavg").split()[0])
        m["load_per_core"] = load1 / (os.cpu_count() or 1)
    except (OSError, ValueError, IndexError):
        pass
    try:
        btime = next(float(line.split()[1]) for line in _read(f"{proc}/stat").splitlines()
                     if line.startswith("btime"))
        epoch = parse_proc_start_epoch(_read(f"{proc}/1/stat"), btime, os.sysconf("SC_CLK_TCK"))
        if epoch is not None:
            m["api_start_epoch"] = epoch
    except (OSError, StopIteration, ValueError, AttributeError):
        pass
    cron_log = Path(out_dir) / "cron.log"
    if cron_log.exists():
        m["cron_log_mb"] = cron_log.stat().st_size / 1e6
    heartbeat = Path(out_dir) / ".backup_ok"  # `touch`ed by the backup cron line
    if heartbeat.exists():
        m["backup_age_h"] = (time.time() - heartbeat.stat().st_mtime) / 3600
    return m


def collect_db() -> dict[str, float]:
    from community.store import db
    row = db.one("SELECT pg_database_size(current_database()) AS size, "
                 "extract(epoch FROM pg_postmaster_start_time()) AS started")
    return {"db_size_gb": row["size"] / 1e9, "pg_start_epoch": float(row["started"])}


def record_samples(metrics: dict[str, float]) -> None:
    from community.store import db
    db.executemany("INSERT INTO resource_samples (metric, value) VALUES (%s, %s)",
                   list(metrics.items()))


def collect_and_record() -> dict[str, float]:
    metrics = collect_host()
    try:
        metrics.update(collect_db())
    except Exception as e:  # noqa: BLE001 — host metrics are still worth recording
        log.warning("db resource metrics unavailable (%s)", e)
    record_samples(metrics)
    return metrics


def history(metric: str, hours: float) -> list[tuple[datetime, float]]:
    from community.store import db
    rows = db.query(
        "SELECT ts, value FROM resource_samples WHERE metric = %s "
        "AND ts > now() - (%s * interval '1 hour') ORDER BY ts", (metric, hours))
    return [(r["ts"], r["value"]) for r in rows]


def top_tables(limit: int = 5) -> list[tuple[str, int]]:
    from community.store import db
    rows = db.query(
        "SELECT c.relname AS name, pg_total_relation_size(c.oid) AS size "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY size DESC LIMIT %s", (limit,))
    return [(r["name"], int(r["size"])) for r in rows]


def eta_days(points: list[tuple[datetime, float]], min_span_h: float = 24,
             min_points: int = 12) -> float | None:
    """Days until free space (GB) reaches zero at the least-squares fill rate."""
    if len(points) < min_points:
        return None
    t0 = points[0][0]
    xs = [(t - t0).total_seconds() / 86400 for t, _ in points]
    ys = [v for _, v in points]
    if xs[-1] < min_span_h / 24:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den  # GB per day
    return ys[-1] / -slope if slope < 0 else None


def eval_disk(r: dict, used_pct: float, free_hist: list[tuple[datetime, float]]) -> Result:
    eta = eta_days(free_hist)
    eta_txt = f", full in about {eta:.0f} days at the current rate" if eta is not None else ""
    detail = f"{used_pct:.0f}% used{eta_txt}"
    hint = "free space on the VM (docker images/logs, out/cron.log, old backups)"
    if used_pct >= r["disk_crit_pct"] or (eta is not None and eta < r["disk_eta_crit_days"]):
        return Result("disk", CRIT, detail, hint)
    if used_pct >= r["disk_warn_pct"] or (eta is not None and eta < r["disk_eta_warn_days"]):
        return Result("disk", WARN, detail, hint)
    return Result("disk", OK, detail)


def eval_memory(r: dict, values: list[float]) -> Result:
    latest = values[-1]
    n = r["mem_crit_samples"]
    if len(values) >= n and all(v < r["mem_crit_pct"] for v in values[-n:]):
        return Result("memory", CRIT, f"{latest:.0f}% memory available for {n}+ samples in a row",
                      "check docker stats; a heavy job may be starving the box")
    if latest < r["mem_warn_pct"]:
        return Result("memory", WARN, f"{latest:.0f}% memory available")
    return Result("memory", OK, f"{latest:.0f}% memory available")


def eval_load(r: dict, values: list[float]) -> Result:
    if len(values) >= 3 and all(v > r["load_warn_per_core"] for v in values[-3:]):
        return Result("load", WARN, f"load {values[-1]:.1f} per core for 3+ samples")
    return Result("load", OK, f"load {values[-1]:.1f} per core")


def eval_swap(r: dict, pct: float) -> Result:
    level = WARN if pct > r["swap_warn_pct"] else OK
    return Result("swap", level, f"{pct:.0f}% of swap in use")


def eval_cron_log(r: dict, mb: float) -> Result:
    level = WARN if mb > r["cron_log_warn_mb"] else OK
    return Result("cron_log", level, f"out/cron.log is {mb:.0f} MB",
                  "trim or rotate out/cron.log by hand" if level == WARN else "")


def eval_restarts(name: str, hist: list[tuple[datetime, float]], now: datetime, r: dict) -> Result:
    key = f"restart:{name}"
    events = [t for (t, v), (_, pv) in zip(hist[1:], hist[:-1])
              if abs(v - pv) > 5 and now - t <= timedelta(hours=24)]
    recent = [t for t in events if now - t <= timedelta(hours=1)]
    if len(recent) >= r["restart_crit_count"]:
        return Result(key, CRIT, f"{name} restarted {len(recent)} times in the last hour",
                      f"docker compose logs {'api' if name == 'api' else 'postgres'} --tail 100")
    if events:
        when = events[-1].astimezone(IST).strftime("%d %b %H:%M")
        return Result(key, WARN, f"{name} restarted at {when} IST")
    return Result(key, OK, f"no {name} restart in the last 24h")


def eval_backup(age_h: float | None, r: dict) -> Result:
    if age_h is None:
        return Result("backup", WARN, "no backup heartbeat file found (out/.backup_ok)",
                      "append '&& touch out/.backup_ok' to the backup cron line")
    if age_h > r["backup_crit_hours"]:
        return Result("backup", CRIT, f"last good backup was {age_h:.0f} h ago",
                      "run deploy/backup.sh by hand and check out/cron.log for the failure")
    return Result("backup", OK, f"last good backup {age_h:.0f} h ago")


@owns("disk", "memory", "load", "swap", "cron_log", "restart:", "backup")
def check_resources(cfg: dict, now: datetime) -> list[Result]:
    r = cfg["resources"]
    results: list[Result] = []
    used = history("disk_used_pct", 2)
    if used:
        results.append(eval_disk(r, used[-1][1], history("disk_free_gb", 24 * 7)))
    mem = history("mem_available_pct", 2)
    if mem:
        results.append(eval_memory(r, [v for _, v in mem]))
    load = history("load_per_core", 2)
    if load:
        results.append(eval_load(r, [v for _, v in load]))
    swap = history("swap_used_pct", 2)
    if swap:
        results.append(eval_swap(r, swap[-1][1]))
    cron = history("cron_log_mb", 2)
    if cron:
        results.append(eval_cron_log(r, cron[-1][1]))
    for name, metric in (("api", "api_start_epoch"), ("postgres", "pg_start_epoch")):
        hist = history(metric, 26)
        if hist:
            results.append(eval_restarts(name, hist, now, r))
    backup = history("backup_age_h", 2)
    results.append(eval_backup(backup[-1][1] if backup else None, r))
    return results
