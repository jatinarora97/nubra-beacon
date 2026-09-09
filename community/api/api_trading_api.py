"""Internal endpoints for the "API Trading" dashboard section
(/api/v1/api-trading/*). Plan: docs/api-trading-section-plan-2026-08-25.md.

Everything reads api_trader_items (the lens table) joined to social_items;
'irrelevant' marker rows are always filtered out. Landscape endpoints manage
landscape_features (weekly auto job + manual adds).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, Header, HTTPException

from community.config.settings import settings
from community.enrich.api_trader import lens_enabled
from community.store import db


def _gate() -> None:
    # section-wide launch hold: API_TRADING_ENABLED=off in .env darkens every
    # route (404), and the sidebar hides the group when its probe fails
    if not lens_enabled():
        raise HTTPException(404, "api-trading section is disabled")


router = APIRouter(prefix="/api/v1/api-trading", tags=["api-trading"],
                   dependencies=[Depends(_gate)])

_BASE = """
    FROM api_trader_items a
    JOIN social_items si ON si.item_id = a.item_id
    LEFT JOIN authors au ON au.author_id = si.author_id
    WHERE a.stage <> 'irrelevant' AND si.duplicate_of IS NULL
"""


def _win(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 365)))


def _range(days: int, window: str | None, from_ts: str | None,
           to_ts: str | None) -> tuple[datetime, datetime]:
    """Standard Beacon window vocabulary (window=7d / from_ts+to_ts), with the
    section's legacy days= as fallback — one filter semantic across the app."""
    from community.api.read_api import _window  # lazy: read_api mounts this router
    w = _window(from_ts, to_ts, window)
    if w:
        return w
    return _win(days), datetime.now(timezone.utc)


@router.get("/funnel")
def funnel(days: int = 90, window: str | None = None,
           from_ts: str | None = None, to_ts: str | None = None):
    """Stage funnel + kind mix + the first_api split, over items CREATED in
    the window."""
    f, t = _range(days, window, from_ts, to_ts)
    rows = db.query(
        f"SELECT a.stage, a.kind, count(*)::int AS n {_BASE} "
        "AND si.created_at >= %s AND si.created_at < %s GROUP BY 1, 2", (f, t))
    stages: dict[str, dict] = {}
    for r in rows:
        s = stages.setdefault(r["stage"], {"stage": r["stage"], "total": 0, "kinds": {}})
        s["total"] += r["n"]
        if r["kind"]:
            s["kinds"][r["kind"]] = s["kinds"].get(r["kind"], 0) + r["n"]
    order = ["exploring", "first_api", "building", "scaling", "churning"]
    split = {r["first_api_type"] or "unclear": r["n"] for r in db.query(
        f"SELECT a.first_api_type, count(*)::int AS n {_BASE} "
        "AND a.stage = 'first_api' AND si.created_at >= %s AND si.created_at < %s "
        "GROUP BY 1", (f, t))}
    return {"days": days,
            "stages": [stages.get(s, {"stage": s, "total": 0, "kinds": {}}) for s in order],
            "first_api_split": split}


@router.get("/themes")
def themes(kind: str = "friction", days: int = 90, per_theme: int = 5,
           window: str | None = None,
           from_ts: str | None = None, to_ts: str | None = None):
    """Theme board: counts + top items per theme (frictions or what-works)."""
    if kind not in ("friction", "working"):
        raise HTTPException(422, "kind must be friction or working")
    f, t = _range(days, window, from_ts, to_ts)
    col = "friction_theme" if kind == "friction" else "working_theme"
    counts = db.query(
        f"SELECT a.{col} AS theme, count(*)::int AS n {_BASE} "
        f"AND a.{col} IS NOT NULL AND si.created_at >= %s AND si.created_at < %s "
        "GROUP BY 1 ORDER BY n DESC", (f, t))
    out = []
    for c in counts:
        items = db.query(
            f"SELECT a.item_id, a.gist, a.stage, si.source, si.url, "
            f"       left(si.text, 200) AS text, "
            f"       coalesce((si.engagement->>'score')::float, 0) AS eng {_BASE} "
            f"AND a.{col} = %s AND si.created_at >= %s AND si.created_at < %s "
            "ORDER BY (si.engagement->>'score')::float DESC NULLS LAST LIMIT %s",
            (c["theme"], f, t, max(1, min(per_theme, 20))))
        out.append({**c, "items": items})
    return {"days": days, "kind": kind, "themes": out}


