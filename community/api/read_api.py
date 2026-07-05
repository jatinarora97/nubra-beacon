"""Read-API (FastAPI) — LLD-03 §7. Base /api/v1.

Reads only (+ INSERT feedback, UPDATE opportunities status columns). On prod an
OIDC proxy injects X-Auth-Request-Email; locally we fall back to "local-dev"
(the header wiring below is the one-liner that changes).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from community.store import db

app = FastAPI(title="Nubra Community Manager — read-API", version="1.0")
API = "/api/v1"

DISMISS_REASONS = ("not_relevant", "already_handled", "too_late", "too_risky", "other")


def _problem(status: int, detail: str) -> JSONResponse:  # RFC-7807-ish
    return JSONResponse(status_code=status,
                        content={"type": "about:blank", "status": status, "detail": detail})


def _who(email: str | None) -> str:
    return email or "local-dev"  # prod: reject if absent instead


def _lim(limit: int) -> int:
    return max(1, min(limit, 100))


@app.get(API + "/trends")
def trends(date_: date | None = Query(None, alias="date"),
           window: Literal["1d", "7d"] = "7d", limit: int = 20):
    end = date_ or datetime.now(timezone.utc).date()
    start = end - timedelta(days=6 if window == "7d" else 0)
    return db.query(
        """
        SELECT t.topic_key, max(x.label) AS label, sum(t.count)::int AS count,
               max(t.velocity_z) AS velocity_z, max(t.spread)::int AS spread,
               sum(t.engagement_sum)::bigint AS engagement_sum
        FROM topic_daily t LEFT JOIN topic_taxonomy x ON x.topic_key = t.topic_key
        WHERE t.day BETWEEN %s AND %s AND t.topic_key NOT LIKE 'other:%%'
        GROUP BY t.topic_key
        ORDER BY max(t.velocity_z) DESC NULLS LAST, sum(t.count) DESC LIMIT %s
        """, (start, end, _lim(limit)))


@app.get(API + "/issues")
def issues(broker: str | None = None,
           from_: date | None = Query(None, alias="from"),
           to: date | None = Query(None, alias="to")):
    end = to or datetime.now(timezone.utc).date()
    start = from_ or end - timedelta(days=6)
    rows = db.query(
        """
        SELECT broker, issue_key,
               jsonb_agg(jsonb_build_object('day', day, 'count', count) ORDER BY day) AS day_counts,
               max(severity) AS severity, avg(sentiment_avg) AS sentiment_avg,
               jsonb_agg(to_jsonb(sample_item_ids)) AS samples_nested
        FROM issue_rollup WHERE day BETWEEN %s AND %s
        GROUP BY broker, issue_key
        ORDER BY sum(count) DESC
        """, (start, end))
    for r in rows:  # flatten + dedup the per-day sample arrays
        nested = r.pop("samples_nested") or []
        r["sample_item_ids"] = sorted({i for arr in nested for i in (arr or [])})
    if broker:
        rows = [r for r in rows if r["broker"] == broker]
    return rows


@app.get(API + "/features")
def features(from_: date | None = Query(None, alias="from"),
             to: date | None = Query(None, alias="to"), min_days: int = 1):
    end = to or datetime.now(timezone.utc).date()
    start = from_ or end - timedelta(days=6)
    rows = db.query(
        """
        SELECT feature_key, max(canonical_label) AS label, sum(count)::int AS count,
               count(DISTINCT day)::int AS days_requested,
               jsonb_agg(to_jsonb(brokers_mentioned)) AS brokers_nested
        FROM feature_rollup WHERE day BETWEEN %s AND %s
        GROUP BY feature_key HAVING count(DISTINCT day) >= %s
        ORDER BY sum(count) DESC
        """, (start, end, min_days))
    for r in rows:  # flatten + dedup the per-day broker arrays
        nested = r.pop("brokers_nested") or []
        r["brokers_mentioned"] = sorted({b for arr in nested for b in (arr or []) if b})
    return rows


@app.get(API + "/voices")
def voices(limit: int = 20, min_score: float = 0):
    rows = db.query(
        """
        SELECT s.author_id, a.handle, a.source, s.voice_score, s.contributions,
               s.authenticity_flag
        FROM author_stats s JOIN authors a ON a.author_id = s.author_id
        WHERE s.voice_score >= %s ORDER BY s.voice_score DESC LIMIT %s
        """, (min_score, _lim(limit)))
    for v in rows:
        v["profile_url"] = (f"https://x.com/{v['handle']}" if v["source"] == "twitter"
                            else f"https://www.reddit.com/user/{v['handle']}")
    return rows


@app.get(API + "/opportunities")
def opportunities(date_: date | None = Query(None, alias="date"),
                  status: str | None = None, min_priority: int = 0, limit: int = 50):
    q = """
        SELECT o.id, o.source, o.thread_id, o.day, o.priority, o.matched_insight AS insight,
               o.brand_reply, o.rep_reply, o.recommended_timing, o.status,
               o.dismissed_reason, si.url, left(si.text, 200) AS title
        FROM opportunities o
        LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id)
        LEFT JOIN social_items si ON si.item_id = c.root_item_id
        WHERE o.priority >= %(minp)s
    """
    params: dict = {"minp": min_priority, "limit": _lim(limit)}
    if date_:
        q += " AND o.day = %(day)s"
        params["day"] = date_
    if status:
        q += " AND o.status = %(status)s"
        params["status"] = status
    q += " ORDER BY o.priority DESC LIMIT %(limit)s"
    return db.query(q, params)


@app.get(API + "/content-proposals")
def content_proposals(date_: date | None = Query(None, alias="date")):
    if date_ is None:
        row = db.one("SELECT max(day) AS d FROM content_proposals")
        date_ = row["d"] if row and row["d"] else datetime.now(timezone.utc).date()
    return db.query(
        "SELECT day, rank, format, hook, outline, why, rides_signal, recommended_timing "
        "FROM content_proposals WHERE day=%s ORDER BY rank", (date_,))


@app.get(API + "/roundups")
def roundups(period: Literal["daily", "weekly"] = "daily",
             date_: date | None = Query(None, alias="date")):
    if date_ is None:
        row = db.one("SELECT max(date) AS d FROM roundups WHERE period=%s", (period,))
        if not row or not row["d"]:
            raise HTTPException(404, "no roundup yet")
        date_ = row["d"]
    row = db.one("SELECT period, date, payload, delivery FROM roundups "
                 "WHERE period=%s AND date=%s", (period, date_))
    if not row:
        raise HTTPException(404, f"no {period} roundup for {date_}")
    return row


@app.get(API + "/items")
def items(topic: str | None = None, broker: str | None = None,
          intent: str | None = None, audience: str | None = None,
          q: str | None = None, min_engagement: float = 0,
          source: str | None = None, limit: int = 20, offset: int = 0):
    sql = """
        SELECT si.source, si.external_id, si.thread_id, left(si.text, 300) AS text,
               si.url, si.created_at, si.engagement, a.handle AS author,
               e.topic_key, e.intent, e.audience, e.sentiment, e.entities,
               (SELECT count(*) FROM social_items d WHERE d.duplicate_of = si.item_id)::int
                 AS duplicate_count
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.duplicate_of IS NULL AND COALESCE(e.is_noise, false) = false
          AND (si.engagement->>'score')::float >= %(minე)s
    """.replace("%(minე)s", "%(mine)s")
    params: dict = {"mine": min_engagement, "limit": _lim(limit), "offset": max(offset, 0)}
    for name, val, clause in (
        ("topic", topic, " AND e.topic_key = %(topic)s"),
        ("intent", intent, " AND e.intent = %(intent)s"),
        ("audience", audience, " AND e.audience = %(audience)s"),
        ("source", source, " AND si.source = %(source)s"),
    ):
        if val:
            sql += clause
            params[name] = val
    if broker:
        sql += " AND e.entities::text ILIKE %(broker)s"
        params["broker"] = f"%{broker}%"
    if q:
        sql += " AND si.text ILIKE %(q)s"
        params["q"] = f"%{q}%"
    sql += " ORDER BY si.created_at DESC LIMIT %(limit)s OFFSET %(offset)s"
    return db.query(sql, params)


@app.get(API + "/items/{source}/{external_id}")
def item_detail(source: str, external_id: str):
    item = db.one(
        """
        SELECT si.*, a.handle AS author_handle, e.topic_key, e.intent, e.audience,
               e.sentiment, e.entities, e.is_noise, e.model AS enrich_model
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.source = %s AND si.external_id = %s
        """, (source, external_id))
    if not item:
        raise HTTPException(404, "item not found")
    siblings = db.query(
        """
        SELECT si.external_id, si.source_type, left(si.text, 200) AS text,
               a.handle AS author, si.created_at
        FROM social_items si JOIN authors a ON a.author_id = si.author_id
        WHERE si.source = %s AND si.thread_id = %s AND si.external_id <> %s
        ORDER BY si.created_at LIMIT 50
        """, (source, item["thread_id"], external_id))
    item.pop("minhash_sig", None)
    return {"item": item, "thread_siblings": siblings}


@app.post(API + "/feedback", status_code=201)
def feedback(body: dict = Body(...),
             x_auth_request_email: str | None = Header(None)):
    if not body.get("object_ref") or not body.get("category"):
        raise HTTPException(400, "object_ref and category are required")
    db.execute(
        "INSERT INTO feedback (object_ref, category, free_text, submitted_by) "
        "VALUES (%s, %s, %s, %s)",
        (db.jsonb(body["object_ref"]), body["category"], body.get("free_text"),
         _who(x_auth_request_email)))
    return {"ok": True}


@app.post(API + "/opportunities/{opp_id}/status")
def set_status(opp_id: int, body: dict = Body(...),
               x_auth_request_email: str | None = Header(None)):
    status = body.get("status")
    reason = body.get("dismissed_reason")
    if status not in ("acted", "dismissed"):
        raise HTTPException(400, "status must be acted|dismissed")
    if status == "dismissed" and reason not in DISMISS_REASONS:
        raise HTTPException(400, f"dismissed_reason required, one of {DISMISS_REASONS}")
    row = db.one("SELECT status FROM opportunities WHERE id=%s", (opp_id,))
    if not row:
        raise HTTPException(404, "opportunity not found")
    if row["status"] != "suggested":
        raise HTTPException(409, f"status is already {row['status']} — transition is one-way")
    db.execute(
        "UPDATE opportunities SET status=%s, dismissed_reason=%s, "
        "status_updated_by=%s, status_updated_at=now() WHERE id=%s",
        (status, reason if status == "dismissed" else None,
         _who(x_auth_request_email), opp_id))
    return {"ok": True, "id": opp_id, "status": status}
