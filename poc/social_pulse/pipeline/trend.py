"""Rank topics by velocity x cross-source spread x audience weight.

Phase-1 topic = the classifier's topic label (keyword-driven). Phase 3 would replace
this with BERTopic / embeddings+HDBSCAN for emergent clusters. The ranking math is the
same either way, so this stays.
"""
from __future__ import annotations

from collections import defaultdict


def rank_topics(classified: list[dict], cfg: dict) -> list[dict]:
    aw = cfg.get("audience_weights", {})
    top_n = int(cfg.get("trend", {}).get("top_n", 10))

    topics: dict[str, dict] = defaultdict(
        lambda: {"mentions": 0, "sources": set(), "engagement": 0,
                 "audiences": defaultdict(int), "sentiments": defaultdict(int),
                 "examples": [], "members": []}
    )

    for c in classified:
        if c.get("is_noise"):
            continue
        g = c["group"]
        t = topics[c["topic"]]
        t["mentions"] += len(g.members)          # each occurrence counts toward velocity
        t["sources"] |= g.sources
        t["engagement"] += sum(m.engagement.get("score", 0) for m in g.members)
        t["audiences"][c["audience"]] += 1
        t["sentiments"][c["sentiment"]] += 1
        # full ground data — every underlying item, with link + provenance
        for m in g.members:
            t["members"].append({
                "text": m.text,
                "source": m.source,
                "type": m.source_type,
                "author": m.author,
                "url": m.url,
                "subreddit": (m.raw or {}).get("subreddit"),
                "score": m.engagement.get("score", 0),
                "replies": m.engagement.get("replies", 0),
                "created_at": m.created_at.isoformat(),
            })
        if len(t["examples"]) < 3:
            t["examples"].append({
                "text": g.representative.text[:200],
                "source": g.representative.source,
                "url": g.representative.url,
                "subreddit": (g.representative.raw or {}).get("subreddit"),
                "score": g.representative.engagement.get("score", 0),
                "spread": g.spread,
            })

    ranked = []
    for topic, d in topics.items():
        spread = len(d["sources"])
        # audience weight = max weight among audiences present (favor dev/algo)
        a_weight = max((aw.get(a, 1.0) for a in d["audiences"]), default=1.0)
        score = d["mentions"] * (1 + 0.5 * (spread - 1)) * a_weight
        dominant_aud = max(d["audiences"], key=d["audiences"].get) if d["audiences"] else "n/a"
        dominant_sent = max(d["sentiments"], key=d["sentiments"].get) if d["sentiments"] else "n/a"
        ranked.append({
            "topic": topic,
            "score": round(score, 1),
            "mentions": d["mentions"],
            "spread": spread,
            "sources": sorted(d["sources"]),
            "engagement": d["engagement"],
            "audience": dominant_aud,
            "sentiment": dominant_sent,
            "examples": d["examples"],
            "members": d["members"],
        })

    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked[:top_n]
