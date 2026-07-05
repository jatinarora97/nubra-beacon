"""Read-API (FastAPI) — LLD-03 §7, v2 contract for the React frontend (webapp/).

Product-shaped responses so the frontend stays thin: server-computed
`why_engage` sentences, voice niches, sample quotes, flattened briefs, and a
/overview endpoint for the landing page. Reads only (+ INSERT feedback,
UPDATE opportunities status columns). On prod an OIDC proxy injects
X-Auth-Request-Email; locally we fall back to "local-dev".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import Body, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from community.store import db

app = FastAPI(title="Nubra Community Manager — read-API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
API = "/api/v1"

DISMISS_REASONS = ("not_relevant", "already_handled", "too_late", "too_risky", "other")

KIND_LABELS = {"broker_issue": "COMPETITOR ISSUE", "feature_request": "FEATURE REQUEST",
               "question": "QUESTION", "comparison": "COMPARISON", "topic": "TOPIC"}


def _problem(status: int, detail: str) -> JSONResponse:  # RFC-7807-ish
    return JSONResponse(status_code=status,
                        content={"type": "about:blank", "status": status, "detail": detail})


def _who(email: str | None) -> str:
    return email or "local-dev"  # prod: reject if absent instead


def _lim(limit: int) -> int:
    return max(1, min(limit, 100))


# ── shared lookups (tiny tables — fetched per request batch, not per row) ────

def _taxonomy_labels() -> dict[str, str]:
    return {r["topic_key"]: r["label"] for r in
            db.query("SELECT topic_key, label FROM topic_taxonomy")}


def _capabilities() -> list[tuple[str, list[str]]]:
    rows = db.query("SELECT feature, seo_keywords FROM nubra_features WHERE is_current")
    return [(r["feature"], [k.lower() for k in (r["seo_keywords"] or [])]) for r in rows]


def _match_capability(caps: list[tuple[str, list[str]]], *texts: str | None) -> str | None:
    hay = " ".join(t for t in texts if t).lower()
    if not hay:
        return None
    best: tuple[int, str] | None = None  # longest matching keyword wins (most specific)
    for feat, kws in caps:
        for kw in kws:
            if kw in hay and (best is None or len(kw) > best[0]):
                best = (len(kw), feat)
    return best[1] if best else None


def _why_engage(insight: dict, velocity: float | None, labels: dict[str, str],
                caps: list[tuple[str, list[str]]]) -> str:
    kind = insight.get("kind", "topic")
    topic_label = labels.get(insight.get("topic_key") or "", insight.get("topic_key") or "the topic")
    phrase = insight.get("feature_phrase") or ""
    if len(phrase) > 60:  # cut at a word boundary, not mid-word
        phrase = phrase[:60].rsplit(" ", 1)[0] + "…"
    if kind == "broker_issue":
        base = f"Competitor complaint about {insight.get('broker', 'a broker')}" + (
            f" ({insight.get('issue_key', '').replace('_', ' ')})" if insight.get("issue_key") else "")
    elif kind == "feature_request":
        base = f"Feature ask we can speak to — {phrase or topic_label}"
    elif kind == "question":
        base = f"Question in our wheelhouse — {topic_label}"
    elif kind == "comparison":
        base = f"Broker comparison in play — {topic_label}"
    else:
        base = f"Active discussion on {topic_label}"
    bits = [base]
    if insight.get("interactions"):
        bits.append(f"{insight['interactions']} interactions")
    if velocity and velocity >= 2:
        bits.append("thread accelerating")
    cap = _match_capability(caps, phrase, topic_label)
    if cap:
        bits.append(f"we have: {cap}")
    return "; ".join(bits)


def _decorate_opportunity(r: dict, labels: dict, caps: list) -> dict:
    insight = r.get("insight") or {}
    kind = insight.get("kind", "topic")
    timing = r.pop("recommended_timing", None) or {}
    now = datetime.now(timezone.utc)
    last_seen = r.pop("last_seen", None)
    r.update({
        "kind": kind,
        "kind_label": KIND_LABELS.get(kind, kind.replace("_", " ").upper()),
        "interactions": insight.get("interactions"),
        "why_engage": _why_engage(insight, r.pop("velocity", None), labels, caps),
        "age_h": round((now - last_seen).total_seconds() / 3600, 1) if last_seen else None,
        "when_action": timing.get("action"),
        "when_window": timing.get("window"),
        "when_why": timing.get("why"),
    })
    return r


_OPP_SELECT = """
    SELECT o.id, o.source, o.thread_id, o.day, o.priority, o.matched_insight AS insight,
           o.brand_reply, o.rep_reply, o.recommended_timing, o.status,
           o.dismissed_reason, si.url, left(si.text, 200) AS title,
           c.velocity, c.last_seen
    FROM opportunities o
    LEFT JOIN conversations c ON (c.source, c.thread_id) = (o.source, o.thread_id)
    LEFT JOIN social_items si ON si.item_id = c.root_item_id
