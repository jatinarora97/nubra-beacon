"""One-time Instagram backfill (user runs on prod after release):

    docker compose exec api python scripts/backfill_instagram.py

Fetches results_limit_backfill (20) posts per watched account, stores them
(insert-if-absent — safe to re-run), then runs the AV tier pass (whisper
transcripts, Haiku vision, top-liked comments) over the gated slice. Local
testing: same command via ./cm shell or .venv python. Idempotent by design.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.config.settings import settings
from community.scrape import instagram
from community.scrape.extra_sources import _run_source


def main() -> None:
    cfg = dict(settings.registry.get("sources", {}).get("instagram", {}) or {})
    if not cfg.get("enabled"):
        print("sources.instagram.enabled is false — nothing to do")
        return
    cfg["backfill"] = True
    # tier the whole backfill in one pass instead of the daily drip
    cfg["max_tier_items_per_run"] = int(cfg.get("results_limit_backfill", 20)) * 12

    print("collecting (backfill mode, %s posts/account)…"
          % cfg.get("results_limit_backfill", 20))
    stats = _run_source("instagram", instagram.fetch, cfg)
    print(json.dumps(stats, indent=1, default=str))

    if "error" in stats:
        print("collection errored — fix and re-run (idempotent). Tiers skipped.")
        sys.exit(1)

    print("tier pass (sequential whisper/vision — this can take a while)…")
    tiers = instagram.process_tiers(cfg)
    print(json.dumps(tiers, indent=1, default=str))
    print(f"apify spend this backfill: ${tiers.get('apify_cost_usd', 0):.2f}")


if __name__ == "__main__":
    main()
