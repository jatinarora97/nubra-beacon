"""API-trader lens — the segment classifier (plan 2026-08-25).

Runs inside the hourly pipeline after enrichment: a cheap regex gate flags
candidates among newly-enriched items, one Haiku call per ~20 classifies
them into api_trader_items (absence-based — an item is classified at most
once). The historical corpus is seeded from the 2026-08-25 full scan
(scripts/load_api_trader_seed.py) so only NEW items ever hit the LLM here.
"""
from __future__ import annotations

import json
import re

from community.config.log import get_logger
from community.config.settings import settings
from community.store import db

log = get_logger("enrich.api_trader")


def lens_enabled() -> bool:
    """One switch for the whole API-trading section (classifier spend,
    landscape monitor, dashboard endpoints). Env API_TRADING_ENABLED
    overrides the registry flag — prod .env is user-managed, so the section
    can stay dark on prod while dev keeps it on (launch hold, 2026-08-27)."""
    import os
    env = os.getenv("API_TRADING_ENABLED", "").strip().lower()
    if env:
        return env not in ("off", "false", "0", "no")
    return bool((settings.registry.get("api_trading", {}) or {}).get("enabled", True))

# Candidate gate — validated on the full corpus 2026-08-25 (3,866 gated of
# 99k; ~74% of gated items classified relevant). Postgres form uses \y.
GATE_PG = (r"\y(kite connect|smartapi|dhanhq|dhan api|fyers api|breeze api|shoonya|"
           r"flattrade|broker api|api key|rest api|websocket|order api|market data api|"
           r"historical data api|rate limit|access token|sdk|algotest|tradetron|openalgo|"
           r"amibroker|quantconnect|backtrader|backtest\w*|paper trad\w*|pine ?script|"
           r"tradingview|chartink|webhook|algo trad\w*|algotrading|automated trading|"
           r"automation|quant|latency|tick data|python)\y")

STAGES = ("exploring", "first_api", "building", "scaling", "churning")

# Theme bucketers — shared by the pipeline and the seed loader so historical
# and live rows speak the same vocabulary.
FRICTION_THEMES = [
    ("cost_pricing", r"data feed|paid data|subscription|pricing|charge|fee|expensive|tier|cost"),
    ("reliability", r"websocket|outage|downtime|403|error|halt|crash|uptime|disconnect|fail"),
    ("order_primitives", r"bracket|square.?off|order type|execution|partial fill|gtt|slippage|fill"),
    ("backtest_trust", r"backtest|overfit|paper trad|forward test|unrealistic"),
    ("data_access", r"free data|market data|historical data|data cost|feed"),
    ("deployment_infra", r"static ip|deploy|infra|server|vps|cloud|latency"),
    ("onboarding_auth", r"onboard|registration|api key|auth|login|credential|kyc|token"),
    ("risk_controls", r"circuit.?break|drawdown|risk exposure|risk management"),
    ("regulation", r"sebi|regulat|compliance|ban"),
    ("data_quality", r"inconsisten|differs|variance|discrepan|mismatch"),
]
WORKING_THEMES = [
    ("automation_live", r"automat|bot|algo running|deployed|24/7"),
    ("live_pnl", r"p&l|pnl|profit|roi|returns|live result"),
    ("backtest_proof", r"backtest|monte carlo|simulat|win rate|cagr"),
    ("free_data_builds", r"free|open.?source|nse data|colab|openbb"),
    ("ai_assisted", r"\bai\b|llm|claude|gpt|mcp|code gen|copilot"),
    ("no_code", r"no.?code|builder|algotest|tradetron|streak"),
]


def json_array(raw: str) -> list:
    """Model replies sometimes wrap the array in prose/fences — cut to the
    outermost [...] before parsing. Shared with landscape_monitor."""
    raw = raw.strip().strip("`")
    if raw.startswith("json"):
        raw = raw[4:]
    start, end = raw.find("["), raw.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("no JSON array in reply")
    return json.loads(raw[start:end + 1])


def _theme(blob: str, themes: list[tuple[str, str]]) -> str | None:
    low = blob.lower()
    for name, pat in themes:
        if re.search(pat, low):
            return name
    return None


