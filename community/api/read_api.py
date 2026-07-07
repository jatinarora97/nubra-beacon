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
from community.api.discover_api import router as discover_router  # noqa: E402
app.include_router(discover_router)
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


# ── health (offline banner probe — must stay dependency-light) ───────────────

@app.get(API + "/health")
def health():
    try:
        db.query("SELECT 1")
        return {"ok": True, "db": True}
    except Exception:  # noqa: BLE001 — API up, DB down is still "degraded"
        return {"ok": True, "db": False}


def _freshness() -> dict:
    """Last-updated per source + pipeline watermarks + the next scheduled runs
    (from the cron plan; flags when the schedule isn't actually installed)."""
    import subprocess
    from zoneinfo import ZoneInfo

    per_source = {r["source"]: r["last"] for r in db.query(
        "SELECT source, max(ingested_at) AS last FROM social_items GROUP BY source")}
    watermarks = {r["stage"]: r["wm"] for r in db.query(
        "SELECT stage, max(watermark) AS wm FROM pipeline_state GROUP BY stage")}

    try:
        crontab = subprocess.run(["crontab", "-l"], capture_output=True,
                                 text=True, timeout=3).stdout
    except Exception:  # noqa: BLE001
        crontab = ""
    installed = "run-local" in crontab

    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    nxt = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while nxt.hour in (1, 2, 3, 4, 5):  # cron pauses 01-05 IST (06:00 = morning build)
        nxt += timedelta(hours=1)
    morning = (now.replace(hour=6, minute=0, second=0, microsecond=0)
               + timedelta(days=1 if now.hour >= 6 else 0))
    wm = watermarks.get("enrich") or watermarks.get("aggregate")
    return {
        "sources": {k: v.isoformat() for k, v in per_source.items() if v},
        "enriched_up_to": wm.isoformat() if wm else None,
        "schedule_installed": installed,
        "next_hourly_run": nxt.isoformat(),
        "next_morning_build": morning.isoformat(),
    }


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
        # last-hour deltas — the hourly cadence the tiles should surface
        "items_last_hour": _n(
            "SELECT count(*) AS n FROM social_items "
            "WHERE ingested_at > now() - interval '1 hour'"),
        "analyzed_last_hour": _n(
            "SELECT count(*) AS n FROM item_enrichment "
            "WHERE enriched_at > now() - interval '1 hour'"),
        "new_actions_last_hour": _n(
            "SELECT count(*) AS n FROM opportunities WHERE status='suggested' "
            "AND updated_at > now() - interval '1 hour'"),
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

    llm_last = db.one(
        """
        SELECT run_id, round(sum(cost_usd)::numeric, 6) AS cost_usd,
               count(*) AS calls, count(DISTINCT stage) AS stages,
               max(ts) AS ts
        FROM llm_usage
        WHERE run_id = (SELECT run_id FROM llm_usage ORDER BY ts DESC LIMIT 1)
        GROUP BY run_id
        """)

    return {"date": str(today), "headline": headline, "kpis": kpis,
            "top_actions": top_actions, "top_movers": top_movers,
            "freshness": _freshness(), "llm_last_run": llm_last}


# ── llm usage (N6 — cost surfacing; tracing writes via community/llm/trace) ──