@router.get("/candidates")
def candidates(days: int = 30, window: str | None = None,
               from_ts: str | None = None, to_ts: str | None = None):
    """Build-candidate cards: live evidence counters + trend vs the previous
    window. Definitions live in registry api_trading.candidates."""
    defs = (settings.registry.get("api_trading", {}) or {}).get("candidates", [])
    cur_from, now = _range(days, window, from_ts, to_ts)
    prev_from = cur_from - (now - cur_from)
    out = []
    for c in defs:
        themes_list = list(c.get("themes") or [])
        row = db.one(
            f"""SELECT
              count(*) FILTER (WHERE si.created_at >= %(cur)s
                               AND si.created_at < %(now)s)::int AS current,
              count(*) FILTER (WHERE si.created_at >= %(prev)s
                               AND si.created_at < %(cur)s)::int AS previous
              {_BASE}
              AND (a.friction_theme = ANY(%(t)s) OR a.working_theme = ANY(%(t)s))""",
            {"cur": cur_from, "prev": prev_from, "now": now, "t": themes_list})
        cur, prev = row["current"], row["previous"]
        out.append({"key": c["key"], "title": c["title"], "themes": themes_list,
                    "grounding": c.get("grounding") or [],
                    "current": cur, "previous": prev,
                    "trend": ("up" if cur > prev else "down" if cur < prev else "flat")})
    return {"days": days, "candidates": out}


@router.get("/landscape")
def landscape(days: int = 90, window: str | None = None,
              from_ts: str | None = None, to_ts: str | None = None):
    """Competitor grounding (features) + live coverage strip per tracked
    player (corpus/relevant/friction mention counts)."""
    feats = db.query("SELECT id, competitor, feature, status, evidence_url, "
                     "first_seen, last_seen, added_by, notes "
                     "FROM landscape_features ORDER BY competitor, status, feature")
    by_comp: dict[str, list] = {}
    for f in feats:
        by_comp.setdefault(f["competitor"], []).append(f)
    coverage = []
    for p in (settings.registry.get("api_trading", {}) or {}).get("landscape", []):
        pat = p.get("patterns")
        if not pat:
            continue
        f, t = _range(days, window, from_ts, to_ts)
        c = db.one("SELECT count(*)::int AS n FROM social_items "
                   "WHERE duplicate_of IS NULL AND created_at >= %s "
                   "AND created_at < %s AND text ~* %s", (f, t, pat))["n"]
        r = db.one(f"SELECT count(*)::int AS rel, "
                   "count(*) FILTER (WHERE a.kind = 'friction')::int AS fr "
                   f"{_BASE} AND si.created_at >= %s AND si.created_at < %s "
                   "AND si.text ~* %s", (f, t, pat))
        coverage.append({"name": p["name"], "corpus": c,
                         "relevant": r["rel"], "frictions": r["fr"],
                         "features": by_comp.get(p["name"], [])})
    return {"days": days, "players": coverage,
            "untracked_features": {k: v for k, v in by_comp.items()
                                   if k not in {x["name"] for x in coverage}}}


@router.post("/landscape", status_code=201)
def landscape_add(payload: dict = Body(...),
                  x_auth_request_email: str | None = Header(default=None)):
    comp = str(payload.get("competitor") or "").strip()
    feat = str(payload.get("feature") or "").strip()
    status = str(payload.get("status") or "shipped").strip()
    if not comp or not feat:
        raise HTTPException(422, "competitor and feature are required")
    if status not in ("shipped", "upcoming", "rumored"):
        raise HTTPException(422, "status must be shipped, upcoming or rumored")
    row = db.one(
        """
        INSERT INTO landscape_features (competitor, feature, status, evidence_url,
                                        added_by, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (competitor, feature) DO UPDATE SET
            status = EXCLUDED.status, last_seen = now(),
            notes = COALESCE(EXCLUDED.notes, landscape_features.notes)
        RETURNING id, competitor, feature, status
        """,
        (comp, feat, status, payload.get("evidence_url"),
         x_auth_request_email or "dashboard", payload.get("notes")))
    return row


