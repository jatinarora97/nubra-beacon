"""Seed nubra_features from the editable Nubra context catalog.

Default source:
    data/nubra_context/nubra_context.yaml

The YAML file is the human-editable source. This script publishes its feature
subset into `nubra_features` and flips `is_current` to that version.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from community.reference.features import ASSUMED_V0, ASSUMED_VERSION
from community.reference.nubra_context import DEFAULT_CONTEXT_PATH, feature_rows, summary
from community.store import db


def _load_rows(path: str | None, use_assumed: bool) -> tuple[str, list[tuple[str, str, str, str, list[str]]]]:
    if use_assumed:
        return ASSUMED_VERSION, ASSUMED_V0
    return feature_rows(path or DEFAULT_CONTEXT_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish Nubra feature catalog into nubra_features")
    parser.add_argument(
        "--context",
        default=str(DEFAULT_CONTEXT_PATH),
        help="Path to editable Nubra context YAML",
    )
    parser.add_argument(
        "--assumed-v0",
        action="store_true",
        help="Use the old hardcoded assumed-v0 fallback catalog",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print summary without writing to DB",
    )
    args = parser.parse_args()

    version, rows = _load_rows(args.context, args.assumed_v0)
    if args.dry_run:
        if args.assumed_v0:
            print({"version": version, "features": len(rows), "source": "assumed-v0"})
        else:
            print(summary(args.context))
        return

    inserted = 0
    for feature, desc, status, category, kws in rows:
        n = db.execute(
            """
            INSERT INTO nubra_features (feature, description, status, category,
                                        seo_keywords, version, is_current)
            VALUES (%s, %s, %s, %s, %s, %s, false)
            ON CONFLICT (feature, version) DO NOTHING
            """,
            (feature, desc, status, category, kws, version),
        )
        inserted += n
    # flip is_current to this version (one current row per feature)
    db.execute("UPDATE nubra_features SET is_current = false WHERE is_current")
    db.execute(
        "UPDATE nubra_features SET is_current = true WHERE version = %s", (version,)
    )
    total = db.one("SELECT count(*) AS n FROM nubra_features WHERE is_current")["n"]
    print(f"seeded {inserted} new rows; {total} features current at version {version}")


if __name__ == "__main__":
    main()
