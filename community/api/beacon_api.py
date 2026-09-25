"""Beacon read-only API — /api/beacon/v1/* (one MCP tool per endpoint).

Plan + locked decisions: docs/beacon-api-surface-2026-08-17.md (2026-08-17):
24h-rolling default window · read-only v1 · per-consumer X-API-Key ·
FULL data by default (only internal pipeline bookkeeping stripped from raw) ·
opaque next_cursor keyset pagination · kill switch = registry
beacon_api.enabled. Intelligence/action endpoints WRAP the same internal
functions the dashboard uses — zero logic drift by construction.

NOTE: read_api mounts this router, so read_api/social/discover imports here
are function-local (module-level would be circular).
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import date, datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row

from community.config.settings import settings
from community.store import db

SOURCES = ("twitter", "reddit", "youtube", "github",
           "community_forum", "app_review", "instagram")
SOURCE_ALIASES = {"x": "twitter", "forum": "community_forum", "review": "app_review"}
INTENTS = ("complaint", "feature_request", "question", "praise",
           "comparison", "how_to", "news_opinion", "spam")
AUDIENCES = ("active_trader", "long_term_investor", "beginner", "influencer", "other")
# raw keys that are OUR pipeline plumbing, not partner data (locked decision 6)
_RAW_INTERNAL = ("s3_video", "s3_display", "s3_children", "transcript_state",
                 "tiers_done", "vision_done", "vision_slides")


def _cfg(key: str, default):
    return (settings.registry.get("beacon_api") or {}).get(key, default)


# ── auth + rate limit (router-level dependency) ────────────────────────────

_BUCKETS: dict[int, list[float]] = {}          # key_id -> recent request times
_LAST_TOUCH: dict[int, float] = {}             # throttle last_used_at writes


def _require_key(request: Request) -> None:
    if not _cfg("enabled", True):
        raise HTTPException(503, "beacon API is disabled")
    secret = request.headers.get("x-api-key") or ""
    if not secret:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            secret = auth[7:].strip()
    if not secret:
        raise HTTPException(401, "missing API key (X-API-Key header)")
    row = db.one("SELECT key_id, label FROM api_keys "
                 "WHERE key_hash = %s AND revoked_at IS NULL",
                 (hashlib.sha256(secret.encode()).hexdigest(),))
    if not row:
        raise HTTPException(401, "unknown or revoked API key")
    key_id = row["key_id"]

    now = time.monotonic()
    per_min = int(_cfg("rate_limit_per_min", 60))
    bucket = [t for t in _BUCKETS.get(key_id, []) if now - t < 60]
    if len(bucket) >= per_min:
        raise HTTPException(429, "rate limit exceeded",
                            headers={"Retry-After": str(int(61 - (now - bucket[0])))})
    bucket.append(now)
    _BUCKETS[key_id] = bucket

    if now - _LAST_TOUCH.get(key_id, 0) > 60:
        _LAST_TOUCH[key_id] = now
        db.execute("UPDATE api_keys SET last_used_at = now() WHERE key_id = %s", (key_id,))
    request.state.beacon_key_id = key_id


router = APIRouter(prefix="/api/beacon/v1", tags=["beacon-api"],
                   dependencies=[Depends(_require_key)])


# ── shared plumbing ────────────────────────────────────────────────────────

def _q(sql: str, params=None) -> list[dict]:
    """Beacon API queries: read-only + statement timeout at the connection —
    a slow query self-cancels before it can contend with the pipeline."""
    ms = int(_cfg("statement_timeout_ms", 2000))
    opts = f"-c statement_timeout={ms} -c default_transaction_read_only=on"
    with psycopg.connect(settings.db_url, row_factory=dict_row, options=opts) as c:
        return c.execute(sql, params).fetchall()


def _envelope(rows: list, next_cursor: str | None = None,
              since: datetime | None = None, until: datetime | None = None) -> dict:
    out = {"results": rows, "next_cursor": next_cursor}
    if since:
        out["window"] = {"since": since.isoformat(), "until": until.isoformat()}
    return out


def _enc(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload, default=str).encode()).decode()


def _dec(cursor: str | None) -> dict:
    if not cursor:
        return {}
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "invalid cursor") from None


def _range(since: str | None, until: str | None) -> tuple[datetime, datetime]:
    """Locked decision 2: default = rolling 24h ending now."""
    def parse(v, name):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, f"{name} must be ISO8601") from None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    u = parse(until, "until") if until else datetime.now(timezone.utc)
    s = parse(since, "since") if since else u - timedelta(hours=24)
    if s >= u:
        raise HTTPException(422, "since must be before until")
    return s, u


def _lim(limit: int) -> int:
    return max(1, min(limit, int(_cfg("max_limit", 200))))


def _src_list(sources: str | None) -> list[str] | None:
    if not sources:
        return None
    out = []
    for tok in sources.split(","):
        s = SOURCE_ALIASES.get(tok.strip().lower(), tok.strip().lower())
        if s not in SOURCES:
            raise HTTPException(422, f"unknown source {tok!r} (valid: {list(SOURCES)}"
                                     f" + aliases {SOURCE_ALIASES})")
        out.append(s)
    return out


def _clean_raw(raw: dict | None) -> dict | None:
    if not isinstance(raw, dict):
        return raw
    return {k: v for k, v in raw.items() if k not in _RAW_INTERNAL}


def _resp() -> Response:
    return Response()   # sink for wrapped internal fns that set headers


_ITEM_SELECT = """
    SELECT si.item_id, si.source, si.source_type, si.external_id, si.thread_id,
           si.parent_id, si.text, si.lang, si.url, si.created_at, si.ingested_at,
           si.engagement, si.raw, a.handle AS author,
           e.topic_key, e.intent, e.audience, e.sentiment, e.entities, e.is_noise
    FROM social_items si
    JOIN authors a USING (author_id)
    LEFT JOIN item_enrichment e ON e.item_id = si.item_id
