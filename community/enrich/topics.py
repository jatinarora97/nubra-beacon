"""Active topic taxonomy, DB-first (work plan E1).

The static `reference.taxonomy.TOPICS` dict is the seed; once emergent-topic
discovery can ACTIVATE suggested topics from the UI, the live list must come
from the DB (status='active') so activated topics reach the enrichment prompt
without a deploy. Static dict remains the fallback when the DB is unreachable
(scrape-time resilience).

NOTE (wiring): community/llm/client.py still builds its prompt + validation
from the static TOPICS import. Until it is switched to `active_topics()`,
activated suggestions are inert (never offered to the LLM) — safe, but not
live. The 3-line client.py patch is in the Phase 5 report.
"""
from __future__ import annotations

from community.reference.taxonomy import TOPICS
from community.store import db


def active_topics() -> dict[str, tuple[str, bool]]:
    """topic_key -> (label, evergreen) for status='active' rows; static fallback."""
    try:
        rows = db.query(
            "SELECT topic_key, label, evergreen FROM topic_taxonomy "
            "WHERE status = 'active' ORDER BY topic_key")
    except Exception:  # noqa: BLE001 — DB down: fall back to the seed
        return dict(TOPICS)
    if not rows:
        return dict(TOPICS)
    return {r["topic_key"]: (r["label"], r["evergreen"]) for r in rows}
