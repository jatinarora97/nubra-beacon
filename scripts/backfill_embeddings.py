"""One-time backfill: embeddings for all existing canonical non-noise items +
centroids for slug-era feature_keys rows (so they participate in the LLD-02
§8.4 centroid matching). Idempotent — safe to re-run.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.enrich import embeddings
from community.store import db


def main() -> None:
    total = 0
    while True:
        n = embeddings.embed_pending(limit=2000)
        total += n
        if n == 0:
            break
    print(f"item embeddings backfilled: {total}")

    legacy = db.query(
        "SELECT feature_key, canonical_label FROM feature_keys WHERE centroid IS NULL")
    if legacy:
        vecs = embeddings.embed_texts([r["canonical_label"] for r in legacy])
        for r, v in zip(legacy, vecs):
            db.execute(
                "UPDATE feature_keys SET centroid = %s::vector, updated_at = now() "
                "WHERE feature_key = %s",
                (embeddings.to_vec(v), r["feature_key"]),
            )
    print(f"feature_keys centroids migrated: {len(legacy)}")

    n_items = db.one("SELECT count(*) AS n FROM item_embeddings")["n"]
    n_keys = db.one(
        "SELECT count(*) AS n FROM feature_keys WHERE centroid IS NOT NULL")["n"]
    print(f"state: {n_items} item_embeddings rows · {n_keys} feature_keys with centroids")


if __name__ == "__main__":
    main()