"""


def _sample_items(item_ids: list[int], cap: int) -> list[dict]:
    if not item_ids:
        return []
    rows = db.query(
        "SELECT left(text, 200) AS text, url, source FROM social_items "
        "WHERE item_id = ANY(%s) ORDER BY (engagement->>'score')::float DESC NULLS LAST "
        "LIMIT %s", (item_ids, cap))
    return rows


# ── overview (landing page) ──────────────────────────────────────────────────

@app.get(API + "/overview")
def overview():
    today = datetime.now(timezone.utc).date()
    labels, caps = _taxonomy_labels(), _capabilities()

    headline_row = db.one(
        "SELECT payload FROM roundups WHERE period='daily' ORDER BY date DESC LIMIT 1")
    headline = (headline_row or {}).get("payload", {}).get("headline")

    def _n(sql: str, params: tuple = ()) -> int:
        return (db.one(sql, params) or {}).get("n", 0)

    kpis = {
        "items_today": _n(
            "SELECT count(*) AS n FROM social_items WHERE ingested_at::date = %s", (today,)),
        "analyzed_today": _n(
            "SELECT count(*) AS n FROM item_enrichment WHERE enriched_at::date = %s", (today,)),
        "actions_on_table": _n(
            "SELECT count(*) AS n FROM opportunities WHERE status='suggested' AND priority >= 40"),
        "new_high_priority_today": _n(
            "SELECT count(*) AS n FROM opportunities WHERE status='suggested' "
            "AND priority >= 60 AND updated_at::date = %s", (today,)),
        "nubra_mentions_24h": _n(
            "SELECT count(*) AS n FROM conversations WHERE is_nubra_watch "
            "AND last_seen > now() - interval '24 hours'"),
        "drafts_ready": _n(
            "SELECT count(*) AS n FROM opportunities WHERE status='suggested' "
            "AND brand_reply IS NOT NULL"),
    }

    top_actions = [
        _decorate_opportunity(r, labels, caps)
        for r in db.query(_OPP_SELECT + " WHERE o.status='suggested' "
                          "ORDER BY o.priority DESC LIMIT 3")
    ]
    for a in top_actions:
        a["title"] = (a.get("title") or "").replace("\n", " ")[:140]
        for k in ("brand_reply", "rep_reply", "insight", "day", "thread_id", "source",
                  "status", "dismissed_reason", "when_action", "when_window", "when_why"):
            a.pop(k, None)

    movers_day = (db.one("SELECT max(day) AS d FROM topic_daily") or {}).get("d") or today
    top_movers = db.query(
        "SELECT t.topic_key, x.label, t.count FROM topic_daily t "
        "LEFT JOIN topic_taxonomy x ON x.topic_key = t.topic_key "
        "WHERE t.day = %s AND t.topic_key NOT LIKE 'other:%%' "
        "ORDER BY t.velocity_z DESC NULLS LAST, t.count DESC LIMIT 3", (movers_day,))

    return {"date": str(today), "headline": headline, "kpis": kpis,
            "top_actions": top_actions, "top_movers": top_movers}


# ── core reads ───────────────────────────────────────────────────────────────

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
    for r in rows:  # flatten + dedup the per-day sample arrays, resolve quotes
        nested = r.pop("samples_nested") or []
        ids = sorted({i for arr in nested for i in (arr or [])})
        r["sample_item_ids"] = ids
        r["samples"] = _sample_items(ids, 2)
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
               jsonb_agg(to_jsonb(brokers_mentioned)) AS brokers_nested,
               jsonb_agg(to_jsonb(sample_item_ids)) AS samples_nested
        FROM feature_rollup WHERE day BETWEEN %s AND %s
        GROUP BY feature_key HAVING count(DISTINCT day) >= %s
        ORDER BY sum(count) DESC
        """, (start, end, min_days))
    for r in rows:
        r["brokers_mentioned"] = sorted(
            {b for arr in (r.pop("brokers_nested") or []) for b in (arr or []) if b})
        ids = sorted({i for arr in (r.pop("samples_nested") or []) for i in (arr or [])})
        r["samples"] = _sample_items(ids, 3)
    return rows


