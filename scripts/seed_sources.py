"""Seed watch_sources from registry.yaml (idempotent). After seeding, the DB is
the source of truth for collection sources; the registry lists remain only as
the seed + fallback when the table is empty."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.config.settings import settings
from community.store import db


def main() -> None:
    reg = settings.registry["sources"]
    rows: list[tuple[str, str, str | None]] = []
    subs = reg["reddit"]["subreddits"]
    if isinstance(subs, dict):
        for cat, lst in subs.items():
            rows += [("subreddit", s, cat) for s in lst]
    else:
        rows += [("subreddit", s, None) for s in subs]
    rows += [("x_query", q, None) for q in reg["twitter"].get("queries", [])]
    n = 0
    for kind, value, cat in rows:
        n += db.execute(
            "INSERT INTO watch_sources (kind, value, category, added_by) "
            "VALUES (%s, %s, %s, 'seed') ON CONFLICT (kind, value) DO NOTHING",
            (kind, value, cat),
        )
    print(f"seeded {n} new watch_sources ({len(rows)} candidates)")


if __name__ == "__main__":
    main()