"""


def _item_where(p: dict, since, until, sources, topic, intent, audience, broker,
                q, min_engagement, sentiment_min, sentiment_max, include_noise) -> str:
    w = ["si.duplicate_of IS NULL",
         "si.ingested_at >= %(since)s", "si.ingested_at < %(until)s"]
    p.update({"since": since, "until": until})
    if sources:
        w.append("si.source = ANY(%(sources)s)")
        p["sources"] = sources
    if topic:
        w.append("e.topic_key = %(topic)s")
        p["topic"] = topic
    if intent:
        w.append("e.intent = %(intent)s")
        p["intent"] = intent
    if audience:
        w.append("e.audience = %(audience)s")
        p["audience"] = audience
    if broker:
        w.append("e.entities->>'broker' = %(broker)s")
        p["broker"] = broker
    if q:
        w.append("si.text ILIKE %(q)s")
        p["q"] = f"%{q}%"
    if min_engagement:
        w.append("(si.engagement->>'score')::float >= %(min_eng)s")
        p["min_eng"] = min_engagement
    if sentiment_min is not None:
        w.append("e.sentiment >= %(s_min)s")
        p["s_min"] = sentiment_min
    if sentiment_max is not None:
        w.append("e.sentiment <= %(s_max)s")
        p["s_max"] = sentiment_max
    if not include_noise:
        w.append("NOT coalesce(e.is_noise, false)")
    return " AND ".join(w)


def _page_items(sql_where: str, p: dict, cursor: str | None, limit: int,
                extra_select: str = "") -> tuple[list[dict], str | None]:
    cur = _dec(cursor)
    if cur:
        sql_where += " AND (si.ingested_at, si.item_id) < (%(c_ts)s, %(c_id)s)"
        p.update({"c_ts": cur.get("ts"), "c_id": cur.get("id")})
    rows = _q(f"{_ITEM_SELECT.replace('SELECT ', 'SELECT ' + extra_select)} "
              f"WHERE {sql_where} "
              f"ORDER BY si.ingested_at DESC, si.item_id DESC LIMIT %(lim)s",
              {**p, "lim": limit + 1})
    nxt = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        nxt = _enc({"ts": last["ingested_at"], "id": last["item_id"]})
    for r in rows:
        r["raw"] = _clean_raw(r.get("raw"))
    return rows, nxt


# ── A · corpus ─────────────────────────────────────────────────────────────

@router.get("/items")
def items(sources: str | None = None, since: str | None = None,
          until: str | None = None, topic: str | None = None,
          intent: str | None = None, audience: str | None = None,
          broker: str | None = None, q: str | None = None,
          min_engagement: float = 0, sentiment_min: float | None = None,
          sentiment_max: float | None = None, include_noise: bool = False,
          limit: int = 25, cursor: str | None = None):
    s, u = _range(since, until)
    p: dict = {}
    where = _item_where(p, s, u, _src_list(sources), topic, intent, audience,
                        broker, q, min_engagement, sentiment_min, sentiment_max,
                        include_noise)
    rows, nxt = _page_items(where, p, cursor, _lim(limit))
    return _envelope(rows, nxt, s, u)


@router.get("/items/search")
def items_search(q: str, sources: str | None = None, since: str | None = None,
                 until: str | None = None, include_noise: bool = False,
                 limit: int = 25, cursor: str | None = None):
    """Full-text: websearch syntax — `a OR b`, quoted phrases, -exclusions."""
    s, u = _range(since, until)
    p: dict = {"tsq": q}
    where = _item_where(p, s, u, _src_list(sources), None, None, None, None,
                        None, 0, None, None, include_noise)
    where += " AND si.text_tsv @@ websearch_to_tsquery('english', %(tsq)s)"
    extra = ("ts_headline('english', si.text, "
             "websearch_to_tsquery('english', %(tsq)s)) AS match_snippet, ")
    rows, nxt = _page_items(where, p, cursor, _lim(limit), extra_select=extra)
    return _envelope(rows, nxt, s, u)


@router.get("/items/{source}/{external_id}")
def item_detail(source: str, external_id: str):
    """external_id = the platform's own id (second half of our uniqueness
    pair; copy it from any /items row): tweet id, reddit t3_..., yt_video_...,
    instagram shortCode."""
    from community.api.read_api import item_detail as internal
    src = SOURCE_ALIASES.get(source.lower(), source.lower())
    out = internal(src, external_id)
    out["item"]["raw"] = _clean_raw(out["item"].get("raw"))
    return out


# ── B · people ─────────────────────────────────────────────────────────────

_AUTHOR_SQL = """
    SELECT a.author_id, a.source, a.handle, a.followers, a.verified,
           min(si.created_at) AS first_seen_at, max(si.created_at) AS last_seen_at,
           count(*)::int AS item_count,
           round(avg((si.engagement->>'score')::float)::numeric, 3) AS avg_engagement,
           (SELECT array_agg(t.topic_key) FROM (
                SELECT e2.topic_key FROM social_items si2
                JOIN item_enrichment e2 ON e2.item_id = si2.item_id
                WHERE si2.author_id = a.author_id AND e2.topic_key IS NOT NULL
                GROUP BY e2.topic_key ORDER BY count(*) DESC LIMIT 3) t
           ) AS top_topics
    FROM authors a JOIN social_items si USING (author_id)
