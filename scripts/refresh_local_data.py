"""LOCAL TEST UTILITY — treat the existing (backfilled) data as fresh.

Shifts every social_items.created_at forward so the newest item is ~2h old
(relative spacing preserved), then resets the derived layers (L3 rollups, L4
outputs, downstream watermarks) so the next `run-local` recomputes everything
as if the data just arrived. Enrichment rows are kept (they don't depend on
created_at); compliance_audit is kept (append-only evidence).

Never run on prod — this rewrites source timestamps.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.store import db


def main() -> None:
    row = db.one("SELECT max(created_at) AS mx, count(*) AS n FROM social_items")
    if not row or not row["mx"]:
        raise SystemExit("no data to refresh")
    shifted = db.execute(
        "UPDATE social_items SET created_at = created_at + (now() - interval '2 hours' - %s)",
        (row["mx"],),
    )
    if "--compress" in sys.argv:  # squeeze the whole history toward now (demo freshness)
        f = float(sys.argv[sys.argv.index("--compress") + 1])
        db.execute(
            "UPDATE social_items SET created_at = now() - (now() - created_at) * %s", (f,))
        print(f"timeline compressed ×{f}")
    for sql in (
        "TRUNCATE conversations, topic_daily, issue_rollup, feature_rollup, author_stats",
        "DELETE FROM feature_rollup",  # no-op after truncate; kept for clarity
        "DELETE FROM content_proposals",
        "DELETE FROM roundups",
        "DELETE FROM opportunities",
        "DELETE FROM pipeline_state WHERE stage IN ('aggregate','score','recommend','roundup')",
    ):
        db.execute(sql)
    print(f"shifted {shifted} items (newest now ~2h old); L3/L4 + watermarks reset")


if __name__ == "__main__":
    main()
