"""Read-only data-staleness report for Twitter and Reddit. See community/health/staleness.py.

    docker compose exec -T api python scripts/data_staleness.py            # 30-day picture
    docker compose exec -T api python scripts/data_staleness.py --days 14
    docker compose exec -T api python scripts/data_staleness.py --json     # machine-readable

It only ever reads; it writes nothing to the database.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

os.environ.setdefault("PGCONNECT_TIMEOUT", "10")      # an unreachable database must not hang the report
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.health import staleness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=30, help="window for the per-day and per-subreddit tables")
    ap.add_argument("--json", action="store_true", help="print the raw report as JSON instead of text")
    args = ap.parse_args()
    try:
        report = staleness.collect(days=args.days)
    except Exception as e:  # noqa: BLE001
        print(f"could not read the database: {type(e).__name__}: {str(e)[:200]}")
        return 1
    print(json.dumps(report, default=str, indent=2) if args.json else staleness.render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
