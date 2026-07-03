"""Cross-source near-duplicate collapse.

Exact dupes -> content_hash. Near-dupes -> token-set Jaccard (cheap, dependency-free
stand-in for MinHash/SimHash). The same tip pasted across many channels collapses to
one representative, but we keep the list of sources it appeared in (spread signal).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..schema import RawItem

_TOK = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOK.findall((text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class DedupGroup:
    representative: RawItem
    members: list[RawItem] = field(default_factory=list)

    @property
    def sources(self) -> set[str]:
        return {m.source for m in self.members}

    @property
    def spread(self) -> int:
        """Distinct sources this content appeared in — cross-source pulse signal."""
        return len(self.sources)


def dedupe(items: list[RawItem], threshold: float = 0.8) -> list[DedupGroup]:
    groups: list[DedupGroup] = []
    tok_cache: list[set[str]] = []
    for it in items:
        toks = _tokens(it.text)
        placed = False
        for g, gt in zip(groups, tok_cache):
            if it.hash == g.representative.hash or _jaccard(toks, gt) >= threshold:
                g.members.append(it)
                placed = True
                break
        if not placed:
            groups.append(DedupGroup(representative=it, members=[it]))
            tok_cache.append(toks)
    return groups
