"""Versioned Nubra product context used only by social recommendations.

The recommendation module reads this file directly so its grounding does not
depend on the editable `nubra_features` database catalog. Existing Beacon
modules continue to use that table and are therefore unaffected.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "data" / "nubra_context" / "social_features.yaml"


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


def load(path: str | Path | None = None) -> ProductContext:
    context_path = Path(path) if path else DEFAULT_PATH
    data = yaml.safe_load(context_path.read_text(encoding="utf-8"))
    context = ProductContext.model_validate(data)
    ids = [feature.id for feature in context.features]
    if len(ids) != len(set(ids)):
        raise ValueError("Nubra social context contains duplicate feature ids")
    return context


def summary(path: str | Path | None = None) -> dict[str, Any]:
    context = load(path)
    return {
        "version": context.version,
        "updated_at": context.updated_at,
        "feature_count": len(context.features),
        "live_features": sum(feature.status == "live" for feature in context.features),
        "upcoming_features": sum(feature.status == "upcoming" for feature in context.features),
        "retail_features": sum(feature.segment in {"retail", "shared"} for feature in context.features),
        "api_features": sum(feature.segment in {"api", "shared"} for feature in context.features),
    }