@app.get(API + "/voices")
def voices(limit: int = 20, min_score: float = 0):
    rows = db.query(
        """
        SELECT s.author_id, a.handle, a.source, a.followers, s.voice_score,
               s.contributions, s.communities, s.relevance, s.authenticity_flag
        FROM author_stats s JOIN authors a ON a.author_id = s.author_id
        WHERE s.voice_score >= %s ORDER BY s.voice_score DESC LIMIT %s
        """, (min_score, _lim(limit)))
    ids = [v["author_id"] for v in rows]
    niches: dict[int, list[str]] = {}
    threads: dict[int, dict] = {}
    if ids:
        for n in db.query(
            """
            SELECT si.author_id, x.label, count(*) AS n
            FROM social_items si
            JOIN item_enrichment e ON e.item_id = si.item_id AND NOT e.is_noise
            JOIN topic_taxonomy x ON x.topic_key = e.topic_key
            WHERE si.author_id = ANY(%s)
            GROUP BY si.author_id, x.label ORDER BY count(*) DESC
            """, (ids,)):
            niches.setdefault(n["author_id"], []).append(n["label"])
        for t in db.query(
            """
            SELECT DISTINCT ON (author_id) author_id,
                   left(text, 120) AS title, url
            FROM social_items
            WHERE author_id = ANY(%s) AND duplicate_of IS NULL
              AND source_type IN ('post', 'tweet')
            ORDER BY author_id, created_at DESC
            """, (ids,)):
            threads[t["author_id"]] = {"title": (t["title"] or "").replace("\n", " "),
                                       "url": t["url"]}
    for v in rows:
        v["profile_url"] = (f"https://x.com/{v['handle']}" if v["source"] == "twitter"
                            else f"https://www.reddit.com/user/{v['handle']}")
        v["niche_topics"] = niches.get(v["author_id"], [])[:3]
        v["recent_thread"] = threads.get(v["author_id"])
        niche = v["niche_topics"][0] if v["niche_topics"] else None
        v["why"] = (f"{v['contributions']} relevant posts across "
                    f"{v['communities']} communit{'ies' if v['communities'] != 1 else 'y'} in 30d"
                    + (f", consistently on {niche.lower()}" if niche else ""))
    return rows


@app.get(API + "/opportunities")
def opportunities(date_: date | None = Query(None, alias="date"),
                  status: str | None = None, min_priority: int = 0, limit: int = 50):
    labels, caps = _taxonomy_labels(), _capabilities()
    q = _OPP_SELECT + " WHERE o.priority >= %(minp)s"
    params: dict = {"minp": min_priority, "limit": _lim(limit)}
    if date_:
        q += " AND o.day = %(day)s"
        params["day"] = date_
    if status:
        q += " AND o.status = %(status)s"
        params["status"] = status
    q += " ORDER BY o.priority DESC LIMIT %(limit)s"
    return [_decorate_opportunity(r, labels, caps) for r in db.query(q, params)]


@app.get(API + "/content-proposals")
def content_proposals(date_: date | None = Query(None, alias="date")):
    if date_ is None:
        row = db.one("SELECT max(day) AS d FROM content_proposals")
        date_ = row["d"] if row and row["d"] else datetime.now(timezone.utc).date()
    rows = db.query(
        "SELECT day, rank, format AS treatment, format_family, platform, hook, "
        "outline, why, rides_signal, recommended_timing "
        "FROM content_proposals WHERE day=%s ORDER BY rank", (date_,))
    for r in rows:
        brief = r.pop("outline", None) or {}
        if isinstance(brief, list):  # pre-taxonomy rows stored beats as a bare list
            brief = {"beats": brief}
        timing = r.pop("recommended_timing", None) or {}
        r.update({
            "beats": brief.get("beats", []),
            "caption": brief.get("caption"),
            "hashtags": brief.get("hashtags", []),
            "cta": brief.get("cta"),
            "visual_direction": brief.get("visual_direction"),
            "platform_why": brief.get("platform_why"),
            "window": timing.get("window"),
        })
    return rows


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
          source: str | None = None,
          sort: Literal["engagement", "recent"] = "engagement",
          limit: int = 20, offset: int = 0):
    sql = """
        SELECT si.source, si.external_id, si.thread_id, left(si.text, 300) AS text,
               si.url, si.created_at, si.ingested_at, si.engagement,
               a.handle AS author,
               e.topic_key, e.intent, e.audience, e.sentiment, e.entities,
               (SELECT count(*) FROM social_items d WHERE d.duplicate_of = si.item_id)::int
                 AS duplicate_count
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.duplicate_of IS NULL AND COALESCE(e.is_noise, false) = false
          AND (si.engagement->>'score')::float >= %(mine)s
    """
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
    order = ("(si.engagement->>'score')::float DESC NULLS LAST, si.created_at DESC"
             if sort == "engagement" else "si.created_at DESC")
    sql += f" ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s"
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


# ── writes (the only two) ────────────────────────────────────────────────────

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
