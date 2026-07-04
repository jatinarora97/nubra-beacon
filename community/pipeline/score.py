"""⑤a hourly scoring pass — no LLM (LLD-03 §1).

Scores conversations into `opportunities`; diverts Nubra-watch threads (never an
opportunity); applies the recurrence boost for new threads on topics already
featured in a heads-up today. `run()` returns the ops-summary stats.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from community.config.settings import settings
from community.reference import features
from community.store import db

_W = None  # loaded from registry


def _weights() -> dict:
    global _W
    if _W is None:
        _W = settings.registry["recommend"]["weights"]
    return _W


def _thread_rows(source: str, thread_id: str) -> list[dict]:
    return db.query(
        """
        SELECT si.item_id, si.text, si.engagement, a.followers,
               e.intent, e.entities, e.topic_key, e.is_noise
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.source = %s AND si.thread_id = %s AND si.duplicate_of IS NULL
        ORDER BY si.created_at
        LIMIT 50
        """,
        (source, thread_id),
    )


def _matched_insight(rows: list[dict]) -> tuple[dict, float, float]:
    """-> (insight jsonb, relevance_base, opportunity_type_score)"""
    feature_phrase = None
    for r in rows:
        e = r.get("entities") or {}
        intent = r.get("intent")
        issue = e.get("issue") or {}
        broker = issue.get("broker") or (e.get("brokers") or [None])[0]
        if intent == "complaint" and broker and broker != "nubra":
            return ({"kind": "broker_issue", "broker": broker,
                     "issue_key": issue.get("issue_key")}, 1.0, 1.0)
        if intent == "feature_request":
            feature_phrase = e.get("feature_phrase") or feature_phrase
    intents = {r.get("intent") for r in rows}
    if feature_phrase or "feature_request" in intents:
        return ({"kind": "feature_request", "feature_phrase": feature_phrase}, 0.9, 0.9)
    if intents & {"question", "how_to"}:
        return ({"kind": "question"}, 0.7, 0.8)
    if "comparison" in intents:
        return ({"kind": "comparison"}, 0.7, 0.7)
    if intents == {"news_opinion"} or intents == {"news_opinion", None}:
        return ({"kind": "topic"}, 0.4, 0.3)
    return ({"kind": "topic"}, 0.4, 0.5)


def _seo_boost(rows: list[dict], kws: list[str]) -> float:
    text = " ".join((r["text"] or "") for r in rows).lower()[:8000]
    hits = sum(1 for kw in kws if kw in text)
    return min(0.1 * hits, 0.2)


def _interactions(rows: list[dict]) -> int:
    """Real engagement: likes + replies + shares (views/followers are NOT interactions)."""
    best = 0
    for r in rows:
        n = (r.get("engagement") or {}).get("native", {})
        inter = (n.get("likes", 0) + n.get("upvotes", 0) + n.get("replies", 0)
                 + n.get("comments", 0) + n.get("retweets", 0) + n.get("quotes", 0))
        best = max(best, inter)
    return best


def _reach(rows: list[dict]) -> float:
    """60% audience size (followers/views), 40% actual interactions — a thread with
    zero likes/replies should not out-reach one people engage with."""
    audience = 0
    for r in rows:
        native = (r.get("engagement") or {}).get("native", {})
        audience = max(audience, r.get("followers") or 0, native.get("views", 0))
    a = min(math.log10(1 + audience) / 6.0, 1.0)
    e = min(math.log1p(_interactions(rows)) / math.log1p(200), 1.0)
    return 0.6 * a + 0.4 * e


def _author_quality(rows: list[dict]) -> float:
    ids = [r["item_id"] for r in rows]
    if not ids:
        return 0.5
    row = db.one(
        """
        SELECT max(s.voice_score) AS vs, bool_or(s.authenticity_flag) AS flagged
        FROM social_items si JOIN author_stats s ON s.author_id = si.author_id
        WHERE si.item_id = ANY(%s)
        """,
        (ids,),
    )
    if not row or row["vs"] is None:
        return 0.5
    q = min(row["vs"] / 100.0, 1.0)
    return q * 0.3 if row["flagged"] else q


def run(lookback_hours: int = 48) -> dict:
    """lookback_hours: widen (e.g. 24*14) when scoring backfilled historical data
    locally — prod runs hourly with the default."""
    now = datetime.now(timezone.utc)
    kws = features.seo_keywords()
    convs = db.query(
        "SELECT * FROM conversations WHERE last_seen > %s",
        (now - timedelta(hours=lookback_hours),),
    )
    stats = {"conversations": len(convs), "scored": 0, "persisted": 0,
             "new_ge70": 0, "nubra_watch": 0, "recurrence_boosted": 0}
    w = _weights()
    today = now.date()

    for c in convs:
        if c["is_nubra_watch"]:
            stats["nubra_watch"] += 1
            continue
        existing = db.one(
            "SELECT id, status FROM opportunities WHERE source=%s AND thread_id=%s",
            (c["source"], c["thread_id"]),
        )
        if existing and existing["status"] in ("acted", "dismissed"):
            continue

        rows = _thread_rows(c["source"], c["thread_id"])
        enriched = [r for r in rows if r.get("intent") and not r.get("is_noise")]
        if not enriched:
            continue
        stats["scored"] += 1

        insight, rel_base, opp_type = _matched_insight(enriched)
        relevance = min(rel_base + _seo_boost(rows, kws), 1.0)
        age_h = max((now - (c["last_seen"] or now)).total_seconds() / 3600.0, 0.0)
        conv_accel = c["velocity"] or 0.0
        freshness = 0.5 * min(conv_accel / 4.0, 1.0) + 0.5 * math.exp(-age_h / 12.0)

        s = (w["freshness_velocity"] * freshness + w["relevance"] * relevance
             + w["reach"] * _reach(rows) + w["opportunity_type"] * opp_type
             + w["author_quality"] * _author_quality(rows))
        priority = 100.0 * s

        # recurrence boost — NEW thread on a topic already featured today (§1.1)
        if not existing and c["dominant_topic_key"]:
            td = db.one(
                "SELECT headsup_count FROM topic_daily WHERE topic_key=%s AND day=%s",
                (c["dominant_topic_key"], today),
            )
            n = (td or {}).get("headsup_count") or 0
            if n >= 1:
                reg = settings.registry["recommend"]
                boost = 1 + min(reg["recurrence_boost_per_hit"] * n, reg["recurrence_boost_cap"])
                priority *= boost
                insight["recurrence"] = {"topic_key": c["dominant_topic_key"],
                                         "nth_thread_today": n + 1,
                                         "boost": round(boost, 2)}
                stats["recurrence_boosted"] += 1

        # Engagement gate: a thread nobody liked/replied to can't be a TOP action
        # (still allowed into the secondary pool).
        inter = _interactions(rows)
        min_inter = settings.registry["recommend"].get("action_min_interactions", 10)
        headsup_bar = settings.registry["recommend"]["thresholds"]["headsup"]
        if inter < min_inter and priority >= headsup_bar:
            priority = headsup_bar - 1

        priority = int(min(priority, 100))
        if priority < settings.registry["recommend"]["thresholds"]["secondary"]:
            continue

        insight["interactions"] = inter
        insight["topic_key"] = insight.get("topic_key") or c["dominant_topic_key"]
        db.execute(
            """
            INSERT INTO opportunities (source, thread_id, day, priority, matched_insight)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (source, thread_id) DO UPDATE SET
                priority = EXCLUDED.priority,
                matched_insight = EXCLUDED.matched_insight,
                day = EXCLUDED.day,
                updated_at = now()
            WHERE opportunities.status = 'suggested'
            """,
            (c["source"], c["thread_id"], today, priority, db.jsonb(insight)),
        )
        stats["persisted"] += 1
        if priority >= settings.registry["recommend"]["thresholds"]["headsup"]:
            stats["new_ge70"] += 1

    from community.store.repositories import advance_state
    advance_state("score", "", items=stats["persisted"])
    return stats
