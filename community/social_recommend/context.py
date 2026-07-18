"""Nubra product context for social recommendations — DB-backed.

Rewired 2026-07-18 (dual-grounding resolution): features come from the SAME
versioned `nubra_features` catalog that grounds drafts and briefs and that the
Grounding page edits (context-v2 as of the rewire). The engine's private YAML
is gone — one catalog, one approval surface, no drift. Brand voice, claim
guardrails and personas are engine-specific prompt scaffolding and live here
as constants (ported verbatim from the retired YAML).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── prompt scaffolding (engine-specific, not feature data) ──────────────────

BRAND: dict[str, Any] = {
    "name": "Nubra",
    "category": "Indian stock broker and trading platform",
    "positioning": (
        "Nubra serves retail investors, active equity and derivatives traders, "
        "options personas, strategy traders, scalpers, and API/algo developers.\n"
    ),
}

CLAIM_GUARDRAILS: list[str] = [
    "Claim a feature as available only when its status is live.",
    "Describe upcoming features as upcoming, planned, or being developed.",
    "Never invent launch dates, performance claims, or market-leading claims.",
    "Do not give investment advice, trade calls, targets, or guaranteed outcomes.",
    "Keep competitor comparisons factual, fair, and grounded in collected evidence.",
]

PERSONAS: list[dict[str, Any]] = [
    {"id": "investor", "context": "Long-term or delivery-focused user who cares about "
     "fundamentals, holdings, portfolio health and stock research."},
    {"id": "option_buyer", "context": "Focused on premium movement, momentum, strike "
     "selection, liquidity, fast execution and risk-defined entries."},
    {"id": "option_seller", "context": "Focused on OI, IV, theta, margin, payoff, "
     "probability, risk-reward and strategy-level protection."},
    {"id": "oi_trader", "context": "Trades using open interest, OI buildup, PCR, max "
     "pain, volume, IV and strike-level positioning."},
    {"id": "scalper", "context": "Active intraday user who needs speed, one-click "
     "actions, bid/ask visibility and fast order modification."},
    {"id": "strategy_trader", "context": "Builds multi-leg strategies and cares about "
     "payoff, breakeven, margin and strategy-level tracking."},
    {"id": "api_algo_user", "context": "Builds systematic strategies, backtests, "
     "integrations and automated trading systems on the API/SDK."},
]


class ProductFeature(BaseModel):
    id: str
    name: str
    status: str
    segment: str
    category: str
    surfaces: list[str] = Field(default_factory=list)
    personas: list[str] = Field(default_factory=list)
    description: str
    keywords: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        if value not in {"live", "upcoming"}:
            raise ValueError("status must be live or upcoming")
        return value

    @field_validator("segment")
    @classmethod
    def valid_segment(cls, value: str) -> str:
        if value not in {"retail", "api", "shared"}:
            raise ValueError("segment must be retail, api, or shared")
        return value


class ProductContext(BaseModel):
    version: str
    updated_at: str
    brand: dict[str, Any]
    claim_guardrails: list[str]
    personas: list[dict[str, Any]]
    features: list[ProductFeature]


def load(path: Any = None) -> ProductContext:
    """Build the context from the current nubra_features catalog. The `path`
    argument is retired (accepted and ignored so old call sites stay valid)."""
    from community.reference import features as catalog
    from community.store import db

    rows = catalog.current()
    if not rows:
        raise ValueError("nubra_features has no current rows — seed the catalog first")
    feats = [
        ProductFeature(
            id=f"f_{r['id']}",
            name=r["feature"],
            status=r["status"],
            segment="api" if (r["category"] or "") == "api" else "retail",
            category=r["category"] or "general",
            description=r["description"],
            keywords=list(r["seo_keywords"] or []),
        )
        for r in rows
    ]
    ids = [f.id for f in feats]
    if len(ids) != len(set(ids)):
        raise ValueError("nubra_features current rows produced duplicate feature ids")
    published = db.one(
        "SELECT max(published_at)::date AS d FROM nubra_features WHERE is_current")
    return ProductContext(
        version=rows[0]["version"],
        updated_at=str(published["d"]) if published and published["d"] else "",
        brand=BRAND,
        claim_guardrails=CLAIM_GUARDRAILS,
        personas=PERSONAS,
        features=feats,
    )


def summary(path: Any = None) -> dict[str, Any]:
    context = load()
    return {
        "version": context.version,
        "updated_at": context.updated_at,
        "feature_count": len(context.features),
        "live_features": sum(feature.status == "live" for feature in context.features),
        "upcoming_features": sum(feature.status == "upcoming" for feature in context.features),
        "retail_features": sum(feature.segment in {"retail", "shared"} for feature in context.features),
        "api_features": sum(feature.segment in {"api", "shared"} for feature in context.features),
    }
