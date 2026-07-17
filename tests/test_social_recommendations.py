"""Focused tests for the isolated social recommendation module."""
from __future__ import annotations

import json

import pytest

from community.social_recommend import context
from community.social_recommend.evidence import classify_segment
from community.social_recommend.models import GenerationEnvelope
from community.social_recommend.service import (
    _json_object,
    _public_copy_issue,
    _validate_grounding,
)


def test_context_is_comprehensive_and_valid():
    catalog = context.load()
    ids = {feature.id for feature in catalog.features}
    assert len(catalog.features) >= 45
    assert len(ids) == len(catalog.features)
    assert {"flexible_brokerage", "option_chain_filters", "api_access", "nubra_uat"} <= ids
    assert any(feature.segment == "retail" for feature in catalog.features)
    assert any(feature.segment == "api" for feature in catalog.features)


@pytest.mark.parametrize(
    ("text", "source", "expected"),
    [
        ("Websocket disconnects while running my Python algo", "github", "api"),
        ("Need OI and IV filters in the option chain", "reddit", "retail"),
        ("Historical candle API date range is unclear", "youtube", "api"),
        ("Brokerage and payoff are hard to compare", "app_store", "retail"),
    ],
)
def test_segment_classification(text, source, expected):
    assert classify_segment(text, source) == expected


def test_json_object_accepts_fenced_or_prefixed_response():
    payload = {"recommendations": []}
    assert _json_object("Result:\n```json\n" + json.dumps(payload) + "\n```") == payload


@pytest.mark.parametrize(
    "copy",
    [
        "The marketing team should create a post about option-chain filters.",
        "Content angle: explain Nubra UAT to API developers.",
        "Hook: Test integrations before production.\nCTA: Try Nubra.",
        "This post should highlight this feature for option sellers.",
    ],
)
def test_internal_marketing_instructions_are_not_publishable(copy):
    assert _public_copy_issue(copy)


def test_finished_public_copy_passes_meta_instruction_gate():
    copy = (
        "Trading integrations need a safe place to fail before production.\n\n"
        "Nubra UAT lets API developers test supported order workflows before "
        "moving to production.\n\nWhat do you test first?"
    )
    assert _public_copy_issue(copy) is None


def test_grounding_rejects_unknown_evidence_and_cross_segment_features():
    payload = {
        "evidence": [
            {"item_id": 10, "segment": "retail", "text": "OI filters", "source": "reddit"},
            {"item_id": 20, "segment": "api", "text": "websocket", "source": "github"},
        ],
        "features": {
            "retail": [{"id": "retail_feature", "segment": "retail", "name": "OI filters"}],
            "api": [{"id": "api_feature", "segment": "api", "name": "Websocket"}],
        },
    }
    base = {
        "recommendation_key": "key",
        "platform": "linkedin",
        "format": "text_post",
        "title": "Title",
        "hook": "Hook",
        "body": "Body",
        "cta": "CTA",
        "hashtags": [],
        "rationale": "Reason",
        "visual_brief": "Visual",
        "priority_score": 80,
    }
    envelope = GenerationEnvelope.model_validate({
        "recommendations": [
            {**base, "segment": "retail", "feature_ids": ["retail_feature"],
             "evidence_item_ids": [10]},
            {**base, "recommendation_key": "bad-evidence", "segment": "retail",
             "feature_ids": ["retail_feature"], "evidence_item_ids": [999]},
            {**base, "recommendation_key": "bad-feature", "segment": "retail",
             "feature_ids": ["api_feature"], "evidence_item_ids": [10]},
            {**base, "recommendation_key": "internal-brief", "segment": "retail",
             "body": "The marketing team should create a post about OI filters.",
             "feature_ids": ["retail_feature"], "evidence_item_ids": [10]},
        ]
    })
    valid = _validate_grounding(envelope, payload)
    assert len(valid) == 1
    assert valid[0].segment == "retail"
