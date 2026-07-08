"""Dispatch — the ONLY stage that sends and mutates delivery state.

Flow per run: render (compose is pure) → send to each configured channel →
archive to out/messages/ ALWAYS → apply novelty stamping only after at least
one successful delivery (the archive counts — it is the audit trail).

Channel gating:
  - heads-up → Slack + email only inside 08:00–20:00 IST; archive any time
  - roundups → archived whenever present; sent to channels once per row,
    tracked in roundups.delivery (LLD-03 §6.2) so hourly runs never re-send
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from community.compose import render
from community.config.settings import settings
from community.dispatch import email as email_ch
from community.dispatch import slack as slack_ch
from community.store import db, repositories as repo

IST = timezone(timedelta(hours=5, minutes=30))
SEND_WINDOW = (8, 20)  # heads-up channel window, IST hours [start, end)


def _archive(markdown: str, filename: str) -> str:
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    p = settings.out_dir / filename
    p.write_text(markdown)
    return str(p)


def _in_headsup_window(now_ist: datetime) -> bool:
    return SEND_WINDOW[0] <= now_ist.hour < SEND_WINDOW[1]


def _apply_stamping(plan: dict) -> None:
    if plan.get("opportunity_ids"):
        db.execute("UPDATE opportunities SET pinged_at = now() WHERE id = ANY(%s)",
                   (plan["opportunity_ids"],))
    for source, thread_id in plan.get("watch_threads", []):
        db.execute("UPDATE conversations SET headsup_at = now() "
                   "WHERE source=%s AND thread_id=%s", (source, thread_id))
    for topic_key, day in plan.get("topics", []):
        db.execute(
            "UPDATE topic_daily SET headsup_at = COALESCE(headsup_at, now()), "
            "headsup_count = headsup_count + 1 WHERE topic_key=%s AND day=%s",
            (topic_key, day),
        )


def _roundup_channel_state(period: str, date) -> dict:
    row = db.one("SELECT delivery FROM roundups WHERE period=%s AND date=%s", (period, date))
    return (row or {}).get("delivery") or {}


def _record_roundup_delivery(period: str, date, channel: str, status: str) -> None:
    db.execute(
        "UPDATE roundups SET delivery = delivery || %s WHERE period=%s AND date=%s",
        (db.jsonb({channel: {"status": status,
                             "ts": datetime.now(timezone.utc).isoformat()}}),
         period, date),
    )


def run(all_stats: dict | None = None) -> dict:
    all_stats = all_stats or {}
    now_ist = datetime.now(IST)
    written: list[str] = []
    channels: dict[str, str] = {}

    # ── heads-up ─────────────────────────────────────────────────────────
    md, plan, payload = render.build_headsup(all_stats)
    if md is None:
        channels["headsup"] = "skipped (no actions; headsup_on_empty=skip)"
    else:
        written.append(_archive(md, f"{now_ist:%Y-%m-%d-%H%M}-headsup.md"))
        subject = f"Community heads-up · {now_ist:%d %b %H:%M} IST"
        if _in_headsup_window(now_ist):
            channels["headsup_slack"] = slack_ch.send(md, subject)
            channels["headsup_email"] = email_ch.send(md, subject)
        else:
            note = f"outside {SEND_WINDOW[0]:02d}–{SEND_WINDOW[1]:02d} IST window (archive only)"
            channels["headsup_slack"] = channels["headsup_email"] = note
        # persist alongside the file archive (work plan N3 — DB is system of record)
        import json as _json
        db.execute(
            "INSERT INTO headsups (payload, markdown, delivery) VALUES (%s, %s, %s)",
            (db.jsonb(_json.loads(_json.dumps(payload, default=str))), md,
             db.jsonb({k: v for k, v in channels.items() if k.startswith("headsup")})),
        )
        # novelty consumed only after ≥1 successful delivery (archive counts)
        _apply_stamping(plan)

    # ── roundups (daily + weekly when present) ──────────────────────────
    for period in ("daily", "weekly"):
        r = render.build_roundup(period)
        if not r:
            continue
        written.append(_archive(r["markdown"], f"{r['date']}-roundup-{period}.md"))
        db.execute("UPDATE roundups SET markdown = %s WHERE period=%s AND date=%s",
                   (r["markdown"], period, r["date"]))
        state = _roundup_channel_state(period, r["date"])
        subject = f"Community roundup ({period}) · {r['date']}"
        for name, sender in (("slack", slack_ch), ("email", email_ch)):
            if (state.get(name) or {}).get("status") == "sent":
                channels[f"roundup_{period}_{name}"] = "already sent for this row"
                continue
            status = sender.send(r["markdown"], subject)
            channels[f"roundup_{period}_{name}"] = status
            if status == "sent":
                _record_roundup_delivery(period, r["date"], name, "sent")

    # ── overview message (Slack; cadence via delivery.overview) ──────────
    try:
        channels.update(_dispatch_overview(datetime.now(IST), written))
    except Exception as e:  # noqa: BLE001 — overview must never break dispatch
        channels["overview"] = f"error: {type(e).__name__}: {str(e)[:80]}"

    return {"written": written, "channels": channels}


def _dispatch_overview(now_ist: datetime, written: list[str]) -> dict:
    """Compose + archive + Slack-send the overview snapshot.

    Cadence (registry delivery.overview): hourly | daily | off, guarded by a
    pipeline_state row (stage='dispatch', source='overview') — DB-backed so it
    survives out/ cleanup and container restarts. hourly = at most one message
    per IST clock-hour (a rerun within the hour skips); daily = one per IST
    day. Both respect the same 08:00-20:00 IST window as heads-ups — outside
    it nothing composes or sends (no 3am Slack messages). The watermark
    advances on COMPOSE (archive), not on successful send: deterministic
    artifacts; if Slack creds land mid-day, sending starts at the next slot."""
    cadence = settings.registry["delivery"].get("overview", "daily")
    if cadence == "off":
        return {"overview": "off (delivery.overview)"}
    if not _in_headsup_window(now_ist):
        return {"overview": f"outside {SEND_WINDOW[0]:02d}-{SEND_WINDOW[1]:02d} IST window"}
    state = repo.get_state("dispatch", "overview")
    wm = (state or {}).get("watermark")
    if wm:
        wm_ist = wm.astimezone(IST)
        if cadence == "daily" and wm_ist.date() == now_ist.date():
            return {"overview": "already sent today"}
        if cadence == "hourly" and (wm_ist.date(), wm_ist.hour) == (now_ist.date(), now_ist.hour):
            return {"overview": "already sent this hour"}
    text = render.build_overview()
    written.append(_archive(text, f"{now_ist:%Y-%m-%d-%H%M}-overview.md"))
    status = slack_ch.send(text, f"Beacon overview · {now_ist:%d %b %H:%M} IST")
    repo.advance_state("dispatch", "overview", watermark=datetime.now(timezone.utc))
    return {"overview_slack": status}