@app.get(API + "/llm-usage/summary")
def llm_usage_summary(days: int = 30):
    days = max(1, min(days, 180))
    by_day = db.query(
        """
        SELECT ts::date AS day, round(sum(cost_usd)::numeric, 6) AS cost_usd,
               sum(input_tokens)::bigint AS input_tokens,
               sum(output_tokens)::bigint AS output_tokens, count(*) AS calls
        FROM llm_usage WHERE ts > now() - make_interval(days => %s)
        GROUP BY 1 ORDER BY 1
        """, (days,))
    by_stage = db.query(
        """
        SELECT stage, round(sum(cost_usd)::numeric, 6) AS cost_usd,
               count(*) AS calls, sum(input_tokens + output_tokens)::bigint AS tokens
        FROM llm_usage WHERE ts > now() - make_interval(days => %s)
        GROUP BY stage ORDER BY sum(cost_usd) DESC NULLS LAST
        """, (days,))
    by_model = db.query(
        """
        SELECT model, batch, round(sum(cost_usd)::numeric, 6) AS cost_usd,
               count(*) AS calls, sum(input_tokens)::bigint AS input_tokens,
               sum(output_tokens)::bigint AS output_tokens
        FROM llm_usage WHERE ts > now() - make_interval(days => %s)
        GROUP BY model, batch ORDER BY model, batch
        """, (days,))
    totals = db.one(
        """
        SELECT round(sum(cost_usd)::numeric, 6) AS cost_usd, count(*) AS calls,
               sum(input_tokens)::bigint AS input_tokens,
               sum(output_tokens)::bigint AS output_tokens,
               round(sum(cost_usd) FILTER (WHERE batch)::numeric, 6) AS batch_cost,
               count(*) FILTER (WHERE batch) AS batch_calls,
               count(*) FILTER (WHERE langfuse_trace_id IS NOT NULL) AS traced_calls,
               count(*) FILTER (WHERE cost_usd IS NULL) AS unpriced_calls
        FROM llm_usage WHERE ts > now() - make_interval(days => %s)
        """, (days,)) or {}
    runs = db.query(
        """
        SELECT run_id, min(ts) AS started, max(ts) AS ended,
               count(*) AS calls, count(DISTINCT stage) AS stages,
               array_agg(DISTINCT stage) AS stage_list,
               sum(input_tokens + output_tokens)::bigint AS tokens,
               round(sum(cost_usd)::numeric, 6) AS cost_usd
        FROM llm_usage GROUP BY run_id ORDER BY max(ts) DESC LIMIT 15
        """)
    return {"window_days": days, "totals": totals, "by_day": by_day,
            "by_stage": by_stage, "by_model": by_model, "recent_runs": runs}


@app.get(API + "/llm-usage/last-run")
def llm_usage_last_run():
    last = db.one("SELECT run_id FROM llm_usage ORDER BY ts DESC LIMIT 1")
    if not last:
        raise HTTPException(404, "no LLM usage recorded yet")
    rows = db.query(
        """
        SELECT stage, purpose, model, batch, count(*) AS calls,
               sum(input_tokens)::bigint AS input_tokens,
               sum(output_tokens)::bigint AS output_tokens,
               round(sum(cost_usd)::numeric, 6) AS cost_usd
        FROM llm_usage WHERE run_id = %s
        GROUP BY stage, purpose, model, batch ORDER BY min(ts)
        """, (last["run_id"],))
    total = db.one(
        "SELECT round(sum(cost_usd)::numeric, 6) AS cost_usd, count(*) AS calls, "
        "min(ts) AS started, max(ts) AS ended FROM llm_usage WHERE run_id = %s",
        (last["run_id"],))
    return {"run_id": last["run_id"], "total": total, "breakdown": rows}


# ── nubra mentions (the positive side; complaints live in /issues) ──────────

@app.get(API + "/nubra-mentions")
def nubra_mentions(days: int = 7, limit: int = 30):
    """People talking about Nubra: positive/neutral quotes + KPIs. Negative
    items are counted (visibility) but rendered on the Broker-issues page."""
    days = max(1, min(days, 90))
    base = """
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.duplicate_of IS NULL AND COALESCE(e.is_noise, false) = false
          AND si.text ~* '(?<![a-z])nubra(?![a-z])'
    """
    kpi = db.one(f"""
        SELECT count(*) FILTER (WHERE si.created_at > now() - interval '24 hours') AS h24,
               count(*) FILTER (WHERE si.created_at > now() - interval '%s days') AS win,
               count(*) FILTER (WHERE si.created_at > now() - interval '%s days'
                                AND COALESCE(e.sentiment, 0) >= 0) AS win_pos
        {base}""" % (days, days)) or {}
    positives = db.query(f"""
        SELECT si.source, si.external_id, left(si.text, 300) AS text, si.url,
               si.created_at, a.handle AS author, e.sentiment, e.intent, e.topic_key
        {base}
          AND COALESCE(e.sentiment, 0) >= 0
          AND si.created_at > now() - interval '{days} days'
        ORDER BY e.sentiment DESC NULLS LAST, si.created_at DESC LIMIT %s
        """, (_lim(limit),))
    complaints = db.one(
        "SELECT COALESCE(sum(count), 0) AS n FROM issue_rollup "
        "WHERE broker = 'nubra' AND day > current_date - %s", (days,)) or {}
    return {
        "window_days": days,
        "kpis": {
            "mentions_24h": kpi.get("h24", 0),
            "mentions_window": kpi.get("win", 0),
            "positive_share": (round(kpi["win_pos"] / kpi["win"], 2)
                               if kpi.get("win") else None),
            "complaints_window": complaints.get("n", 0),
        },
        "positives": positives,
    }


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
        SELECT broker, issue_key, sum(count)::int AS count,
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
        r["samples"] = _sample_items(ids, 5)
    if broker:
        rows = [r for r in rows if r["broker"] == broker]
    # full watched-broker list so the heatmap can show clean rows (0 complaints)
    from community.reference.taxonomy import BROKER_GAZETTEER
    return {"segments": rows, "brokers": list(BROKER_GAZETTEER)}


