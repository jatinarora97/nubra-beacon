"""Landscape monitor — weekly competitor grounding (plan 2026-08-25).

For each player in registry api_trading.landscape, fetches its public pages
(API docs / pricing / changelog), extracts shipped/upcoming features via one
Haiku call, and upserts landscape_features. Existing feature names are fed
back to the model so the same feature keeps one canonical name across weeks.
Runs at most once per 6 days (pipeline_state gate); rides the morning build,
isolated. Cost: ~10 players x 1 call ≈ $0.05/week.
"""
from __future__ import annotations

import json
import re

import httpx

from community.config.log import get_logger
from community.config.settings import settings
from community.enrich.api_trader import json_array
from community.store import db, repositories as repo

log = get_logger("enrich.landscape")

_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

_PROMPT = """You are maintaining a competitor-feature catalog for an Indian broker.
Below is text scraped from {name}'s public pages (API docs / pricing / product).
Extract PRODUCT FEATURES relevant to API/algo traders (APIs, order types, data
feeds, sandboxes, integrations, pricing tiers for API access). For each:
- feature: short name, <=60 chars. IMPORTANT: if it matches one of the EXISTING
  names below, reuse that exact name (do not invent a synonym).
- status: "shipped" (available now) or "upcoming" (announced/beta/coming soon).
EXISTING names for {name}: {existing}
Skip marketing fluff, generic brokerage features, and anything not
API-trader-relevant. Max 15 features. Return ONLY a JSON array
[{{"feature","status"}}]."""


def _page_text(url: str) -> str:
    try:
        r = httpx.get(url, headers=_UA, timeout=25, follow_redirects=True)
        if r.status_code != 200:
            return ""
        txt = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        txt = re.sub(r"<[^>]+>", " ", txt)
        return re.sub(r"\s+", " ", txt)[:12000]
    except Exception as e:  # noqa: BLE001 — a dead page is a note, not a crash
        log.warning("fetch failed %s (%s)", url, type(e).__name__)
        return ""


def run_weekly() -> dict:
    reg = settings.registry.get("api_trading", {}) or {}
    players = reg.get("landscape") or []
    if not reg.get("enabled", True) or not players:
        return {"enabled": False}
    state = repo.get_state("ingest", "landscape")
    last = (state or {}).get("last_success_at")
    if last and (repo.now_utc() - last).days < 6:
        return {"skipped": f"weekly cadence — last run {last.date()}"}

    from community.llm.client import client
    stats = {"players": 0, "pages": 0, "features_upserted": 0, "failed": []}
    for p in players:
        name, urls = p.get("name"), p.get("urls") or []
        if not name or not urls:  # urls: [] = manual-only player, by design
            continue
        text = " ".join(t for t in (_page_text(u) for u in urls[:3]) if t)
        stats["pages"] += min(len(urls), 3)
        if len(text) < 200:
            stats["failed"].append(f"{name}:no_text")
            continue
        existing = [r["feature"] for r in db.query(
            "SELECT feature FROM landscape_features WHERE competitor=%s", (name,))]
        try:
            resp = client().messages.create(
                model=settings.enrich_model, max_tokens=1500,
                messages=[{"role": "user", "content":
                           _PROMPT.format(name=name, existing=json.dumps(existing[:40]))
                           + "\n\nPAGE TEXT:\n" + text[:9000]}])
            feats = json_array(resp.content[0].text)
        except Exception as e:  # noqa: BLE001
            log.warning("extract failed for %s (%s: %s)", name, type(e).__name__, str(e)[:80])
            stats["failed"].append(f"{name}:extract")
            continue
        for f in feats[:15]:
            feat = str(f.get("feature") or "").strip()[:60]
            status = f.get("status") if f.get("status") in ("shipped", "upcoming") else "shipped"
            if not feat:
                continue
            db.execute(
                """
                INSERT INTO landscape_features (competitor, feature, status,
                                                evidence_url, added_by)
                VALUES (%s, %s, %s, %s, 'auto')
                ON CONFLICT (competitor, feature) DO UPDATE SET
                    last_seen = now(),
                    -- auto refresh never overwrites a manual row's status
                    status = CASE WHEN landscape_features.added_by = 'auto'
                                  THEN EXCLUDED.status ELSE landscape_features.status END
                """,
                (name, feat, status, urls[0]))
            stats["features_upserted"] += 1
        stats["players"] += 1
    repo.advance_state("ingest", "landscape", watermark=repo.now_utc(),
                       items=stats["features_upserted"])
    log.info("landscape monitor: %s", stats)
    return stats
