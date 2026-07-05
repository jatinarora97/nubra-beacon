"""X trending-hashtag discovery → suggested watch sources.

We do NOT consume X's trending panel implicitly. This module (run daily from the
morning build once X credits exist) pulls India trends from twitterapi.io,
LLM-filters them for trading/finance relevance, and inserts the survivors into
watch_sources as INACTIVE suggestions (added_by='discovery') — they appear on
the UI Sources page with a "suggested" badge for one-click activation. Nothing
is ever auto-collected without a human activating it.

Status: implemented + credit-gated. twitterapi.io currently returns 402
(credits exhausted), so the live endpoint shape is unverified — the call is
wrapped accordingly and degrades to a note.
"""
from __future__ import annotations

import json

import httpx

from community.config.settings import settings
from community.store import db

WOEID_INDIA = 23424848
ENDPOINT = "https://api.twitterapi.io/twitter/trends"


def discover() -> dict:
    if not settings.twitterapi_key:
        return {"note": "trend discovery skipped: no TWITTERAPI_IO_KEY"}
    try:
        r = httpx.get(ENDPOINT, params={"woeid": WOEID_INDIA},
                      headers={"X-API-Key": settings.twitterapi_key}, timeout=20)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:  # noqa: BLE001 — 402/404/shape all degrade to a note
        return {"note": f"trend discovery unavailable ({type(e).__name__}: {str(e)[:80]})"}

    names = []
    for entry in (payload if isinstance(payload, list) else payload.get("trends", [])):
        name = entry.get("name") if isinstance(entry, dict) else None
        if name:
            names.append(name)
    if not names:
        return {"note": "trend discovery: endpoint returned no trends"}

    from community.llm.client import complete
    raw, _u = complete(
        settings.enrich_model,
        "You filter trending topics for an Indian stock broker's community radar. "
        "From the list, return ONLY JSON {\"relevant\": [\"tag\", ...]} keeping items "
        "related to Indian markets, trading, brokers, F&O, mutual funds, or the "
        "economy. Exclude politics, sports, entertainment, crypto.",
        json.dumps(names[:50]), max_tokens=400)
    try:
        relevant = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])["relevant"]
    except Exception:  # noqa: BLE001
        return {"note": "trend discovery: filter output unparsable", "raw_trends": len(names)}

    suggested = 0
    for tag in relevant[:15]:
        suggested += db.execute(
            "INSERT INTO watch_sources (kind, value, category, active, added_by, note) "
            "VALUES ('x_hashtag', %s, 'custom', false, 'discovery', 'trending in India today') "
            "ON CONFLICT (kind, value) DO NOTHING", (tag.lstrip("#"),))
    return {"raw_trends": len(names), "relevant": len(relevant), "suggested_new": suggested}
