"""Cheap relevance gate. No LLM. Drops most junk before any token spend."""
from __future__ import annotations

from ..pipeline.dedupe import DedupGroup


def prefilter(groups: list[DedupGroup], cfg: dict) -> list[DedupGroup]:
    pf = cfg.get("prefilter", {})
    keywords = [k.lower() for k in pf.get("keywords", [])]
    min_chars = int(pf.get("min_chars", 20))

    kept = []
    for g in groups:
        text = g.representative.text.lower()
        if len(text.strip()) < min_chars:
            continue
        if keywords and not any(k in text for k in keywords):
            continue
        kept.append(g)
    return kept
