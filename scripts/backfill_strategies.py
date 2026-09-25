"""One-shot strategy-detection backfill over the historical corpus.

    docker compose exec -T api python scripts/backfill_strategies.py

Loops the bounded hourly classifier until the gated backlog drains
(~762 candidates measured on the 2026-09 corpus => under a dollar of Haiku).
Idempotent and crash-safe: every chunk stores immediately; re-running skips
judged items. New items are handled by the hourly pipeline automatically.
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.enrich.strategy_tagger import classify_new


def main() -> None:
    total = {"classified": 0, "strategies": 0, "calls": 0}
    for i in range(60):  # hard stop well above any real backlog
        s = classify_new(limit=200)
        if not s.get("candidates"):
            print(f"drained after round {i}")
            break
        for k in total:
            total[k] += s.get(k, 0)
        print(f"round {i}: {s}", flush=True)
    print(json.dumps(total, indent=1))


if __name__ == "__main__":
    main()
