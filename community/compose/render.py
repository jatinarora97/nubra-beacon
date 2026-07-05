"""Compose — PURE rendering. No DB writes, no file writes, no sending.

build_headsup(all_stats)  -> (markdown | None, stamping_plan)
build_roundup(period)     -> {"markdown", "date", "period"} | None

The stamping_plan (opportunity ids, Nubra-watch thread keys, topic keys) is
returned to the caller; dispatch applies it AFTER at least one successful
delivery — rendering alone must never consume novelty.
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from community.config.settings import settings
from community.store import db

IST = timezone(timedelta(hours=5, minutes=30))
_env = Environment(
    loader=FileSystemLoader(pathlib.Path(__file__).parent / "templates"),
    undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
)

_ICONS = {"broker_issue": "🔥", "feature_request": "✨", "question": "❓",
          "comparison": "⚖️", "topic": "📈"}


def _today_start_utc() -> datetime:
    now_ist = datetime.now(IST)
    return now_ist.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _action_items() -> list[dict]:
    threshold = settings.registry["recommend"]["thresholds"]["headsup"]
    rows = db.query(
        """
        SELECT o.id, o.priority, o.matched_insight, o.brand_reply, o.rep_reply,
               o.recommended_timing, c.last_seen, si.url, left(si.text, 180) AS title
        FROM opportunities o
        LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id)
        LEFT JOIN social_items si ON si.item_id = c.root_item_id
        WHERE o.pinged_at IS NULL AND o.status = 'suggested' AND o.priority >= %s
        ORDER BY o.priority DESC LIMIT 8
        """,
        (threshold,),
    )
    now = datetime.now(timezone.utc)
    actions = []
    for r in rows:
        mi = r.get("matched_insight") or {}
        kind = mi.get("kind", "topic")
        rec = mi.get("recurrence")
        age_h = ((now - r["last_seen"]).total_seconds() / 3600) if r.get("last_seen") else None
        actions.append({
            "id": r["id"], "priority": r["priority"],
            "interactions": mi.get("interactions"),
            "icon": "↗" if rec else _ICONS.get(kind, "•"),
            "kind_label": (f"STILL RISING · {rec['topic_key']} — thread #{rec['nth_thread_today']} today"
                            if rec else kind.replace("_", " ").upper()),
            "boost_note": f"boosted ×{rec['boost']}" if rec else None,
            "title": (r.get("title") or "").replace("\n", " "),
            "insight": {k: v for k, v in mi.items() if k != "recurrence"},
            "age": f"{age_h:.0f}h" if age_h is not None else "?",
            "timing": (r.get("recommended_timing") or {}).get("window"),
            "url": r.get("url"),
            "brand_reply": r.get("brand_reply"), "rep_reply": r.get("rep_reply"),
        })
    return actions


def _nubra_watch_items() -> list[dict]:
    return db.query(
        """
        SELECT c.source, c.thread_id, si.url, left(si.text, 160) AS summary
        FROM conversations c
        LEFT JOIN social_items si ON si.item_id = c.root_item_id
        WHERE c.is_nubra_watch
          AND (c.headsup_at IS NULL OR c.headsup_at < %s)
          AND c.last_seen > now() - interval '24 hours'
        ORDER BY c.last_seen DESC LIMIT 10
        """,
        (_today_start_utc(),),
    )


def _rising_topics() -> list[dict]:
    today = datetime.now(timezone.utc).date()
    rows = db.query(
        """
        SELECT t.topic_key, x.label, t.count, t.velocity_z, false AS cold_start
        FROM topic_daily t LEFT JOIN topic_taxonomy x ON x.topic_key = t.topic_key
        WHERE t.day = %s AND t.velocity_z >= 1.5 AND t.headsup_at IS NULL
        ORDER BY t.velocity_z DESC LIMIT 5
        """,
        (today,),
    )
    if rows:
        return rows
    # cold-start (no 7d baseline yet): top by raw count, only if not yet surfaced
    return db.query(
        """
        SELECT t.topic_key, x.label, t.count, t.velocity_z, true AS cold_start
        FROM topic_daily t LEFT JOIN topic_taxonomy x ON x.topic_key = t.topic_key
        WHERE t.day = %s AND t.headsup_at IS NULL AND t.count >= 3
        ORDER BY t.count DESC LIMIT 3
        """,
        (today,),
    )


def _ops_block(all_stats: dict) -> dict:
    """The 'what we did in the last hour' framework — human-facing, no pipeline
    internals: sources fetched, volume analyzed, actions identified per platform
    and kind, top standing actions."""
    # stage keys per runner.STAGE_MODULES ("ingest"/"dedup" kept as fallbacks
    # for older callers)
    ing = all_stats.get("scrape") or all_stats.get("ingest") or {}
    enr = all_stats.get("enrich") or {}
    fetched = ing.get("fetched", ing.get("fetched_by_source") or {})

    src_bits = []
    for src, n in fetched.items():
        src_bits.append(f"{src.replace('_', ' ')} **{n}**")
    fetched_line = " · ".join(src_bits) if src_bits else "no new fetches this run"
    blocked = [h for h in (ing.get("reddit_health") or []) if "block" in h.lower() or "FAIL" in h]
    if blocked:
        fetched_line += f" · reddit **blocked on this network** ({len(blocked)} subs unreachable)"

    analyzed = (enr.get("llm_enriched", 0) or 0) + (enr.get("prefiltered_noise", 0) or 0)
    junk = enr.get("prefiltered_noise", 0) or 0
    llm_noise = (db.one(
        "SELECT count(*) AS n FROM item_enrichment WHERE is_noise AND model NOT LIKE 'rule%%' "
        "AND enriched_at > now() - interval '2 hours'") or {}).get("n", 0)
    analyzed_line = (f"**{analyzed}** new items analyzed → {max(analyzed - junk - llm_noise, 0)} relevant "
                     f"({junk + llm_noise} junk/noise filtered out)") if analyzed else \
        "no new items this run (nothing new to analyze)"

    by_src = db.query(
        "SELECT source, count(*) AS n FROM opportunities "
        "WHERE status='suggested' AND updated_at > now() - interval '24 hours' GROUP BY source")
    by_kind = db.query(
        "SELECT matched_insight->>'kind' AS kind, count(*) AS n FROM opportunities "
        "WHERE status='suggested' AND updated_at > now() - interval '24 hours' "
        "GROUP BY 1 ORDER BY n DESC")
    total_opps = sum(r["n"] for r in by_src)
    kind_labels = {"feature_request": "feature requests", "question": "questions",
                   "broker_issue": "competitor complaints", "comparison": "comparisons",
                   "topic": "topical threads"}
    identified_line = (
        f"**{total_opps}** possible actions on the table ("
        + " · ".join(f"{r['source']} {r['n']}" for r in by_src) + ") — "
        + " · ".join(f"{r['n']} {kind_labels.get(r['kind'], r['kind'])}" for r in by_kind if r["kind"])
    ) if total_opps else "no actions identified yet"

    top_standing = db.query(
        "SELECT o.priority, o.matched_insight->>'kind' AS kind, left(si.text, 110) AS title, si.url "
        "FROM opportunities o "
        "LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id) "
        "LEFT JOIN social_items si ON si.item_id = c.root_item_id "
        "WHERE o.status='suggested' ORDER BY o.priority DESC LIMIT 3")
    for i, r in enumerate(top_standing, 1):
        r["rank"] = i
        r["kind_label"] = kind_labels.get(r["kind"], r["kind"] or "thread")

    return {"fetched": fetched_line, "analyzed": analyzed_line,
            "identified": identified_line, "top_standing": top_standing}


def build_headsup(all_stats: dict) -> tuple[str | None, dict]:
    """Render the heads-up. Returns (markdown | None, stamping_plan).
    None markdown = nothing to send this hour (ops-only + headsup_on_empty=skip)."""
    now_ist = datetime.now(IST)
    actions = _action_items()
    watch = _nubra_watch_items()
    rising = _rising_topics()
    is_ops_only = not (actions or watch or rising)
    on_empty = settings.registry["delivery"].get("headsup_on_empty", "ops_summary")
    plan = {
        "opportunity_ids": [a["id"] for a in actions],
        "watch_threads": [(n["source"], n["thread_id"]) for n in watch],
        "topics": [(t["topic_key"], str(now_ist.date())) for t in rising],
    }
    if is_ops_only and on_empty == "skip":
        return None, plan
    mention = settings.registry["delivery"].get("nubra_watch_mention") or ""
    ctx = {
        "window": now_ist.strftime("%d %b %Y · %H:%M IST"),
        "is_ops_only": is_ops_only,
        "actions": actions, "nubra_watch": watch, "rising_topics": rising,
        "mention": f" · {mention}" if mention else "",
        "ops": _ops_block(all_stats),
        "x_live_note": (all_stats.get("scrape") or all_stats.get("ingest") or {}).get("x_live_note"),
    }
    return _env.get_template("headsup_md.j2").render(**ctx), plan


def build_roundup(period: str = "daily") -> dict | None:
    """Render the latest roundup of a period. Daily = today's row; weekly = the
    most recent row within 7 days (produced Saturdays). Returns
    {"markdown", "date", "period"} or None when no row exists."""
    now_ist = datetime.now(IST)
    if period == "daily":
        row = db.one("SELECT date, payload FROM roundups WHERE period='daily' AND date=%s",
                     (now_ist.date(),))
    else:
        row = db.one(
            "SELECT date, payload FROM roundups WHERE period='weekly' "
            "AND date > %s ORDER BY date DESC LIMIT 1",
            (now_ist.date() - timedelta(days=7),))
    if not row:
        return None
    template = "roundup_daily_md.j2" if period == "daily" else "roundup_weekly_md.j2"
    md = _env.get_template(template).render(
        date=now_ist.strftime("%a %d %b %Y"), payload=row["payload"])
    return {"markdown": md, "date": row["date"], "period": period}
