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


@router.get("/funnel")
def funnel(days: int = 90):
    """Stage funnel + kind mix + the first_api split, over items CREATED in
    the window."""
    rows = db.query(
        f"SELECT a.stage, a.kind, count(*)::int AS n {_BASE} "
        "AND si.created_at >= %s GROUP BY 1, 2", (_win(days),))
    stages: dict[str, dict] = {}
    for r in rows:
        s = stages.setdefault(r["stage"], {"stage": r["stage"], "total": 0, "kinds": {}})
        s["total"] += r["n"]
        if r["kind"]:
            s["kinds"][r["kind"]] = s["kinds"].get(r["kind"], 0) + r["n"]
    order = ["exploring", "first_api", "building", "scaling", "churning"]
    split = {r["first_api_type"] or "unclear": r["n"] for r in db.query(
        f"SELECT a.first_api_type, count(*)::int AS n {_BASE} "
        "AND a.stage = 'first_api' AND si.created_at >= %s GROUP BY 1", (_win(days),))}
    return {"days": days,
            "stages": [stages.get(s, {"stage": s, "total": 0, "kinds": {}}) for s in order],
            "first_api_split": split}


@router.get("/themes")
def themes(kind: str = "friction", days: int = 90, per_theme: int = 5):
    """Theme board: counts + top items per theme (frictions or what-works)."""
    if kind not in ("friction", "working"):
        raise HTTPException(422, "kind must be friction or working")
    col = "friction_theme" if kind == "friction" else "working_theme"
    counts = db.query(
        f"SELECT a.{col} AS theme, count(*)::int AS n {_BASE} "
        f"AND a.{col} IS NOT NULL AND si.created_at >= %s "
        "GROUP BY 1 ORDER BY n DESC", (_win(days),))
    out = []
    for c in counts:
        items = db.query(
            f"SELECT a.item_id, a.gist, a.stage, si.source, si.url, "
            f"       left(si.text, 200) AS text, "
            f"       coalesce((si.engagement->>'score')::float, 0) AS eng {_BASE} "
            f"AND a.{col} = %s AND si.created_at >= %s "
            "ORDER BY (si.engagement->>'score')::float DESC NULLS LAST LIMIT %s",
            (c["theme"], _win(days), max(1, min(per_theme, 20))))
        out.append({**c, "items": items})
    return {"days": days, "kind": kind, "themes": out}


@router.get("/candidates")
def candidates(days: int = 30):
    """Build-candidate cards: live evidence counters + trend vs the previous
    window. Definitions live in registry api_trading.candidates."""
    defs = (settings.registry.get("api_trading", {}) or {}).get("candidates", [])
    now = datetime.now(timezone.utc)
    cur_from, prev_from = now - timedelta(days=days), now - timedelta(days=2 * days)
    out = []
    for c in defs:
        themes_list = list(c.get("themes") or [])
        row = db.one(
            f"""SELECT
              count(*) FILTER (WHERE si.created_at >= %(cur)s)::int AS current,
              count(*) FILTER (WHERE si.created_at >= %(prev)s
                               AND si.created_at < %(cur)s)::int AS previous
              {_BASE}
              AND (a.friction_theme = ANY(%(t)s) OR a.working_theme = ANY(%(t)s))""",
            {"cur": cur_from, "prev": prev_from, "t": themes_list})
        cur, prev = row["current"], row["previous"]
        out.append({"key": c["key"], "title": c["title"], "themes": themes_list,
                    "grounding": c.get("grounding") or [],
                    "current": cur, "previous": prev,
                    "trend": ("up" if cur > prev else "down" if cur < prev else "flat")})
    return {"days": days, "candidates": out}


@router.get("/landscape")
def landscape(days: int = 90):
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
        c = db.one("SELECT count(*)::int AS n FROM social_items "
                   "WHERE duplicate_of IS NULL AND created_at >= %s AND text ~* %s",
                   (_win(days), pat))["n"]
        r = db.one(f"SELECT count(*)::int AS rel, "
                   "count(*) FILTER (WHERE a.kind = 'friction')::int AS fr "
                   f"{_BASE} AND si.created_at >= %s AND si.text ~* %s",
                   (_win(days), pat))
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


@router.get("/items")
def items(stage: str | None = None, kind: str | None = None,
          layer: str | None = None, theme: str | None = None,
          first_api_type: str | None = None, tool: str | None = None,
          q: str | None = None, days: int = 90,
          limit: int = 50, offset: int = 0):
    """The Data page: classified items with raw + lens columns."""
    sql = _BASE + " AND si.created_at >= %(since)s"
    p: dict = {"since": _win(days), "lim": max(1, min(limit, 200)),
               "off": max(offset, 0)}
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
    return db.query(
        "SELECT a.item_id, a.stage, a.first_api_type, a.layer, a.kind, a.tools, "
        "       a.gist, a.friction_theme, a.working_theme, si.source, si.url, "
        "       left(si.text, 300) AS text, si.created_at, au.handle AS author, "
        "       coalesce((si.engagement->>'score')::float, 0) AS engagement "
        + sql +
        " ORDER BY si.created_at DESC LIMIT %(lim)s OFFSET %(off)s", p)
