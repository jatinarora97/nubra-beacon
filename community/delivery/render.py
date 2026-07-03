"""Local delivery — renders the heads-up + daily roundup to out/messages/*.md.

On prod the same context dicts feed the Slack Block-Kit + email templates
(LLD-03 §6.4); locally the markdown pair stands in for both channels. Novelty
stamping (pinged_at / conversations.headsup_at / topic_daily.headsup_at+count)
happens HERE, on send — exactly like the prod heads-up sender.
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


def _ops_lines(all_stats: dict) -> list[str]:
    ing = all_stats.get("ingest", {})
    ded = all_stats.get("dedup", {})
    enr = all_stats.get("enrich", {})
    agg = all_stats.get("aggregate", {})
    sco = all_stats.get("score", {})
    fetched = ing.get("fetched_by_source") or {}
    lines = []
    if fetched:
        per_src = " · ".join(f"{k} {v}" for k, v in fetched.items())
        lines.append(f"- fetched **{sum(fetched.values())}** ({per_src})"
                     + (f" + backfilled {ing['backfilled']}" if ing.get("backfilled") else ""))
    if ded:
        lines.append(f"- dedup: {ded.get('checked', 0)} checked → "
                     f"{ded.get('exact_dupes', 0)} exact + {ded.get('near_dupes', 0)} near dupes linked")
    if enr:
        lines.append(f"- enriched {enr.get('enriched', 0)} · noise-filtered "
                     f"{enr.get('prefiltered_noise', 0)} (rules) · LLM calls {enr.get('llm_calls', 0)}"
                     + (" · **keyword fallback active**" if enr.get("fallback") else ""))
    if agg:
        lines.append(f"- aggregate: {agg.get('conversations', 0)} conversations · "
                     f"{agg.get('topics', agg.get('topics_rising', 0))} topics · "
                     f"{agg.get('issues', 0)} issue rollups · {agg.get('features', 0)} feature rollups")
    if sco:
        lines.append(f"- scored {sco.get('scored', 0)} → {sco.get('persisted', 0)} opportunities "
                     f"({sco.get('new_ge70', 0)} ≥70) · Nubra mentions {sco.get('nubra_watch', 0)}"
                     + (f" · recurrence-boosted {sco['recurrence_boosted']}"
                        if sco.get("recurrence_boosted") else ""))
    return lines or ["- no stage stats this run"]


def write_local_messages(all_stats: dict) -> list[pathlib.Path]:
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    now_ist = datetime.now(IST)
    paths: list[pathlib.Path] = []

    # ── heads-up ──
    actions = _action_items()
    watch = _nubra_watch_items()
    rising = _rising_topics()
    is_ops_only = not (actions or watch or rising)
    on_empty = settings.registry["delivery"].get("headsup_on_empty", "ops_summary")
    mention = settings.registry["delivery"].get("nubra_watch_mention") or ""
    if not (is_ops_only and on_empty == "skip"):
        ctx = {
            "window": now_ist.strftime("%d %b %Y · %H:%M IST"),
            "is_ops_only": is_ops_only,
            "actions": actions, "nubra_watch": watch, "rising_topics": rising,
            "mention": f" · {mention}" if mention else "",
            "ops_lines": _ops_lines(all_stats),
            "x_live_note": (all_stats.get("ingest") or {}).get("x_live_note"),
        }
        out = _env.get_template("headsup_md.j2").render(**ctx)
        p = settings.out_dir / f"{now_ist:%Y-%m-%d-%H%M}-headsup.md"
        p.write_text(out)
        paths.append(p)
        # novelty stamping — on send, exactly like prod
        if actions:
            db.execute("UPDATE opportunities SET pinged_at = now() WHERE id = ANY(%s)",
                       ([a["id"] for a in actions],))
        for n in watch:
            db.execute("UPDATE conversations SET headsup_at = now() "
                       "WHERE source=%s AND thread_id=%s", (n["source"], n["thread_id"]))
        for t in rising:
            db.execute(
                "UPDATE topic_daily SET headsup_at = COALESCE(headsup_at, now()), "
                "headsup_count = headsup_count + 1 WHERE topic_key=%s AND day=%s",
                (t["topic_key"], now_ist.date()),
            )

    # ── daily roundup ──
    r = db.one("SELECT payload FROM roundups WHERE period='daily' AND date=%s",
               (now_ist.date(),))
    if r:
        out = _env.get_template("roundup_daily_md.j2").render(
            date=now_ist.strftime("%a %d %b %Y"), payload=r["payload"])
        p = settings.out_dir / f"{now_ist:%Y-%m-%d}-roundup-daily.md"
        p.write_text(out)
        paths.append(p)
    return paths