def themes_for(kind: str | None, gist: str, text: str) -> tuple[str | None, str | None]:
    """(friction_theme, working_theme) — first matching bucket wins; the
    long tail stays null."""
    blob = f"{gist} {text}"[:600]
    return (_theme(blob, FRICTION_THEMES) if kind == "friction" else None,
            _theme(blob, WORKING_THEMES) if kind == "showcase" else None)


_PROMPT = """You are analyzing Indian trading-community chatter for the API-TRADER lens: people who trade via code/APIs/automation rather than manual chart trading.
For each item decide:
- relevant: about API/algo/automated trading practice, tools, or the journey INTO it (chart patterns, stock picks, memes, generic market talk = false)
- stage: exploring | first_api | building | scaling | churning
- first_api_type: ONLY when stage=first_api — "broker" (their first BROKER API: keys/auth/first order with a broker) | "any" (clearly their first API of any kind / new to APIs entirely) | "unclear"
- layer: broker_api | no_code_builder | backtesting | data_feed | charting_signal | community_learning
- kind: friction | guidance_seeking | showcase | comparison
- tools: named products/brokers, lowercase list
- gist: one sentence, the insight for a broker building for API traders
Return ONLY a JSON array [{"id","relevant","stage","first_api_type","layer","kind","tools","gist"}]."""


def classify_new(limit: int = 200) -> dict:
    """Classify enriched-but-unclassified gate matches. Bounded per run;
    isolated — a failure never breaks the pipeline (caller wraps)."""
    reg = settings.registry.get("api_trading", {}) or {}
    if not lens_enabled():
        return {"enabled": False}
    rows = db.query(
        """
        SELECT si.item_id, si.source, si.text
        FROM social_items si
        JOIN item_enrichment e ON e.item_id = si.item_id
        LEFT JOIN api_trader_items a ON a.item_id = si.item_id
        WHERE a.item_id IS NULL AND si.duplicate_of IS NULL
          AND NOT e.is_noise AND si.text ~* %s
        ORDER BY si.ingested_at DESC LIMIT %s
        """, (GATE_PG, min(limit, int(reg.get("max_classified_per_run", 200)))))
    if not rows:
        return {"candidates": 0, "classified": 0, "relevant": 0}

    from community.llm.client import client
    stats = {"candidates": len(rows), "classified": 0, "relevant": 0, "calls": 0}
    for i in range(0, len(rows), 20):
        chunk = rows[i:i + 20]
        items = [{"id": str(r["item_id"]), "text": (r["text"] or "")[:600]} for r in chunk]
        try:
            resp = client().messages.create(
                model=settings.enrich_model, max_tokens=4000,
                messages=[{"role": "user",
                           "content": _PROMPT + "\n\n" + json.dumps(items, ensure_ascii=False)}])
            stats["calls"] += 1
            out = json_array(resp.content[0].text)
        except Exception as e:  # noqa: BLE001 — one chunk must not sink the run
            log.warning("chunk failed (%s: %s)", type(e).__name__, str(e)[:100])
            continue
        byid = {str(r["item_id"]): r for r in chunk}
        for o in out:
            r = byid.get(str(o.get("id")))
            if r is None:
                continue
            stats["classified"] += 1
            if not o.get("relevant") or o.get("stage") not in STAGES:
                # marker row: never re-classify this item (endpoints filter these)
                db.execute("INSERT INTO api_trader_items (item_id, stage, model) "
                           "VALUES (%s, 'irrelevant', %s) ON CONFLICT (item_id) DO NOTHING",
                           (r["item_id"], settings.enrich_model))
                continue
            stats["relevant"] += 1
            fr, wk = themes_for(o.get("kind"), o.get("gist") or "", r["text"] or "")
            fat = o.get("first_api_type")
            db.execute(
                """
                INSERT INTO api_trader_items (item_id, stage, first_api_type, layer,
                    kind, tools, gist, friction_theme, working_theme, model)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (item_id) DO NOTHING
                """,
                (r["item_id"], o["stage"],
                 fat if (o["stage"] == "first_api" and fat in ("broker", "any", "unclear")) else None,
                 o.get("layer"), o.get("kind"),
                 db.jsonb([t for t in (o.get("tools") or []) if isinstance(t, str)][:10]),
                 (o.get("gist") or "")[:500], fr, wk, settings.enrich_model))
    log.info("api-trader lens: %s", stats)
    return stats
