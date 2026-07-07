"""Feature-key cluster health report (work plan E1 companion) — print-only.

Two lenses on whether the incremental-centroid feature keys have drifted:
1. Pairwise centroid cosine similarity — pairs >= 0.80 are merge candidates.
2. HDBSCAN over the raw phrase embeddings of mapped items — do the natural
   clusters agree with the key assignment?

No writes. Registry-gated auto-merge is future work; a human reads this first.
Run: ./.venv/bin/python scripts/report_feature_clusters.py
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from community.enrich.embeddings import embed_texts, from_vec
from community.store import db

def _merge_bar() -> float:
    """e5-small phrase embeddings sit on a tight cone — mean pairwise sim is
    ~0.8, so 0.80 flags everything. Use the measured assignment threshold τ
    (registry, 0.86) as the merge bar: pairs the assigner itself would have
    merged had it seen them in the other order."""
    from community.config.settings import settings
    return float(settings.registry.get("aggregate", {}).get("feature_sim_threshold", 0.86))


def main() -> None:
    MERGE_BAR = _merge_bar()
    keys = db.query(
        "SELECT fk.feature_key, fk.canonical_label, fk.phrase_count, fk.centroid::text AS c, "
        "COALESCE(m.n, 0) AS mapped_items "
        "FROM feature_keys fk LEFT JOIN (SELECT feature_key, count(*) AS n "
        "FROM feature_item_map GROUP BY feature_key) m USING (feature_key) "
        "WHERE fk.centroid IS NOT NULL AND fk.is_active ORDER BY fk.feature_key")
    print(f"feature keys: {len(keys)}")
    if len(keys) < 2:
        print("nothing to compare")
        return

    C = np.array([from_vec(k["c"]) for k in keys])
    C = C / np.linalg.norm(C, axis=1, keepdims=True)
    sims = C @ C.T
    off = sims[np.triu_indices(len(keys), k=1)]
    print(f"baseline: mean pairwise centroid sim {off.mean():.3f} "
          f"(e5-small cone — the merge bar must sit above this)")

    print(f"\n== centroid pairs >= {MERGE_BAR} (merge candidates — the measured tau) ==")
    found = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if sims[i, j] >= MERGE_BAR:
                a, b = keys[i], keys[j]
                print(f"  {sims[i, j]:.3f}  {a['feature_key']} '{a['canonical_label']}' "
                      f"({a['mapped_items']} items)  <->  "
                      f"{b['feature_key']} '{b['canonical_label']}' ({b['mapped_items']} items)")
                found += 1
    if not found:
        print("  none — no key pair above the bar")

    # lens 2: cluster the raw phrases of mapped items
    rows = db.query(
        "SELECT m.feature_key, ie.entities->>'feature_phrase' AS phrase "
        "FROM feature_item_map m JOIN item_enrichment ie ON ie.item_id = m.item_id "
        "WHERE ie.entities->>'feature_phrase' IS NOT NULL")
    print(f"\n== HDBSCAN sanity check over {len(rows)} mapped phrases ==")
    if len(rows) < 4:
        print("  too few phrases to cluster")
        return
    from sklearn.cluster import HDBSCAN
    X = np.array(embed_texts([r["phrase"] for r in rows]))
    labels = HDBSCAN(min_cluster_size=2, metric="euclidean").fit_predict(X)
    by_cluster: dict[int, list[str]] = defaultdict(list)
    for r, lab in zip(rows, labels):
        by_cluster[int(lab)].append(r["feature_key"])
    for lab in sorted(by_cluster):
        mix = Counter(by_cluster[lab])
        tag = "noise " if lab == -1 else f"cluster {lab}"
        pure = "PURE" if lab != -1 and len(mix) == 1 else ("MIXED" if lab != -1 else "")
        print(f"  {tag}: {dict(mix)} {pure}")
    mixed = sum(1 for lab, ks in by_cluster.items() if lab != -1 and len(set(ks)) > 1)
    print(f"\nsummary: {max(labels) + 1 if labels.max() >= 0 else 0} phrase clusters, "
          f"{mixed} mixed-key clusters (mixed = keys HDBSCAN would merge)")


if __name__ == "__main__":
    main()