@app.get(API + "/features")
def features(from_: date | None = Query(None, alias="from"),
             to: date | None = Query(None, alias="to"), min_days: int = 1):
    end = to or datetime.now(timezone.utc).date()
    start = from_ or end - timedelta(days=6)
    rows = db.query(
        """
        SELECT fr.feature_key, max(fr.canonical_label) AS label, sum(fr.count)::int AS count,
               count(DISTINCT fr.day)::int AS days_requested,
               jsonb_agg(to_jsonb(fr.brokers_mentioned)) AS brokers_nested,
               jsonb_agg(to_jsonb(fr.sample_item_ids)) AS samples_nested,
               COALESCE((SELECT sum((si.engagement->>'score')::float)
                         FROM feature_item_map m
                         JOIN social_items si ON si.item_id = m.item_id
                         WHERE m.feature_key = fr.feature_key
                           AND m.day BETWEEN %s AND %s), 0) AS engagement
        FROM feature_rollup fr WHERE fr.day BETWEEN %s AND %s
        GROUP BY fr.feature_key HAVING count(DISTINCT fr.day) >= %s
        ORDER BY engagement DESC, sum(fr.count) DESC
        """, (start, end, start, end, min_days))
    for r in rows:
        r["brokers_mentioned"] = sorted(
            {b for arr in (r.pop("brokers_nested") or []) for b in (arr or []) if b})
        ids = sorted({i for arr in (r.pop("samples_nested") or []) for i in (arr or [])})
        r["samples"] = _sample_items(ids, 3)
        r["engagement"] = round(r["engagement"], 1)
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


def _flatten_proposal(r: dict) -> dict:
    brief = r.pop("outline", None) or {}
    if isinstance(brief, list):  # pre-taxonomy rows stored beats as a bare list
        brief = {"beats": brief}
    timing = r.pop("recommended_timing", None) or {}
    revisions = brief.get("revisions", [])
    r.update({
        "beats": brief.get("beats", []),
        "caption": brief.get("caption"),
        "hashtags": brief.get("hashtags", []),
        "cta": brief.get("cta"),
        "visual_direction": brief.get("visual_direction"),
        "platform_why": brief.get("platform_why"),
        "window": timing.get("window"),
        "revisions_count": len(revisions),
        "last_revised_by": revisions[-1].get("by") if revisions else None,
    })
    return r


_PROPOSAL_SELECT = ("SELECT day, rank, format AS treatment, format_family, platform, "
                    "hook, outline, why, rides_signal, recommended_timing "
                    "FROM content_proposals")


@app.get(API + "/content-proposals")
def content_proposals(date_: date | None = Query(None, alias="date")):
    if date_ is None:
        row = db.one("SELECT max(day) AS d FROM content_proposals")
        date_ = row["d"] if row and row["d"] else datetime.now(timezone.utc).date()
    return [_flatten_proposal(r) for r in
            db.query(_PROPOSAL_SELECT + " WHERE day=%s ORDER BY rank", (date_,))]


@app.get(API + "/content-taxonomy")
def content_taxonomy():
    from community.config.settings import settings
    c = settings.registry.get("content", {})
    return {"format_families": c.get("format_families", []),
            "platforms": c.get("platforms", [])}


@app.post(API + "/content-proposals/revise")
def revise_proposal(body: dict = Body(...),
                    x_auth_request_email: str | None = Header(None)):
    from community.recommend.revise import revise_brief
    rank = body.get("rank")
    if not isinstance(rank, int):
        raise HTTPException(400, "rank (int) is required")
    day_ = body.get("day")
    if day_ is None:
        row = db.one("SELECT max(day) AS d FROM content_proposals")
        if not row or not row["d"]:
            raise HTTPException(404, "no proposals exist")
        day_ = row["d"]
    else:
        day_ = date.fromisoformat(str(day_))
    if not (body.get("instruction") or body.get("platform") or body.get("manual")):
        raise HTTPException(400, "nothing to apply: pass instruction, platform or manual")
    try:
        row = revise_brief(day_, rank,
                           instruction=(body.get("instruction") or "").strip() or None,
                           platform=body.get("platform"),
                           manual=body.get("manual"),
                           by=_who(x_auth_request_email))
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    row = {"day": row["day"], "rank": row["rank"], "treatment": row["format"],
           "format_family": row["format_family"], "platform": row["platform"],
           "hook": row["hook"], "outline": row["outline"], "why": row["why"],
           "rides_signal": row["rides_signal"],
           "recommended_timing": row["recommended_timing"]}
    return _flatten_proposal(row)


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
    if period == "weekly":
        row["week_stats"] = _week_stats(row["payload"].get("window") or {})
    return row


