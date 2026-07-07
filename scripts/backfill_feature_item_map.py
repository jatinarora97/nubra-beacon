"""One-off backfill of feature_item_map (work plan 2026-07-07, B3).

Reconstructs which item fed which feature_key for items enriched BEFORE the
map existed. Assignment order:
  1. sample evidence — the item appears in a feature_rollup.sample_item_ids
     array (exact historical assignment, no guessing);
  2. nearest-centroid — embed the phrase and take the closest active centroid
     WITHOUT folding (folding already happened when the item was first
     aggregated; re-folding would drift the centroid). Below-tau matches are
     assigned anyway with a warning: every item historically fed SOME key, and
     nearest is the best reconstruction available.

Then recomputes every touched (feature_key, day) rollup row from the map and
prints the invariants. Run via:  ./.venv/bin/python scripts/backfill_feature_item_map.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from community.aggregate.rollups import recompute_feature_day  # noqa: E402
from community.config.settings import settings  # noqa: E402
from community.store import db  # noqa: E402


def main() -> None:
    items = db.query(
        """
        SELECT ie.item_id, ie.entities->>'feature_phrase' AS phrase,
               si.created_at::date AS day
        FROM item_enrichment ie
        JOIN social_items si ON si.item_id = ie.item_id
        WHERE ie.intent = 'feature_request' AND NOT ie.is_noise
          AND ie.entities->>'feature_phrase' IS NOT NULL
        ORDER BY ie.item_id
        """)
    already = {r["item_id"] for r in db.query("SELECT item_id FROM feature_item_map")}
    todo = [i for i in items if i["item_id"] not in already]
    print(f"feature items: {len(items)} · already mapped: {len(already)} · to backfill: {len(todo)}")
    if not todo:
        return

    # pass 1 — sample evidence from feature_rollup
    evidence: dict[int, tuple[str, object]] = {}
    for r in db.query("SELECT feature_key, day, sample_item_ids FROM feature_rollup"):
        for iid in r["sample_item_ids"] or []:
            evidence.setdefault(iid, (r["feature_key"], r["day"]))

    from community.enrich import embeddings
    tau = float(settings.registry.get("aggregate", {}).get("feature_sim_threshold", 0.80))
    touched: set[tuple] = set()
    by_evidence = by_centroid = below_tau = 0

    for it in todo:
        if it["item_id"] in evidence:
            key, _ = evidence[it["item_id"]]
            by_evidence += 1
        else:
            vec = embeddings.embed_texts([it["phrase"]])[0]
            vstr = embeddings.to_vec(vec)
            best = db.one(
                "SELECT feature_key, 1 - (centroid <=> %s::vector) AS sim "
                "FROM feature_keys WHERE centroid IS NOT NULL AND is_active "
                "ORDER BY centroid <=> %s::vector LIMIT 1", (vstr, vstr))
            if not best:
                print(f"  WARN item {it['item_id']}: no centroids exist — skipped")
                continue
            key = best["feature_key"]
            by_centroid += 1
            if best["sim"] < tau:
                below_tau += 1
                print(f"  WARN item {it['item_id']} sim {best['sim']:.3f} < tau {tau}: "
                      f"{it['phrase'][:60]!r} -> {key} (assigned nearest anyway)")
        db.execute(
            "INSERT INTO feature_item_map (item_id, feature_key, day) "
            "VALUES (%s,%s,%s) ON CONFLICT (item_id) DO NOTHING",
            (it["item_id"], key, it["day"]))
        touched.add((key, it["day"]))

    # recompute every (key, day) that exists in EITHER the map or old rollups,
    # so stale rollup rows for re-assigned days get replaced too
    for r in db.query("SELECT DISTINCT feature_key, day FROM feature_rollup"):
        touched.add((r["feature_key"], r["day"]))
    for key, day in sorted(touched, key=lambda t: (t[0], str(t[1]))):
        recompute_feature_day(key, day)

    print(f"assigned: {by_evidence} by sample evidence, {by_centroid} by nearest "
          f"centroid ({below_tau} below tau) · recomputed {len(touched)} (key, day) rows")
    inv = db.one(
        "SELECT (SELECT count(*) FROM feature_item_map) AS mapped, "
        "(SELECT COALESCE(sum(count),0) FROM feature_rollup) AS rollup_sum")
    print(f"invariant: feature_item_map={inv['mapped']} rows · "
          f"sum(feature_rollup.count)={inv['rollup_sum']}")


if __name__ == "__main__":
    main()
