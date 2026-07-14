"""Typed contracts for social recommendation generation."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SourceSignal(BaseModel):
    source: str
    source_type: str
    text: str
    url: str = ""
    topic_key: str | None = None
    intent: str | None = None
    audience: str | None = None
    engagement_score: float = 0.0
    created_at: str | None = None
    raw: dict = Field(default_factory=dict)


class FeatureContext(BaseModel):
    id: str | None = None
    feature: str
    description: str
    status: str
    category: str | None = None
    seo_keywords: list[str] = Field(default_factory=list)


class SocialRecommendation(BaseModel):
    recommendation_key: str
    title: str
    summary: str
    recommendation_type: str
    target_persona: str
    platform: str
    format_family: str
    priority_score: float
    mapped_features: list[dict] = Field(default_factory=list)
    source_signals: list[dict] = Field(default_factory=list)
    reason: str
    post_angle: str
    draft_copy: str
    creative_brief: str
