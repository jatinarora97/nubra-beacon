"""Thin Anthropic wrapper: sync enrichment batches + a generic completion helper.

Local mode runs sync calls; prod moves enrichment to the Batch API (cost plan §2.1).
Every call is recorded to llm_usage (+ Langfuse when keys are configured) via
community/llm/trace.py — tracing never breaks or delays a call.
"""
from __future__ import annotations

import json
import pathlib
from typing import Literal

import anthropic
from pydantic import BaseModel, Field, ValidationError

from community.config.settings import settings
from community.llm import trace
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


def _build_prompt(items: list[dict]) -> str:
    taxonomy = "\n".join(f"- {k}: {label}" for k, (label, _) in TOPICS.items())
    return _PROMPT.replace("{taxonomy}", taxonomy) \
                  .replace("{issue_types}", ", ".join(ISSUE_TYPES)) \
                  .replace("{items}", json.dumps(items, ensure_ascii=False, default=str))


def enrich_batch(items: list[dict]) -> tuple[EnrichResponse, dict]:
    """SYNC path: items: [{id, source, text, thread_hint}] → validated response +
    usage. Retries ≤2 appending the validation error; raises EnrichError after."""
    prompt = _build_prompt(items)
    expected = [str(i["id"]) for i in items]
    messages = [{"role": "user", "content": prompt}]
    usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    last_err = None
    for _ in range(3):
        with trace.timer() as t:
            resp = client().messages.create(
                model=settings.enrich_model, max_tokens=8000, messages=messages
            )
        usage["input_tokens"] += resp.usage.input_tokens
        usage["output_tokens"] += resp.usage.output_tokens
        usage["calls"] += 1
        raw = next((b.text for b in resp.content if b.type == "text"), "")
        trace.record(model=settings.enrich_model,
                     input_tokens=resp.usage.input_tokens,
                     output_tokens=resp.usage.output_tokens,
                     duration_ms=t.ms, prompt=prompt, response=raw,
                     metadata={"items": len(items), "attempt": usage["calls"]})
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


def enrich_via_batch_api(
    chunks: list[list[dict]], *, sla_minutes: float = 25, poll_seconds: float = 20,
) -> tuple[dict[int, EnrichResponse | None], dict]:
    """Message Batches API path (−50%, cost plan §2.1). One request per chunk,
    custom_id = chunk index. Polls until ended or the SLA; on SLA breach the
    batch is cancelled and every unresolved chunk maps to None (caller falls
    back to the sync path). Per-chunk validation failure / errored / expired
    also map to None. Returns ({chunk_idx: EnrichResponse|None}, usage)."""
    import time as _time

    usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "batch_id": None}
    requests = [
        {"custom_id": f"chunk_{i}",
         "params": {"model": settings.enrich_model, "max_tokens": 8000,
                    "messages": [{"role": "user", "content": _build_prompt(chunk)}]}}
        for i, chunk in enumerate(chunks)
    ]
    t0 = _time.monotonic()
    batch = client().messages.batches.create(requests=requests)
    usage["batch_id"] = batch.id
    print(f"[enrich] batch {batch.id} submitted ({len(chunks)} chunks) — polling")

    deadline = _time.monotonic() + sla_minutes * 60
    while True:
        b = client().messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        if _time.monotonic() > deadline:
            try:
                client().messages.batches.cancel(batch.id)
            except Exception:  # noqa: BLE001 — cancel is best-effort
                pass
            print(f"[enrich] batch {batch.id} exceeded {sla_minutes}min SLA — "
                  "cancelled, falling back to sync for this pass")
            trace.record(model=settings.enrich_model, input_tokens=0, output_tokens=0,
                         duration_ms=int((_time.monotonic() - t0) * 1000), batch=True,
                         metadata={"batch_id": batch.id, "chunks": len(chunks),
                                   "succeeded": 0, "sla_breached": True})
            return {i: None for i in range(len(chunks))}, usage
        _time.sleep(poll_seconds)

    out: dict[int, EnrichResponse | None] = {i: None for i in range(len(chunks))}
    for result in client().messages.batches.results(batch.id):
        idx = int(result.custom_id.split("_")[1])
        if result.result.type != "succeeded":
            print(f"[enrich] batch chunk {idx}: {result.result.type} — sync retry")
            continue
        msg = result.result.message
        usage["input_tokens"] += msg.usage.input_tokens
        usage["output_tokens"] += msg.usage.output_tokens
        usage["calls"] += 1
        raw = next((blk.text for blk in msg.content if blk.type == "text"), "")
        expected = [str(it["id"]) for it in chunks[idx]]
        try:
            out[idx] = _validate(raw, expected)
        except (ValueError, ValidationError, json.JSONDecodeError) as e:
            print(f"[enrich] batch chunk {idx} failed validation ({e}) — sync retry")
    # one llm_usage row per submitted batch: aggregate tokens, -50% batch pricing
    trace.record(model=settings.enrich_model,
                 input_tokens=usage["input_tokens"],
                 output_tokens=usage["output_tokens"],
                 duration_ms=int((_time.monotonic() - t0) * 1000), batch=True,
                 metadata={"batch_id": batch.id, "chunks": len(chunks),
                           "succeeded": sum(1 for v in out.values() if v)})
    return out, usage


def complete(model: str, system: str, user: str, max_tokens: int = 2000) -> tuple[str, dict]:
    """Generic single completion (used by recommend/compliance — Fork C)."""
    with trace.timer() as t:
        resp = client().messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
    usage = {"input_tokens": resp.usage.input_tokens,
             "output_tokens": resp.usage.output_tokens, "calls": 1}
    text = next((b.text for b in resp.content if b.type == "text"), "")
    trace.record(model=model, input_tokens=resp.usage.input_tokens,
                 output_tokens=resp.usage.output_tokens, duration_ms=t.ms,
                 prompt=user, system=system, response=text)
    return text, usage
