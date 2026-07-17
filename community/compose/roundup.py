"""⑥ Roundup — daily payload (LLD-03 §6.1) + weekly Sat→Sat (§6.3).

Builds the payload from the L3/L4 tables, UPSERTs `roundups`, and (daily) asks
Sonnet for a 2-line headline. Local delivery renders it to markdown (render.py);
prod routes to Slack + email.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from community.config.settings import settings
from community.llm.client import complete
from community.reference import features
from community.store import db


def _daily_payload(today: date) -> dict:
    cfg = settings.registry.get("roundup", {})
    trend_bar = cfg.get("trending_min_items", 3)
    exclude = cfg.get("trending_exclude_topics", []) or [""]
    feat_bar = cfg.get("features_min_mentions", 2)
    # Trending = ≥N items (1 person ≠ a trend), excluding topics that already have
    # their own section (broker issues/charges), excluding unclassified other:*.
    window = cfg.get("daily_window_days", 1)  # prod 1; wider locally (spread test data)
    since = today - timedelta(days=window - 1)
    trending = db.query(
        "SELECT t.topic_key, x.label, SUM(t.count)::int AS count, MAX(t.velocity_z) AS velocity_z, "
        "MAX(t.spread)::int AS spread FROM topic_daily t "
        "LEFT JOIN topic_taxonomy x ON x.topic_key = t.topic_key "
        "WHERE t.day BETWEEN %s AND %s AND NOT (t.topic_key = ANY(%s)) "
        "AND t.topic_key NOT LIKE 'other:%%' GROUP BY t.topic_key, x.label "
        "HAVING SUM(t.count) >= %s "
        "ORDER BY MAX(t.velocity_z) DESC NULLS LAST, SUM(t.count) DESC LIMIT 8",
        (since, today, exclude, trend_bar))
    broker_issues = db.query(  # deliberately NO cutoff — one complaint is reportable
        "SELECT broker, issue_key, SUM(count)::int AS count, MAX(severity) AS severity, "
        "AVG(sentiment_avg) AS sentiment_avg FROM issue_rollup "
        "WHERE day BETWEEN %s AND %s GROUP BY broker, issue_key "
        "ORDER BY SUM(count) DESC LIMIT 8", (since, today))
    feature_requests = db.query(
        "SELECT feature_key, MAX(canonical_label) AS label, SUM(count)::int AS count "
        "FROM feature_rollup WHERE day BETWEEN %s AND %s GROUP BY feature_key "
        "HAVING SUM(count) >= %s ORDER BY SUM(count) DESC LIMIT 8", (since, today, feat_bar))
    opportunities = db.query(
        "SELECT o.id, o.source, o.thread_id, o.priority, o.matched_insight, o.brand_reply, "
        "o.rep_reply, o.recommended_timing, o.status, si.url "
        "FROM opportunities o "
        "LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id) "
        "LEFT JOIN social_items si ON si.item_id = c.root_item_id "
        "WHERE o.day = %s AND o.status='suggested' ORDER BY o.priority DESC LIMIT 10", (today,))
    content_proposals = db.query(
        "SELECT rank, format, format_family, platform, hook, outline, why, recommended_timing "
        "FROM content_proposals WHERE day=%s ORDER BY rank", (today,))
    nubra_watch = db.query(
        "SELECT c.source, c.thread_id, si.url, left(si.text, 200) AS summary "
        "FROM conversations c LEFT JOIN social_items si ON si.item_id = c.root_item_id "
        "WHERE c.is_nubra_watch AND c.last_seen > %s ORDER BY c.last_seen DESC LIMIT 10",
        (datetime.now(timezone.utc) - timedelta(hours=24),))
    rising_voices = db.query(
        "SELECT a.handle, a.source, s.voice_score, s.contributions, s.authenticity_flag "
        "FROM author_stats s JOIN authors a ON a.author_id = s.author_id "
        "ORDER BY s.voice_score DESC LIMIT 5")
    for v in rising_voices:  # profile links, not bare names
        profile_urls = {
            "twitter": f"https://x.com/{v['handle']}",
            "reddit": f"https://www.reddit.com/user/{v['handle']}",
            "github": f"https://github.com/{v['handle']}",
        }
        v["profile_url"] = profile_urls.get(v["source"]) or v.get("profile_url")
    stats_row = {
        "items_today": (db.one(
            "SELECT count(*) AS n FROM social_items WHERE ingested_at::date = %s", (today,)) or {}).get("n", 0),
        "conversations": (db.one("SELECT count(*) AS n FROM conversations") or {}).get("n", 0),
        "pings_sent": (db.one(
            "SELECT count(*) AS n FROM opportunities WHERE pinged_at::date = %s", (today,)) or {}).get("n", 0),
        "drafts_dropped_compliance": (db.one(
            "SELECT count(*) AS n FROM compliance_audit WHERE verdict='fail' AND ts::date = %s",
            (today,)) or {}).get("n", 0),
    }
    return {
        "period": "daily", "date": str(today),
        "grounding": features.current_version() or "UNSEEDED",
        "trending": trending, "broker_issues": broker_issues,
        "feature_requests": feature_requests, "opportunities": opportunities,
        "content_proposals": content_proposals, "nubra_watch": nubra_watch,
        "rising_voices": rising_voices, "stats": stats_row,
        "trending_bar": trend_bar, "features_bar": feat_bar,
    }


def _headline(payload: dict) -> str:
    has_signal = any(payload[k] for k in
                     ("trending", "broker_issues", "feature_requests", "opportunities"))
    if not has_signal:
        return "Quiet day — no significant community signals."
    slim = {k: payload[k][:4] for k in
            ("trending", "broker_issues", "feature_requests") if payload.get(k)}
    slim["opportunities"] = [
        {"priority": o["priority"], "insight": o.get("matched_insight")}
        for o in payload.get("opportunities", [])[:4]]
    raw, _u = complete(
        settings.draft_model,
        "You summarize a day of Indian trading-community chatter for Nubra's marketing "
        "team. Two short lines, factual, no advice, no hype, no emojis. Plain text only.",
        json.dumps(slim, default=str), max_tokens=150)
    return raw.strip()[:400]


def build_weekly(today: date) -> dict:
    """Sat→Sat window with last-week persistence weighting (LLD-03 §6.3)."""
    this_sat = today
    prev_sat = this_sat - timedelta(days=7)
    prior = db.one("SELECT payload FROM roundups WHERE period='weekly' AND date=%s", (prev_sat,))
    prior_keys: set[str] = set()
    if prior:
        for sec in ("persisted", "new_this_week"):
            prior_keys |= {i.get("key") for i in prior["payload"].get(sec, []) if i.get("key")}

    def weight(key: str, metric: float, weeks_running: int) -> float:
        return metric * (1 + 0.25 * min(weeks_running - 1, 3))

    topics = db.query(
        "SELECT topic_key AS key, sum(count) AS metric FROM topic_daily "
        "WHERE day >= %s AND day < %s GROUP BY topic_key", (prev_sat, this_sat))
    issues = db.query(
        "SELECT broker || ':' || issue_key AS key, sum(count) AS metric FROM issue_rollup "
        "WHERE day >= %s AND day < %s GROUP BY broker, issue_key", (prev_sat, this_sat))
    feats = db.query(
        "SELECT feature_key AS key, max(canonical_label) AS label, sum(count) AS metric, "
        "count(DISTINCT day) AS days FROM feature_rollup "
        "WHERE day >= %s AND day < %s GROUP BY feature_key", (prev_sat, this_sat))

    persisted, new_this_week = [], []
    for kind, rows in (("topic", topics), ("issue", issues), ("feature", feats)):
        for r in rows:
            wr = 2 if r["key"] in prior_keys else 1
            item = {"kind": kind, "key": r["key"], "label": r.get("label") or r["key"],
                    "metric": float(r["metric"] or 0), "weeks_running": wr,
                    "rank_score": weight(r["key"], float(r["metric"] or 0), wr)}
            (persisted if wr > 1 else new_this_week).append(item)
    persisted.sort(key=lambda i: -i["rank_score"])
    new_this_week.sort(key=lambda i: -i["rank_score"])

    acted = db.query(
        "SELECT status, dismissed_reason, count(*) AS n FROM opportunities "
        "WHERE status_updated_at >= %s GROUP BY status, dismissed_reason", (prev_sat,))
    return {
        "period": "weekly", "window": {"from": str(prev_sat), "to": str(this_sat)},
        "grounding": features.current_version() or "UNSEEDED",
        "persisted": persisted[:10], "new_this_week": new_this_week[:10],
        "consistent_features": [f for f in feats if f["days"] >= 4],
        "actions_recap": {
            "opportunities_surfaced": (db.one(
                "SELECT count(*) AS n FROM opportunities WHERE created_at >= %s",
                (prev_sat,)) or {}).get("n", 0),
            "status_changes": acted,
        },
    }


def run() -> dict:
    today = datetime.now(timezone.utc).date()
    payload = _daily_payload(today)
    # Headline is one Sonnet call per day (morning build); hourly composes
    # refresh the payload but reuse the day's existing headline.
    prior = db.one("SELECT payload->>'headline' AS h FROM roundups "
                   "WHERE period='daily' AND date=%s", (today,))
    payload["headline"] = (prior or {}).get("h") or _headline(payload)
    db.execute(
        "INSERT INTO roundups (period, date, payload) VALUES ('daily', %s, %s) "
        "ON CONFLICT (period, date) DO UPDATE SET payload = EXCLUDED.payload",
        (today, db.jsonb(payload)),
    )
    stats = {"sections": {k: len(v) for k, v in payload.items() if isinstance(v, list)},
             "headline": payload["headline"][:120]}
    if today.weekday() == 5:  # Saturday — Sat→Sat weekly
        wk = build_weekly(today)
        db.execute(
            "INSERT INTO roundups (period, date, payload) VALUES ('weekly', %s, %s) "
            "ON CONFLICT (period, date) DO UPDATE SET payload = EXCLUDED.payload",
            (today, db.jsonb(wk)),
        )
        stats["weekly"] = True
    from community.store.repositories import advance_state
    advance_state("roundup", "", items=1)
    return stats
