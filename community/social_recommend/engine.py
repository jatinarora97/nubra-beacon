"""Deterministic social post recommendation engine.

This first version is deliberately non-LLM so it can be tested before Docker
and without Anthropic keys. It turns community/source signals + Nubra context
into ranked post ideas, draft copy and designer-ready creative briefs.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict

from community.social_recommend.models import FeatureContext, SocialRecommendation, SourceSignal


PERSONA_HINTS = {
    "API / Algo User": [
        "api", "websocket", "algo", "sdk", "developer", "historical data", "backtesting",
        "paper trading", "uat", "totp", "static ip", "mcp",
    ],
    "Option Buyer": ["option buyer", "premium", "call", "put", "payoff", "delta", "gamma", "iv", "risk reward"],
    "Option Seller": [
        "option seller", "option selling", "margin", "straddle", "strangle", "hedge",
        "strategy-level", "theta", "p&l based",
    ],
    "OI Trader": ["oi", "open interest", "pcr", "max pain", "volume spike", "oi buildup", "oi concentration"],
    "Scalper": ["scalper", "scalping", "one click", "bid ask", "fill price", "slippage", "quick order", "execution"],
    "Investor": ["investor", "portfolio", "fundamental", "fii", "dii", "watchlist", "sip", "stock sip"],
}

PLATFORM_BY_PERSONA = {
    "API / Algo User": ("LinkedIn", "text_post"),
    "Option Buyer": ("Instagram / LinkedIn", "carousel"),
    "Option Seller": ("LinkedIn", "carousel"),
    "OI Trader": ("YouTube Shorts / Instagram", "video_short"),
    "Scalper": ("YouTube Shorts / X", "video_short"),
    "Investor": ("LinkedIn / Instagram", "carousel"),
}

TYPE_BY_CATEGORY = {
    "api": "developer education",
    "testing": "developer education",
    "analytics": "feature education",
    "options": "feature education",
    "strategy": "feature education",
    "execution": "workflow education",
    "risk": "risk education",
    "alerts": "feature education",
    "scanners": "feature education",
    "funds": "trust/ops education",
    "pricing": "pricing education",
    "market_context": "market education",
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _words(text: str) -> str:
    return _clean(text).lower()


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _hit(term: str, haystack: str) -> bool:
    term = term.lower().strip()
    if not term:
        return False
    plain_term = _plain(term)
    plain_haystack = _plain(haystack)
    if plain_term and plain_term in plain_haystack:
        return True
    if " " in term or "/" in term or "&" in term:
        return term in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack))


def _persona_for(text: str, feature: FeatureContext | None = None) -> str:
    hay = _words(text + " " + (feature.feature if feature else "") + " " + (feature.description if feature else ""))
    scores = {persona: sum(1 for term in terms if _hit(term, hay)) for persona, terms in PERSONA_HINTS.items()}
    best, score = max(scores.items(), key=lambda kv: kv[1])
    return best if score > 0 else "Retail trader"


def _feature_matches(signals: list[SourceSignal], features: list[FeatureContext]) -> dict[str, dict]:
    text = _words(" ".join(s.text for s in signals))
    out: dict[str, dict] = {}
    for f in features:
        # Avoid matching broad category words such as "execution" or "strategy"
        # by themselves; use feature names and explicit keywords only.
        terms = [f.feature, *f.seo_keywords]
        hits = [t for t in terms if _hit(t, text)]
        if not hits:
            continue
        strength = len(set(h.lower() for h in hits))
        out[f.feature] = {
            "feature": f.feature,
            "status": f.status,
            "category": f.category,
            "match_strength": strength,
            "matched_terms": sorted({h for h in hits}, key=str.lower)[:12],
        }
    return out


def _topic_key_for(signal: SourceSignal, feature: FeatureContext | None) -> str:
    if signal.topic_key:
        return signal.topic_key
    if feature:
        return re.sub(r"[^a-z0-9]+", "_", feature.feature.lower()).strip("_")[:80]
    return hashlib.sha1(signal.text.encode("utf-8")).hexdigest()[:12]


def _recommendation_key(topic: str, persona: str, feature_name: str | None) -> str:
    raw = f"{topic}|{persona}|{feature_name or ''}".lower()
    return "social_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _title(feature: FeatureContext | None, persona: str, topic: str) -> str:
    if feature:
        if feature.status == "upcoming":
            return f"Explain the upcoming {feature.feature} workflow for {persona}s"
        return f"Educate {persona}s on {feature.feature}"
    return f"Create a post around {topic.replace('_', ' ')}"


def _summary(feature: FeatureContext | None, persona: str) -> str:
    if feature:
        status = "already available" if feature.status == "live" else "coming up / planned"
        return (
            f"Community signals indicate a content opportunity around {feature.feature}. "
            f"This maps to {persona}s and should be framed as {status} according to Nubra context."
        )
    return f"Community signals indicate a content opportunity for {persona}s."


def _post_angle(feature: FeatureContext | None, persona: str) -> str:
    if not feature:
        return "Turn the repeated user question into a simple educational post with a practical checklist."
    cat = feature.category or "product"
    if cat in {"options", "analytics"}:
        return f"Show how {persona}s can reduce noise and make better sense of the data before placing a trade."
    if cat in {"strategy", "risk"}:
        return "Explain the risk-first workflow: payoff, breakeven, SL/TP, margin and what to check before execution."
    if cat in {"api", "testing"}:
        return "Make the developer workflow clear: what to test, what to monitor, and how to move safely from sandbox to live."
    if cat == "execution":
        return "Explain how the workflow reduces manual friction while keeping order safety and clarity."
    return "Explain the user problem first, then show the Nubra capability or upcoming improvement in simple language."


def _draft_copy(title: str, feature: FeatureContext | None, persona: str) -> str:
    if feature:
        status_line = "Available in Nubra" if feature.status == "live" else "Coming up in Nubra"
        return (
            f"{title}\n\n"
            f"Many {persona.lower()}s do not need more screens — they need the right context at the right moment.\n\n"
            f"{status_line}: {feature.feature}.\n\n"
            f"Why it matters:\n"
            f"- reduces manual checking\n"
            f"- makes the workflow easier to understand\n"
            f"- helps users review risk before acting\n\n"
            f"Use this as an educational post, not a trade recommendation."
        )
    return (
        f"{title}\n\n"
        "A recurring community discussion can be converted into a simple educational post. "
        "Start with the user problem, explain the confusion, and end with a practical checklist."
    )


def _creative_brief(feature: FeatureContext | None, persona: str, format_family: str, signals: list[SourceSignal]) -> str:
    evidence_lines = "\n".join(f"- {s.source}: {_clean(s.text)[:140]}" for s in signals[:3])
    feature_line = feature.feature if feature else "community discussion theme"
    return (
        f"Format: {format_family}\n"
        f"Audience: {persona}\n"
        f"Topic: {feature_line}\n"
        f"Design direction: clean trading-product education, minimal clutter, one main idea per frame.\n"
        f"Must show: user problem, why it matters, key workflow/checklist, Nubra context if claim-safe.\n"
        f"Do not show: profit guarantees, buy/sell calls, aggressive competitor claims.\n\n"
        f"Evidence snippets:\n{evidence_lines}"
    )


def build_recommendations(
    signals: list[SourceSignal],
    features: list[FeatureContext],
    *,
    max_count: int = 12,
) -> list[SocialRecommendation]:
    """Build ranked social recommendations from already-collected signals."""
    if not signals:
        return []

    grouped: dict[str, list[SourceSignal]] = defaultdict(list)
    group_feature: dict[str, FeatureContext | None] = {}
    for signal in signals:
        matches = _feature_matches([signal], features)
        best_feature = None
        if matches:
            best_name = max(matches.values(), key=lambda m: m["match_strength"])["feature"]
            best_feature = next((f for f in features if f.feature == best_name), None)
        topic = _topic_key_for(signal, best_feature)
        grouped[topic].append(signal)
        group_feature.setdefault(topic, best_feature)

    recs: list[SocialRecommendation] = []
    for topic, items in grouped.items():
        feature = group_feature.get(topic)
        all_matches = list(_feature_matches(items, features).values())
        persona = _persona_for(" ".join(i.text for i in items), feature)
        platform, format_family = PLATFORM_BY_PERSONA.get(persona, ("LinkedIn", "text_post"))
        engagement = sum(float(i.engagement_score or 0) for i in items)
        sources = len({i.source for i in items})
        frequency = len(items)
        feature_boost = max([m["match_strength"] for m in all_matches] or [0])
        priority = round(min(100.0, 15 + frequency * 7 + math.log1p(engagement) * 10 + sources * 8 + feature_boost * 3), 2)
        title = _title(feature, persona, topic)
        reason = (
            f"{frequency} signal(s) across {sources} source(s), mapped to "
            f"{feature.feature if feature else topic.replace('_', ' ')} with priority score {priority}."
        )
        recs.append(
            SocialRecommendation(
                recommendation_key=_recommendation_key(topic, persona, feature.feature if feature else None),
                title=title,
                summary=_summary(feature, persona),
                recommendation_type=TYPE_BY_CATEGORY.get((feature.category if feature else "") or "", "educational post"),
                target_persona=persona,
                platform=platform,
                format_family=format_family,
                priority_score=priority,
                mapped_features=all_matches[:5],
                source_signals=[s.model_dump(mode="json") for s in sorted(items, key=lambda s: s.engagement_score, reverse=True)[:8]],
                reason=reason,
                post_angle=_post_angle(feature, persona),
                draft_copy=_draft_copy(title, feature, persona),
                creative_brief=_creative_brief(feature, persona, format_family, items),
            )
        )

    return sorted(recs, key=lambda r: r.priority_score, reverse=True)[:max_count]
