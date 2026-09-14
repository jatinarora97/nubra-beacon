"""Strategy detection — is this post an actual trading strategy, and if so
what is it? Feeds the Strategy columns on Explore and the API-trading Data
page (user request 2026-09-14).

Two-tier like the api_trader lens: a cheap SQL gate (action words + setup
words + length) flags candidates among enriched items; Haiku judges whether
the post states real, followable trading rules and extracts them two ways —
verbatim (strategy_raw) and normalized (strategy_summary). Judged
non-strategies get is_strategy=false marker rows so nothing is re-bought.
Runs hourly inside the enrich stage, bounded per run; the historical backlog
drains via scripts/backfill_strategies.py or organically.
"""
from __future__ import annotations

import json

from community.config.log import get_logger
from community.config.settings import settings
from community.enrich.api_trader import json_array
from community.store import db

log = get_logger("enrich.strategy")

# action words (what to do) AND setup words (with what) AND enough text —
# measured 2026-09-14: 762 of 69k enriched items gate through (~1% => the
# full backlog classifies for under a dollar)
GATE_ACTION = (r"\y(entry|exit|stop.?loss|\ysl\y|target|take.?profit|"
               r"book profit)\y")
GATE_SETUP = (r"\y(rsi|ema|sma|vwap|macd|bollinger|supertrend|crossover|"
              r"breakout|straddle|strangle|iron condor|butterfly|covered call|"
              r"spread|option selling|scalp\w*|swing|intraday|expiry|momentum|"
              r"mean reversion|orb|opening range)\y")

_PROMPT = """You judge Indian trading-community posts. For each item decide whether the
post states an ACTUAL TRADING STRATEGY — concrete, followable rules (an
instrument/underlying plus entry and/or exit logic: indicator conditions,
levels, times, strikes, adjustments). Merely mentioning "my strategy",
performance talk without rules, courses/ads, or generic advice = NOT a
strategy.

For each item return:
- id: as given
- is_strategy: true|false
- raw: ONLY if true — the strategy rules QUOTED VERBATIM from the post
  (trim unrelated text; keep the author's own words; <= 600 chars)
- summary: ONLY if true — the strategy rewritten cleanly in one or two
  sentences: instrument, timeframe, entry rule, exit/SL/target, indicators.
  Neutral wording; never add rules the post does not state.

Return ONLY a JSON array: [{"id","is_strategy","raw","summary"}]"""


def classify_new(limit: int = 200) -> dict:
    """Classify gated-but-unjudged items. Bounded; caller isolates failures."""
    rows = db.query(
        """
        SELECT si.item_id, si.text
        FROM social_items si
        JOIN item_enrichment e ON e.item_id = si.item_id
        LEFT JOIN item_strategy st ON st.item_id = si.item_id
        WHERE st.item_id IS NULL AND si.duplicate_of IS NULL AND NOT e.is_noise
          AND length(si.text) > 200
          AND si.text ~* %s AND si.text ~* %s
        ORDER BY si.ingested_at DESC LIMIT %s
        """, (GATE_ACTION, GATE_SETUP, max(1, min(limit, 400))))
    if not rows:
        return {"candidates": 0, "classified": 0, "strategies": 0}

    from community.llm.client import client
    stats = {"candidates": len(rows), "classified": 0, "strategies": 0, "calls": 0}
    for i in range(0, len(rows), 20):
        chunk = rows[i:i + 20]
        items = [{"id": str(r["item_id"]), "text": (r["text"] or "")[:1200]} for r in chunk]
        try:
            resp = client().messages.create(
                model=settings.enrich_model, max_tokens=6000,
                messages=[{"role": "user", "content":
                           _PROMPT + "\n\n" + json.dumps(items, ensure_ascii=False)}])
            stats["calls"] += 1
            out = json_array(resp.content[0].text)
        except Exception as e:  # noqa: BLE001 — one chunk must not sink the run
            log.warning("strategy chunk failed (%s: %s)", type(e).__name__, str(e)[:100])
            continue
        byid = {str(r["item_id"]): r for r in chunk}
        for o in out:
            r = byid.get(str(o.get("id")))
            if r is None:
                continue
            is_strat = bool(o.get("is_strategy"))
            raw = (o.get("raw") or "")[:800] if is_strat else None
            summary = (o.get("summary") or "")[:600] if is_strat else None
            if is_strat and not (raw and summary):
                is_strat, raw, summary = False, None, None
            db.execute(
                "INSERT INTO item_strategy (item_id, is_strategy, strategy_raw, "
                "strategy_summary, model) VALUES (%s, %s, %s, %s, %s) "
                "ON CONFLICT (item_id) DO NOTHING",
                (r["item_id"], is_strat, raw, summary, settings.enrich_model))
            stats["classified"] += 1
            stats["strategies"] += int(is_strat)
    log.info("strategy tagger: %s", stats)
    return stats
