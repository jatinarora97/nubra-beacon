"""Validated contracts for evidence selection and Claude output."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class EvidenceItem(BaseModel):
    item_id: int
    source: str
    source_type: str
    text: str
    url: str = ""
    created_at: str | None = None
    topic_key: str | None = None
    intent: str | None = None
    engagement_score: float = 0
    segment: Literal["retail", "api"]


class GeneratedRecommendation(BaseModel):
    recommendation_key: str
    segment: Literal["retail", "api"]
    platform: Literal["linkedin", "x", "instagram", "youtube"]
    format: Literal["text_post", "thread", "carousel", "short_video", "product_demo"]
    title: str
    hook: str
    body: str
    cta: str
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    feature_ids: list[str] = Field(min_length=1, max_length=5)
    evidence_item_ids: list[int] = Field(min_length=1, max_length=10)
    rationale: str
    visual_brief: str
    recommended_timing: str = ""
    priority_score: float = Field(ge=0, le=100)

    @field_validator("title", "hook", "body", "cta", "rationale", "visual_brief")
    @classmethod
    def non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("field cannot be empty")
        return value

    @property
    def exact_copy(self) -> str:
        parts = [self.hook, self.body, self.cta]
        if self.hashtags:
            parts.append(" ".join(self.hashtags))
        return "\n\n".join(part.strip() for part in parts if part.strip())


class GenerationEnvelope(BaseModel):
    recommendations: list[GeneratedRecommendation] = Field(min_length=1, max_length=8)
