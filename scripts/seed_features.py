"""Seed/publish the grounded nubra_features catalog (idempotent).

Re-running on any DB inserts the catalog version if absent and flips
is_current to it — this IS the swap mechanism (used 2026-07-17 to replace
assumed-v0 with context-v1 from nubra_product_context.md). Later edits go
through the Grounding page, which mints v2, v3, ...
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.reference.features import CONTEXT_V1, CONTEXT_VERSION
from community.store import db


def main() -> None:
    inserted = 0
    for feature, desc, status, category, kws in CONTEXT_V1:
        n = db.execute(
            """
            INSERT INTO nubra_features (feature, description, status, category,
                                        seo_keywords, version, is_current)
            VALUES (%s, %s, %s, %s, %s, %s, false)
            ON CONFLICT (feature, version) DO NOTHING
            """,
            (feature, desc, status, category, kws, CONTEXT_VERSION),
        )
        inserted += n
    # flip is_current to this version (one current row per feature)
    db.execute("UPDATE nubra_features SET is_current = false WHERE is_current")
    db.execute(
        "UPDATE nubra_features SET is_current = true WHERE version = %s", (CONTEXT_VERSION,)
    )
    total = db.one("SELECT count(*) AS n FROM nubra_features WHERE is_current")["n"]
    print(f"seeded {inserted} new rows; {total} features current at version {CONTEXT_VERSION}")


if __name__ == "__main__":
    main()
