"""Seed nubra_features with the assumed-v0 catalog (idempotent).

Later: marketing's vetted cut (and keyword excel via --from-xlsx, prod) publishes
as a new version; this script flips is_current to the newest published version.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.reference.features import ASSUMED_V0, ASSUMED_VERSION
from community.store import db


def main() -> None:
    inserted = 0
    for feature, desc, status, category, kws in ASSUMED_V0:
        n = db.execute(
            """
            INSERT INTO nubra_features (feature, description, status, category,
                                        seo_keywords, version, is_current)
            VALUES (%s, %s, %s, %s, %s, %s, false)
            ON CONFLICT (feature, version) DO NOTHING
            """,
            (feature, desc, status, category, kws, ASSUMED_VERSION),
        )
        inserted += n
    # flip is_current to this version (one current row per feature)
    db.execute("UPDATE nubra_features SET is_current = false WHERE is_current")
    db.execute(
        "UPDATE nubra_features SET is_current = true WHERE version = %s", (ASSUMED_VERSION,)
    )
    total = db.one("SELECT count(*) AS n FROM nubra_features WHERE is_current")["n"]
    print(f"seeded {inserted} new rows; {total} features current at version {ASSUMED_VERSION}")


if __name__ == "__main__":
    main()