@router.delete("/landscape/{feature_id}", status_code=204)
def landscape_delete(feature_id: int):
    if not db.execute("DELETE FROM landscape_features WHERE id = %s", (feature_id,)):
        raise HTTPException(404, "no such feature")


@router.get("/content")
def content_queue(platform: str | None = None, status: str = "draft",
                  limit: int = 60):
    """The intern-facing content queue: api_trading-lens briefs.
    status: draft (ready to post) | published (acted) | rejected (dismissed)."""
    if status not in ("draft", "published", "rejected", "all"):
        raise HTTPException(422, "status must be draft, published, rejected or all")
    sql = ("SELECT r.id, r.day, r.platform, r.post_format, r.title, r.hook, "
           "r.body, r.cta, r.exact_copy, r.hashtags, r.mapped_features, "
           "r.source_evidence, r.rationale, r.recommended_timing, "
           "r.priority_score, r.status, r.seed_url, r.created_at "
           "FROM social_recommendations r WHERE r.lens = 'api_trading'")
    p: dict = {"lim": max(1, min(limit, 200))}
    if status != "all":
        sql += " AND r.status = %(status)s"
        p["status"] = status
    if platform:
        sql += " AND r.platform = %(platform)s"
        p["platform"] = platform
    return db.query(sql + " ORDER BY r.created_at DESC, r.priority_score DESC "
                          "LIMIT %(lim)s", p)


def _content_transition(brief_id: int, new_status: str, event: str,
                        actor: str, note: str | None) -> dict:
    row = db.one("SELECT id, status FROM social_recommendations "
                 "WHERE id = %s AND lens = 'api_trading'", (brief_id,))
    if not row:
        raise HTTPException(404, "no such brief")
    if row["status"] != "draft":
        raise HTTPException(409, f"brief already {row['status']}")
    db.execute("UPDATE social_recommendations SET status=%s, updated_at=now() "
               "WHERE id=%s", (new_status, brief_id))
    db.execute("INSERT INTO social_recommendation_events "
               "(recommendation_id, event_type, actor, note) VALUES (%s,%s,%s,%s)",
               (brief_id, event, actor, note))
    return {"id": brief_id, "status": new_status, "actor": actor}


@router.post("/content/{brief_id}/act")
def content_act(brief_id: int, payload: dict = Body(default={}),
                x_auth_request_email: str | None = Header(default=None),
                x_forwarded_email: str | None = Header(default=None)):
    """Intern posted it — mark published. Optional note: the live post URL."""
    return _content_transition(brief_id, "published", "published",
                               x_auth_request_email or x_forwarded_email or "dashboard",
                               (payload.get("note") or "").strip() or None)


@router.post("/content/{brief_id}/dismiss")
def content_dismiss(brief_id: int, payload: dict = Body(default={}),
                    x_auth_request_email: str | None = Header(default=None),
                    x_forwarded_email: str | None = Header(default=None)):
    """Not worth posting — permanently out of the queue."""
    return _content_transition(brief_id, "rejected", "rejected",
                               x_auth_request_email or x_forwarded_email or "dashboard",
                               (payload.get("note") or "").strip() or None)


@router.post("/content/top-up", status_code=202)
def content_top_up():
    """Manual refill (the hourly compose does this automatically)."""
    from community.social_recommend import api_lens
    return api_lens.top_up()


