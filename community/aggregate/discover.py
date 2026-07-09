"""Emergent-topic discovery (work plan E1) — HDBSCAN over `other:*` chatter.

Items the enrichment LLM could not place in the taxonomy land in ad-hoc
`other:<slug>` keys and are invisible to trends. This module (morning build,
daily) clusters their embeddings; each dense cluster becomes a SUGGESTED
topic_taxonomy row (status='suggested') that a human activates from the
Trends page — nothing is auto-collected into the live taxonomy, mirroring
the discovered-hashtag pattern.

Embeddings are L2-normalized at encode time (multilingual-e5-small), so
euclidean HDBSCAN approximates cosine clustering. min_cluster_size=4: a
theme needs at least 4 independent items to be worth a human's click.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from community.store import db
from community.config.log import get_logger

log = get_logger("discover")

MIN_CLUSTER_SIZE = 4
WINDOW_DAYS = 30
MAX_SUGGESTIONS_PER_RUN = 8

_LABEL_SYSTEM = (
    "You name discussion topics for an Indian stock-broker community radar. "
    "Given sample posts from ONE cluster of related community chatter, return "
    'ONLY JSON: {"key": "<snake_case_topic_key>", "label": "<short human label, '
    '<=6 words>", "why": "<one line: what this cluster is about>"}. '
    "The key must be lowercase snake_case, no 'other' prefix, specific to the "
    "theme (e.g. margin_penalty, mtf_funding). Exclude politics/sports/crypto "
    "framing — these are trading/market/broker conversations."
)


def _fetch_other_embeddings() -> list[dict]:
    return db.query(
        """
        SELECT ie.item_id, emb.embedding::text AS vec, left(si.text, 400) AS text
        FROM item_enrichment ie
        JOIN item_embeddings emb ON emb.item_id = ie.item_id
        JOIN social_items si ON si.item_id = ie.item_id
        WHERE ie.topic_key LIKE 'other:%%' AND NOT ie.is_noise
          AND si.duplicate_of IS NULL
          AND ie.enriched_at > now() - interval '%s days'
        """ % WINDOW_DAYS)


def discover_topics() -> dict:
    """Cluster other:* items -> suggested taxonomy rows. Returns run stats."""
    import numpy as np
    from sklearn.cluster import HDBSCAN

    from community.config.settings import settings
    from community.enrich.embeddings import from_vec
    from community.llm.client import complete

    rows = _fetch_other_embeddings()
    if len(rows) < MIN_CLUSTER_SIZE:
        return {"note": f"topic discovery skipped: only {len(rows)} other:* items"}

    X = np.array([from_vec(r["vec"]) for r in rows])
    labels = HDBSCAN(min_cluster_size=MIN_CLUSTER_SIZE, metric="euclidean",
                     copy=True).fit_predict(X)
    n_clusters = int(labels.max()) + 1 if labels.max() >= 0 else 0
    stats = {"other_items": len(rows), "clusters": n_clusters,
             "suggested_new": 0, "skipped_existing": 0, "label_failures": 0}
    if n_clusters == 0:
        return stats

    existing = {r["topic_key"] for r in db.query("SELECT topic_key FROM topic_taxonomy")}
    # largest clusters first; cap suggestions per run to keep review light
    order = sorted(range(n_clusters), key=lambda c: -(labels == c).sum())
    for c in order[:MAX_SUGGESTIONS_PER_RUN]:
        idx = np.where(labels == c)[0]
        centroid = X[idx].mean(axis=0)
        central = idx[np.argsort(-(X[idx] @ centroid))][:5]
        samples = "\n---\n".join(rows[int(i)]["text"] for i in central)
        try:
            raw, _u = complete(settings.enrich_model, _LABEL_SYSTEM,
                               f"Cluster of {len(idx)} posts:\n{samples}",
                               max_tokens=200)
            out = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            key = re.sub(r"[^a-z0-9_]", "", str(out["key"]).strip().lower().replace(" ", "_"))[:50]
            label, why = str(out["label"]).strip()[:80], str(out["why"]).strip()[:200]
        except Exception as e:  # noqa: BLE001 — one bad label never kills the run
            stats["label_failures"] += 1
            log.warning("cluster %s label failed: %s: %s", c, type(e).__name__, str(e)[:80])
            continue
        if not key or key in existing:
            stats["skipped_existing"] += 1
            continue
        db.execute(
            """
            INSERT INTO topic_taxonomy (topic_key, label, seeded, active, evergreen,
                                        status, suggested_why, suggested_count, suggested_at)
            VALUES (%s, %s, false, false, false, 'suggested', %s, %s, %s)
            ON CONFLICT (topic_key) DO NOTHING
            """,
            (key, label, why, int(len(idx)), datetime.now(timezone.utc)))
        existing.add(key)
        stats["suggested_new"] += 1
    return stats
