"""Build a bounded, deduplicated evidence pack from Beacon's existing data."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

from community.social_recommend.context import ProductContext, ProductFeature
from community.social_recommend.models import EvidenceItem
from community.store import db


API_TERMS = {
    "api", "sdk", "websocket", "developer", "algo", "algorithmic", "automation",
    "backtest", "historical data", "rest api", "python", "github", "uat",
    "sandbox", "totp", "static ip", "webhook", "rate limit", "latency",
}
RETAIL_TERMS = {
    "option chain", "brokerage", "watchlist", "portfolio", "margin", "payoff",
    "futures", "options", "trader", "investor", "order", "alert", "scanner",
    "chart", "withdrawal", "fund", "slippage", "open interest", "pcr",
}


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _contains(haystack: str, term: str) -> bool:
    term = _normal(term)
    return bool(term and re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack))


def classify_segment(text: str, source: str = "", topic: str = "") -> str:
    haystack = _normal(f"{text} {source} {topic}")
    api = sum(_contains(haystack, term) for term in API_TERMS)
    retail = sum(_contains(haystack, term) for term in RETAIL_TERMS)
    if source.lower() == "github":
        api += 2
    return "api" if api > retail and api > 0 else "retail"


def _engagement(value: object) -> float:
    if not isinstance(value, dict):
        return 0
    try:
        direct = float(value.get("score") or 0)
    except (TypeError, ValueError):
        direct = 0
    native = value.get("native")
    if not isinstance(native, dict):
        return direct
    weights = {
        "likes": 1, "upvotes": 1, "score": 1, "comments": 2, "replies": 2,
        "shares": 3, "views": 0.01, "stars": 2, "downloads": 0.1,
    }
    total = direct
    for key, weight in weights.items():
        try:
            total += float(native.get(key) or 0) * weight
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def load(days: int = 30, limit: int = 800, per_source: int = 35) -> list[EvidenceItem]:
    rows = db.query(
        """
        SELECT si.item_id, si.source, si.source_type, si.text, si.url,
               si.created_at, si.engagement, ie.topic_key, ie.intent
        FROM social_items si
        LEFT JOIN item_enrichment ie ON ie.item_id = si.item_id
        WHERE si.duplicate_of IS NULL
          AND si.created_at >= now() - (%s || ' days')::interval
          AND length(trim(COALESCE(si.text, ''))) >= 24
          AND COALESCE(ie.is_noise, false) = false
        ORDER BY si.created_at DESC
        LIMIT %s
        """,
        (max(1, min(days, 180)), max(50, min(limit, 3000))),
    )
    now = datetime.now(timezone.utc)
    candidates: list[tuple[float, EvidenceItem]] = []
    seen_text: set[str] = set()
    for row in rows:
        normalized = _normal(row.get("text") or "")
        fingerprint = normalized[:400]
        if not fingerprint or fingerprint in seen_text:
            continue
        seen_text.add(fingerprint)
        created = row.get("created_at")
        age_days = max(0, (now - created).total_seconds() / 86400) if created else days
        recency = max(0, 20 - age_days)
        intent_boost = 12 if row.get("intent") in {"feature_request", "question", "comparison"} else 0
        score = _engagement(row.get("engagement")) + recency + intent_boost
        segment = classify_segment(
            row.get("text") or "", row.get("source") or "", row.get("topic_key") or ""
        )
        candidates.append((
            score,
            EvidenceItem(
                item_id=row["item_id"],
                source=row["source"],
                source_type=row["source_type"],
                text=(row.get("text") or "").strip()[:1800],
                url=row.get("url") or "",
                created_at=created.isoformat() if created else None,
                topic_key=row.get("topic_key"),
                intent=row.get("intent"),
                engagement_score=_engagement(row.get("engagement")),
                segment=segment,
            ),
        ))

    selected: list[EvidenceItem] = []
    source_counts: dict[tuple[str, str], int] = defaultdict(int)
    segment_counts: dict[str, int] = defaultdict(int)
    for _, item in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        source_key = (item.segment, item.source)
        if source_counts[source_key] >= per_source or segment_counts[item.segment] >= 120:
            continue
        source_counts[source_key] += 1
        segment_counts[item.segment] += 1
        selected.append(item)
    return selected


def feature_candidates(
    context: ProductContext,
    evidence: Iterable[EvidenceItem],
    segment: str,
    limit: int = 24,
) -> list[ProductFeature]:
    rows = [item for item in evidence if item.segment == segment]
    haystack = _normal(" ".join(item.text for item in rows))
    scored: list[tuple[int, ProductFeature]] = []
    stopwords = {
        "with", "from", "based", "mode", "trading", "support", "price",
        "data", "order", "option", "options", "feature",
    }
    for feature in context.features:
        if feature.segment not in {segment, "shared"}:
            continue
        terms = [feature.name, *feature.keywords]
        score = 6 if _contains(haystack, feature.name) else 0
        score += 2 * sum(_contains(haystack, term) for term in feature.keywords)
        # Community wording rarely repeats a catalogue label exactly. Add a
        # conservative distinctive-token overlap so "OI ... filters in the
        # option chain" still maps to "Option-chain filters and saved modes".
        tokens = {
            token for token in _normal(" ".join(terms)).split()
            if len(token) >= 3 and token not in stopwords
        }
        score += min(6, sum(_contains(haystack, token) for token in tokens))
        if score:
            scored.append((score, feature))
    # If the collected evidence is quiet, include a small catalogue fallback so
    # Claude can still map an adjacent pain point without inventing a feature.
    if len(scored) < 8:
        included = {feature.id for _, feature in scored}
        for feature in context.features:
            if feature.segment in {segment, "shared"} and feature.id not in included:
                scored.append((0, feature))
    return [feature for _, feature in sorted(scored, key=lambda pair: (-pair[0], pair[1].name))[:limit]]


def pack(days: int = 30) -> tuple[list[EvidenceItem], dict[str, list[ProductFeature]], dict]:
    from community.social_recommend.context import load as load_context

    context = load_context()
    items = load(days=days)
    features = {
        segment: feature_candidates(context, items, segment)
        for segment in ("retail", "api")
    }
    stats = {
        "items": len(items),
        "sources": sorted({item.source for item in items}),
        "retail_items": sum(item.segment == "retail" for item in items),
        "api_items": sum(item.segment == "api" for item in items),
        "context_version": context.version,
        "context_features": len(context.features),
    }
    return items, features, stats