def _week_stats(window: dict) -> dict:
    """Pipeline throughput for the weekly window — the Overview KPIs, extended
    to the week: collected -> filtered -> analyzed -> what came out the end."""
    frm, to = window.get("from"), window.get("to")
    if not frm or not to:
        return {}

    def _n(sql: str, params: tuple) -> int:
        return (db.one(sql, params) or {}).get("n", 0)

    span = (frm, to)
    return {
        "collected": _n("SELECT count(*) AS n FROM social_items "
                        "WHERE ingested_at::date BETWEEN %s AND %s", span),
        "duplicates_merged": _n(
            "SELECT count(*) AS n FROM social_items "
            "WHERE ingested_at::date BETWEEN %s AND %s AND duplicate_of IS NOT NULL", span),
        "noise_filtered": _n(
            "SELECT count(*) AS n FROM item_enrichment ie "
            "JOIN social_items si ON si.item_id = ie.item_id "
            "WHERE si.ingested_at::date BETWEEN %s AND %s AND ie.is_noise", span),
        "analyzed": _n(
            "SELECT count(*) AS n FROM item_enrichment "
            "WHERE ingested_at::date BETWEEN %s AND %s", span),
        "trends_identified": _n(
            "SELECT count(*) AS n FROM (SELECT topic_key FROM topic_daily "
            "WHERE day BETWEEN %s AND %s AND topic_key NOT LIKE 'other:%%' "
            "GROUP BY topic_key HAVING sum(count) >= 3) t", span),
        "issue_segments": _n(
            "SELECT count(*) AS n FROM (SELECT broker, issue_key FROM issue_rollup "
            "WHERE day BETWEEN %s AND %s GROUP BY broker, issue_key) t", span),
        "feature_themes": _n(
            "SELECT count(DISTINCT feature_key) AS n FROM feature_rollup "
            "WHERE day BETWEEN %s AND %s", span),
        "opportunities": _n(
            "SELECT count(*) AS n FROM opportunities "
            "WHERE day BETWEEN %s AND %s", span),
        "drafts_written": _n(
            "SELECT count(*) AS n FROM opportunities "
            "WHERE day BETWEEN %s AND %s AND brand_reply IS NOT NULL", span),
        "headsups_sent": _n(
            "SELECT count(*) AS n FROM headsups "
            "WHERE ts::date BETWEEN %s AND %s", span),
    }


def _item_filters(topic: str | None, broker: str | None, intent: str | None,
                  audience: str | None, q: str | None, min_engagement: float,
                  source: str | None) -> tuple[str, dict]:
    """Shared FROM/WHERE for /items and /items/export — one filter semantic."""
    sql = """
        FROM social_items si
        JOIN authors a ON a.author_id = si.author_id
        LEFT JOIN item_enrichment e ON e.item_id = si.item_id
        WHERE si.duplicate_of IS NULL AND COALESCE(e.is_noise, false) = false
          AND (si.engagement->>'score')::float >= %(mine)s
    """
    params: dict = {"mine": min_engagement}
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
    return sql, params


def _item_order(sort: str) -> str:
    return ("(si.engagement->>'score')::float DESC NULLS LAST, si.created_at DESC"
            if sort == "engagement" else "si.created_at DESC")


@app.get(API + "/items")
def items(topic: str | None = None, broker: str | None = None,
          intent: str | None = None, audience: str | None = None,
          q: str | None = None, min_engagement: float = 0,
          source: str | None = None,
          sort: Literal["engagement", "recent"] = "engagement",
          limit: int = 20, offset: int = 0):
    body, params = _item_filters(topic, broker, intent, audience, q, min_engagement, source)
    params.update({"limit": _lim(limit), "offset": max(offset, 0)})
    sql = """
        SELECT si.source, si.external_id, si.thread_id, left(si.text, 300) AS text,
               si.url, si.created_at, si.ingested_at, si.engagement,
               a.handle AS author,
               e.topic_key, e.intent, e.audience, e.sentiment, e.entities,
               (SELECT count(*) FROM social_items d WHERE d.duplicate_of = si.item_id)::int
                 AS duplicate_count
    """ + body + f" ORDER BY {_item_order(sort)} LIMIT %(limit)s OFFSET %(offset)s"
    return db.query(sql, params)