"""


@router.get("/authors")
def authors(sources: str | None = None, since: str | None = None,
            until: str | None = None, q: str | None = None, min_items: int = 1,
            limit: int = 25, cursor: str | None = None):
    s, u = _range(since, until)
    p: dict = {"since": s, "until": u, "min_items": max(1, min_items)}
    where = ["si.ingested_at >= %(since)s", "si.ingested_at < %(until)s"]
    srcs = _src_list(sources)
    if srcs:
        where.append("si.source = ANY(%(sources)s)")
        p["sources"] = srcs
    if q:
        where.append("a.handle ILIKE %(q)s")
        p["q"] = f"%{q}%"
    offset = int(_dec(cursor).get("o", 0))
    lim = _lim(limit)
    rows = _q(f"{_AUTHOR_SQL} WHERE {' AND '.join(where)} "
              "GROUP BY a.author_id HAVING count(*) >= %(min_items)s "
              "ORDER BY item_count DESC, a.author_id LIMIT %(lim)s OFFSET %(off)s",
              {**p, "lim": lim + 1, "off": offset})
    nxt = _enc({"o": offset + lim}) if len(rows) > lim else None
    return _envelope(rows[:lim], nxt, s, u)


@router.get("/authors/{source}/{handle}")
def author_detail(source: str, handle: str):
    src = SOURCE_ALIASES.get(source.lower(), source.lower())
    profile = _q(f"{_AUTHOR_SQL} WHERE a.source = %(src)s AND a.handle = %(h)s "
                 "GROUP BY a.author_id", {"src": src, "h": handle})
    if not profile:
        raise HTTPException(404, "author not found")
    recent = _q(_ITEM_SELECT + " WHERE a.source = %(src)s AND a.handle = %(h)s "
                "AND si.duplicate_of IS NULL "
                "ORDER BY si.created_at DESC LIMIT 20", {"src": src, "h": handle})
    for r in recent:
        r["raw"] = _clean_raw(r.get("raw"))
    return {"author": profile[0], "recent_items": recent}


# ── C · intelligence (wrap the exact functions the dashboard renders) ──────

@router.get("/trends")
def trends(since: str | None = None, until: str | None = None, limit: int = 20):
    from community.api.read_api import trends as internal
    s, u = _range(since, until)
    return _envelope(internal(_resp(), date_=None, from_ts=s.isoformat(),
                              to_ts=u.isoformat(), limit=_lim(limit)), None, s, u)


@router.get("/broker-issues")
def broker_issues(broker: str | None = None, since: str | None = None,
                  until: str | None = None):
    from community.api.read_api import issues as internal
    s, u = _range(since, until)
    return _envelope(internal(broker=broker, from_=s.date(), to=u.date()), None, s, u)


@router.get("/feature-requests")
def feature_requests(since: str | None = None, until: str | None = None,
                     min_days: int = 1):
    from community.api.read_api import features as internal
    s, u = _range(since, until)
    return _envelope(internal(_resp(), from_=None, to=None, min_days=min_days,
                              from_ts=s.isoformat(), to_ts=u.isoformat()), None, s, u)


@router.get("/nubra-mentions")
def nubra_mentions(since: str | None = None, until: str | None = None,
                   limit: int = 30):
    from community.api.read_api import nubra_mentions as internal
    s, u = _range(since, until)
    return _envelope(internal(limit=_lim(limit), window=None,
                              from_ts=s.isoformat(), to_ts=u.isoformat()), None, s, u)


@router.get("/topic-suggestions")
def topic_suggestions():
    from community.api.discover_api import topic_suggestions as internal
    return _envelope(internal())


# ── D · action layer ───────────────────────────────────────────────────────

@router.get("/opportunities")
def opportunities(since: str | None = None, until: str | None = None,
                  status: str | None = None, min_priority: int = 0,
                  limit: int = 50):
    from community.api.read_api import opportunities as internal
    s, u = _range(since, until)
    return _envelope(internal(_resp(), date_=None, status=status,
                              min_priority=min_priority, from_ts=s.isoformat(),
                              to_ts=u.isoformat(), limit=_lim(limit)), None, s, u)


@router.get("/drafts")
def drafts(since: str | None = None, until: str | None = None, limit: int = 50):
    """Opportunities that carry a ready compliant draft (brand and/or rep)."""
    from community.api.read_api import opportunities as internal
    s, u = _range(since, until)
    rows = internal(_resp(), date_=None, from_ts=s.isoformat(),
                    to_ts=u.isoformat(), limit=_lim(limit))
    rows = [r for r in rows if r.get("brand_reply") or r.get("rep_reply")]
    return _envelope(rows, None, s, u)


@router.get("/briefs")
def briefs(day: date | None = None):
    """Content briefs for a day (default: latest built day)."""
    from community.api.read_api import content_proposals as internal
    return _envelope(internal(date_=day))


@router.get("/social-recommendations")
def social_recommendations(segment: str | None = None, status: str | None = None,
                           platform: str | None = None, limit: int = 30):
    from community.api.social_recommend_api import list_recommendations as internal
    return _envelope(internal(segment=segment, status=status, platform=platform,
                              limit=max(1, min(limit, 100))))


@router.get("/roundups")
def roundups(period: str = "daily", day: date | None = None):
    from community.api.read_api import roundups as internal
    if period not in ("daily", "weekly"):
        raise HTTPException(422, "period must be daily or weekly")
    return _envelope([internal(period=period, date_=day)])


# ── E · ops + meta ─────────────────────────────────────────────────────────

@router.get("/runs")
def runs():
    rows = _q("SELECT stage, source, watermark, last_success_at, last_error, "
              "last_error_at, items_last_run FROM pipeline_state "
              "ORDER BY stage, source")
    return _envelope(rows)


@router.get("/source-health")
def source_health(live: bool = False):
    from community.api.read_api import source_health as internal
    return _envelope(internal(live=live)["sources"])


@router.get("/watch-sources")
def watch_sources():
    from community.api.read_api import list_sources as internal
    return _envelope(internal())


@router.get("/taxonomy")
def taxonomy():
    """Valid filter values — use these instead of guessing enum values."""
    from community.enrich.topics import active_topics
    from community.reference.taxonomy import BROKER_GAZETTEER, ISSUE_TYPES
    return {
        "sources": list(SOURCES),
        "source_aliases": SOURCE_ALIASES,
        "topics": {k: label for k, (label, _) in active_topics().items()},
        "intents": list(INTENTS),
        "audiences": list(AUDIENCES),
        "issue_types": list(ISSUE_TYPES),
        "brokers": list(BROKER_GAZETTEER.keys()),
    }


@router.get("/grounding")
def grounding():
    """Nubra's real capabilities (context-v2+) — ground product claims here."""
    from community.api.read_api import features_catalog as internal
    out = internal()   # {"version", "published_at", "features": [...]}
    return {"results": out["features"], "next_cursor": None,
            "version": out["version"], "published_at": out["published_at"]}


@router.get("/usage")
def usage(days: int = 30):
    from community.api.read_api import llm_usage_summary as internal
    return internal(days=days)
