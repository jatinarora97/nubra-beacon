"""Load the historical API-trader classification seed into api_trader_items.

    docker compose exec -T api python scripts/load_api_trader_seed.py

The seed (data/api_trader_seed.json.gz) is the 2026-08-25 full-corpus scan —
run on a restored PROD dump, so item_ids match prod. Loading costs zero LLM
spend; idempotent (insert-if-absent); rows whose item no longer exists are
skipped. New items after the seed date are classified live by the pipeline
lens (community/enrich/api_trader.py).
"""
from __future__ import annotations

import gzip
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.enrich.api_trader import STAGES, themes_for
from community.store import db

SEED = pathlib.Path(__file__).resolve().parent.parent / "data" / "api_trader_seed.json.gz"


def main() -> None:
    rows = json.loads(gzip.decompress(SEED.read_bytes()))
    stats = {"seed_rows": len(rows), "inserted": 0, "already": 0, "no_item": 0, "bad": 0}
    known = {r["item_id"] for r in db.query(
        "SELECT item_id FROM social_items WHERE duplicate_of IS NULL")}
    for o in rows:
        try:
            item_id = int(o["id"])
        except (KeyError, ValueError):
            stats["bad"] += 1
            continue
        if o.get("stage") not in STAGES:
            stats["bad"] += 1
            continue
        if item_id not in known:
            stats["no_item"] += 1
            continue
        tools = o.get("tools") or []
        if isinstance(tools, str):
            tools = [tools]
        fr, wk = themes_for(o.get("kind"), o.get("gist") or "", o.get("text") or "")
        n = db.execute(
            """
            INSERT INTO api_trader_items (item_id, stage, first_api_type, layer,
                kind, tools, gist, friction_theme, working_theme, model)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'seed-2026-08-25')
            ON CONFLICT (item_id) DO NOTHING
            """,
            (item_id, o["stage"],
             "unclear" if o["stage"] == "first_api" else None,
             o.get("layer"), o.get("kind"),
             db.jsonb([t for t in tools if isinstance(t, str)][:10]),
             (o.get("gist") or "")[:500], fr, wk))
        stats["inserted" if n else "already"] += 1
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