def _item_filters(stage, kind, layer, theme, first_api_type, tool, q,
                  days, window, from_ts, to_ts) -> tuple[str, dict]:
    """Shared FROM/WHERE for /items and /items/export — one filter semantic."""
    f, t = _range(days, window, from_ts, to_ts)
    sql = _BASE + " AND si.created_at >= %(since)s AND si.created_at < %(until)s"
    p: dict = {"since": f, "until": t}
    for name, val, clause in (
            ("stage", stage, " AND a.stage = %(stage)s"),
            ("kind", kind, " AND a.kind = %(kind)s"),
            ("layer", layer, " AND a.layer = %(layer)s"),
            ("fat", first_api_type, " AND a.first_api_type = %(fat)s")):
        if val:
            sql += clause
            p[name] = val
    if theme:
        sql += " AND (a.friction_theme = %(theme)s OR a.working_theme = %(theme)s)"
        p["theme"] = theme
    if tool:
        sql += " AND a.tools ? %(tool)s"
        p["tool"] = tool.lower()
    if q:
        sql += " AND si.text ILIKE %(q)s"
        p["q"] = f"%{q}%"
    return sql, p


@router.get("/items")
def items(stage: str | None = None, kind: str | None = None,
          layer: str | None = None, theme: str | None = None,
          first_api_type: str | None = None, tool: str | None = None,
          q: str | None = None, days: int = 90, window: str | None = None,
          from_ts: str | None = None, to_ts: str | None = None,
          sort: str = "recent", limit: int = 50, offset: int = 0):
    """The Data page: classified items with raw + lens columns."""
    sql, p = _item_filters(stage, kind, layer, theme, first_api_type, tool, q,
                           days, window, from_ts, to_ts)
    p.update({"lim": max(1, min(limit, 200)), "off": max(offset, 0)})
    return db.query(
        "SELECT a.item_id, a.stage, a.first_api_type, a.layer, a.kind, a.tools, "
        "       a.gist, a.friction_theme, a.working_theme, si.source, si.url, "
        "       left(si.text, 300) AS text, si.created_at, au.handle AS author, "
        "       coalesce((si.engagement->>'score')::float, 0) AS engagement "
        + sql + " ORDER BY " +
        ("coalesce((si.engagement->>'score')::float,0) DESC, si.created_at DESC"
         if sort == "engagement" else "si.created_at DESC") +
        " LIMIT %(lim)s OFFSET %(off)s", p)


@router.get("/items/export")
def items_export(format: str = "csv", stage: str | None = None,
                 kind: str | None = None, layer: str | None = None,
                 theme: str | None = None, first_api_type: str | None = None,
                 tool: str | None = None, q: str | None = None, days: int = 90,
                 window: str | None = None, from_ts: str | None = None,
                 to_ts: str | None = None, limit: int = 2000):
    """Same filters as /items, full text, spreadsheet-shaped — mirrors
    /items/export on the Explore page (same _spreadsheet renderer)."""
    if format not in ("csv", "xlsx"):
        raise HTTPException(422, "format must be csv or xlsx")
    sql, p = _item_filters(stage, kind, layer, theme, first_api_type, tool, q,
                           days, window, from_ts, to_ts)
    p["lim"] = max(1, min(limit, 10000))
    rows = db.query(
        "SELECT si.source, a.stage, a.first_api_type, a.layer, a.kind, "
        "       a.friction_theme, a.working_theme, a.tools, a.gist, si.text, "
        "       si.url, au.handle AS author, si.created_at, "
        "       coalesce((si.engagement->>'score')::float, 0) AS engagement "
        + sql + " ORDER BY si.created_at DESC LIMIT %(lim)s", p)
    from community.api.read_api import _spreadsheet
    header = ["source", "stage", "first_api_type", "layer", "kind",
              "friction_theme", "working_theme", "tools", "gist", "text",
              "url", "author", "created_at", "engagement"]
    return _spreadsheet(format, "api-trading-items", header, [
        [r["source"], r["stage"], r["first_api_type"], r["layer"], r["kind"],
         r["friction_theme"], r["working_theme"],
         ", ".join(r["tools"] or []) if isinstance(r["tools"], list) else r["tools"],
         r["gist"], r["text"], r["url"], r["author"],
         r["created_at"].isoformat() if r["created_at"] else "",
         r["engagement"]] for r in rows])