_EXPORT_COLUMNS = ["source", "external_id", "thread_id", "author", "text", "url",
                   "topic_key", "intent", "audience", "sentiment", "interactions",
                   "engagement_score", "entities", "posted_at_ist", "fetched_at_ist",
                   "duplicate_count"]


@app.get(API + "/items/export")
def items_export(format: Literal["csv", "xlsx"] = "csv",
                 topic: str | None = None, broker: str | None = None,
                 intent: str | None = None, audience: str | None = None,
                 q: str | None = None, min_engagement: float = 0,
                 source: str | None = None,
                 sort: Literal["engagement", "recent"] = "engagement",
                 limit: int = 2000):
    """Same filters as /items, but full text and spreadsheet-shaped rows."""
    import csv
    import io
    import json as _json
    import re as _re
    from zoneinfo import ZoneInfo

    from fastapi.responses import Response

    body, params = _item_filters(topic, broker, intent, audience, q, min_engagement, source)
    params["limit"] = max(1, min(limit, 10000))
    rows = db.query("""
        SELECT si.source, si.external_id, si.thread_id, si.text, si.url,
               si.created_at, si.ingested_at, si.engagement, a.handle AS author,
               e.topic_key, e.intent, e.audience, e.sentiment, e.entities,
               (SELECT count(*) FROM social_items d WHERE d.duplicate_of = si.item_id)::int
                 AS duplicate_count
    """ + body + f" ORDER BY {_item_order(sort)} LIMIT %(limit)s", params)

    ist = ZoneInfo("Asia/Kolkata")
    ctrl = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # Excel rejects control chars

    def _cell(v, guard_formula: bool = False):
        if v is None:
            return ""
        s = ctrl.sub(" ", str(v))
        if guard_formula and s[:1] in "=+-@":  # neutralize spreadsheet formula injection
            s = "'" + s
        return s

    flat = []
    for r in rows:
        native = (r.get("engagement") or {}).get("native") or {}
        inter = sum(v for v in native.values() if isinstance(v, (int, float)))
        flat.append([
            r["source"], r["external_id"], r["thread_id"],
            _cell(r["author"], True), _cell(r["text"], True), r["url"] or "",
            r["topic_key"] or "", r["intent"] or "", r["audience"] or "",
            r["sentiment"] if r["sentiment"] is not None else "",
            int(inter), (r.get("engagement") or {}).get("score", ""),
            _json.dumps(r["entities"]) if r["entities"] else "",
            r["created_at"].astimezone(ist).strftime("%Y-%m-%d %H:%M") if r["created_at"] else "",
            r["ingested_at"].astimezone(ist).strftime("%Y-%m-%d %H:%M") if r["ingested_at"] else "",
            r["duplicate_count"],
        ])

    stamp = datetime.now(ist).strftime("%Y%m%d-%H%M")
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(_EXPORT_COLUMNS)
        w.writerows(flat)
        return Response(
            buf.getvalue().encode("utf-8-sig"),  # BOM so Excel opens UTF-8 correctly
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="beacon-items-{stamp}.csv"'})

    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "items"
    ws.append(_EXPORT_COLUMNS)
    for row in flat:
        ws.append(row)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="beacon-items-{stamp}.xlsx"'})


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


@app.get(API + "/feedback")
def list_feedback(category: str | None = None, limit: int = 50):
    q = ("SELECT id, object_ref, category, free_text, submitted_by, ts "
         "FROM feedback")
    params: tuple = ()
    if category:
        q += " WHERE category = %s"
        params = (category,)
    return db.query(q + " ORDER BY ts DESC LIMIT %s", params + (_lim(limit),))


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


# ── features catalog (grounding editor — work plan N8) ────────────────────

_FEATURE_STATUSES = ("live", "upcoming")


@app.get(API + "/features-catalog")
def features_catalog():
    rows = db.query(
        "SELECT feature, description, status, category, seo_keywords, version, "
        "published_at FROM nubra_features WHERE is_current ORDER BY feature")
    version = rows[0]["version"] if rows else None
    published_at = rows[0]["published_at"] if rows else None
    return {"version": version, "published_at": published_at, "features": rows}


@app.post(API + "/features-catalog", status_code=201)
def publish_features_catalog(body: dict = Body(...),
                             x_auth_request_email: str | None = Header(None)):
    """Full-replacement publish: the posted list becomes version v<n+1> and
    is_current flips to it — the next draft/brief run grounds on it."""
    features = body.get("features")
    if not isinstance(features, list) or not features:
        raise HTTPException(400, "features must be a non-empty list")
    for f in features:
        if not (f.get("feature") or "").strip() or not (f.get("description") or "").strip():
            raise HTTPException(400, "every row needs feature and description")
        if f.get("status") not in _FEATURE_STATUSES:
            raise HTTPException(400, f"status must be one of {_FEATURE_STATUSES}")
    names = [f["feature"].strip() for f in features]
    if len(set(names)) != len(names):
        raise HTTPException(400, "duplicate feature names")
    # next version: v<n+1> over any existing v<int>; seed 'assumed-v0' counts as 0
    versions = [r["version"] for r in db.query("SELECT DISTINCT version FROM nubra_features")]
    nums = [0]
    for v in versions:
        tail = v.rsplit("v", 1)[-1]
        if tail.isdigit():
            nums.append(int(tail))
    new_version = f"v{max(nums) + 1}"
    for f in features:
        kws = f.get("seo_keywords") or []
        if not isinstance(kws, list):
            raise HTTPException(400, "seo_keywords must be a list")
        db.execute(
            "INSERT INTO nubra_features (feature, description, status, category, "
            "seo_keywords, version, is_current) VALUES (%s,%s,%s,%s,%s,%s,false) "
            "ON CONFLICT (feature, version) DO NOTHING",
            (f["feature"].strip(), f["description"].strip(), f["status"],
             (f.get("category") or "").strip() or None, [str(k).strip() for k in kws if str(k).strip()],
             new_version))
    db.execute("UPDATE nubra_features SET is_current = false WHERE is_current")
    db.execute("UPDATE nubra_features SET is_current = true WHERE version = %s", (new_version,))
    n = db.one("SELECT count(*) AS n FROM nubra_features WHERE is_current")["n"]
    return {"version": new_version, "features_current": n,
            "published_by": _who(x_auth_request_email)}


# ── watch sources (UI-managed collection config) ──────────────────────────

_KINDS = ("subreddit", "x_hashtag", "x_handle", "x_query", "keyword")


@app.get(API + "/sources")
def list_sources():
    rows = db.query("SELECT id, kind, value, category, active, added_by, note, "
                    "config, created_at FROM watch_sources ORDER BY kind, active DESC, value")
    return rows


@app.post(API + "/sources", status_code=201)
def add_source(payload: dict = Body(...),
               x_auth_request_email: str | None = Header(default=None)):
    kind = payload.get("kind")
    if kind not in _KINDS:
        raise HTTPException(400, f"kind must be one of {_KINDS}")
    value = (payload.get("value") or "").strip()
    # normalize prefixes users naturally paste
    for pre in ("r/", "@", "#", "https://reddit.com/r/", "https://www.reddit.com/r/",
                "https://x.com/", "https://twitter.com/"):
        if value.lower().startswith(pre):
            value = value[len(pre):]
    value = value.strip("/ ")
    # keywords and full queries may contain spaces; handles/hashtags/subs may not
    if not value or (kind not in ("x_query", "keyword") and (" " in value or len(value) > 60)):
        raise HTTPException(400, "value looks invalid for this kind")
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    if kind == "keyword" and not config:
        config = {"x": True, "reddit": True}  # default: watch everywhere
    row = db.one(
        "INSERT INTO watch_sources (kind, value, category, added_by, note, config) "
        "VALUES (%s, %s, %s, 'ui', %s, %s) "
        "ON CONFLICT (kind, value) DO UPDATE SET active = true, "
        "config = EXCLUDED.config "
        "RETURNING id, kind, value, category, active, config",
        (kind, value, payload.get("category") or "custom", payload.get("note"),
         db.jsonb(config)))
    return row


@app.post(API + "/sources/{source_id}/toggle")
def toggle_source(source_id: int):
    row = db.one("UPDATE watch_sources SET active = NOT active WHERE id=%s "
                 "RETURNING id, kind, value, active", (source_id,))
    if not row:
        raise HTTPException(404, "no such source")
    return row


@app.delete(API + "/sources/{source_id}", status_code=204)
def delete_source(source_id: int):
    if not db.execute("DELETE FROM watch_sources WHERE id=%s", (source_id,)):
        raise HTTPException(404, "no such source")
