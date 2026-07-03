"""Thin Anthropic wrapper: sync enrichment batches + a generic completion helper.

Local mode runs sync calls; prod moves enrichment to the Batch API (cost plan §2.1).
Token usage is printed to stdout (llm_usage table is a prod reuse, absent locally).
"""
from __future__ import annotations

import json
import pathlib
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from community.config.settings import settings
from community.reference.taxonomy import ISSUE_TYPES, TOPICS

_PROMPT = (pathlib.Path(__file__).parent / "prompts" / "enrich.txt").read_text()

_client: anthropic.Anthropic | None = None


class EnrichError(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


class Entities(BaseModel):
    broker: str | None = None
    issue_type: str | None = None
    feature_phrase: str | None = None
    summary: str | None = None


class EnrichedItem(BaseModel):
    id: str
    audience: Literal["active_trader", "long_term_investor", "beginner",
                      "influencer", "other"] | None = None
    intent: Literal["complaint", "feature_request", "question", "praise",
                    "comparison", "how_to", "news_opinion", "spam"]
    topic_key: str
    sentiment: float | None = Field(default=None, ge=-1, le=1)
    entities: Entities = Field(default_factory=Entities)
    is_noise: bool = False


class EnrichResponse(BaseModel):
    items: list[EnrichedItem]


def _validate(raw: str, expected_ids: list[str]) -> EnrichResponse:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`\n")
        if text.startswith("json"):
            text = text[4:]
    parsed = EnrichResponse.model_validate(json.loads(text))
    got = [i.id for i in parsed.items]
    if sorted(got) != sorted(expected_ids):
        raise ValueError(f"id mismatch: expected {expected_ids}, got {got}")
    valid_keys = set(TOPICS)
    for it in parsed.items:
        if it.topic_key not in valid_keys and not it.topic_key.startswith("other:"):
            raise ValueError(f"invalid topic_key {it.topic_key!r} for id {it.id}")
        if it.entities.issue_type is not None and it.entities.issue_type not in ISSUE_TYPES:
            it.entities.issue_type = None  # soft-drop invalid issue types
    return parsed


def enrich_batch(items: list[dict]) -> tuple[EnrichResponse, dict]:
    """items: [{id, source, text, thread_hint}] → validated response + usage.
    Retries ≤2 appending the validation error; raises EnrichError after."""
    taxonomy = "\n".join(f"- {k}: {label}" for k, (label, _) in TOPICS.items())
    prompt = _PROMPT.replace("{taxonomy}", taxonomy) \
                    .replace("{issue_types}", ", ".join(ISSUE_TYPES)) \
                    .replace("{items}", json.dumps(items, ensure_ascii=False, default=str))
    expected = [str(i["id"]) for i in items]
    messages = [{"role": "user", "content": prompt}]
    usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    last_err = None
    for _ in range(3):
        resp = client().messages.create(
            model=settings.enrich_model, max_tokens=8000, messages=messages
        )
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        usage["calls"] += 1
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return _validate(raw, expected), usage
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            last_err = e
            messages = messages[:1] + [
                {"role": "assistant", "content": raw},
                {"role": "user",
                 "content": f"Your last output failed validation: {e}. "
                            "Return ONLY the corrected JSON object."},
            ]
    raise EnrichError(f"batch failed after retries: {last_err}")


def complete(model: str, system: str, user: str, max_tokens: int = 2000) -> tuple[str, dict]:
    """Generic single completion (used by recommend/compliance — Fork C)."""
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}],
    )
    usage = {"input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens, "calls": 1}
    return next((b.text for b in resp.content if b.type == "text"), ""), usage
