"""Claude-backed social recommendation service with hard failure isolation."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from community.config.log import get_logger
from community.config.settings import settings
from community.llm.client import complete
from community.recommend.compliance import check as compliance_check
from community.social_recommend import context as product_context
from community.social_recommend.evidence import pack
from community.social_recommend.models import GenerationEnvelope, GeneratedRecommendation
from community.store import db, repositories as repo


log = get_logger("social_recommend")
PROMPT_VERSION = "social-ready-copy-v1"

SYSTEM_PROMPT = """You create ready-to-publish social content for Nubra, an Indian
stock broker and trading platform. Use the supplied community evidence to find
real user pain, questions, content demand, or product confusion. Map each idea
to only the supplied Nubra features.

Hard rules:
- The public-facing `hook`, `body`, `cta`, and `hashtags` must be the finished
  marketing post in Nubra's voice. They must be directly copy-pastable without
  rewriting, interpretation, or instructions from a marketing person.
- Never write a brief or meta-instruction inside public copy. Do not say
  "create a post", "the marketing team should", "highlight this feature",
  "content angle", "visual direction", "CTA should", or similar language.
- Do not label public copy with "Hook:", "Body:", "Caption:", or "CTA:".
- Make the post audience-native, specific, benefit-led and confident without
  hype. Explain the product value in language a trader or developer would
  understand immediately. Avoid generic filler.
- Start from the user problem, not a product feature list.
- Never invent a Nubra capability, status, date, price, metric, or comparison.
- A live feature may be described as available. An upcoming feature must be
  explicitly called upcoming, planned, or being developed.
- No investment advice, trade calls, targets, stop-loss levels, predictions,
  guaranteed outcomes, urgency, FOMO, or competitor disparagement.
- Retail and API/developer content must remain separate.
- Write clear product-focused English. No corporate filler and no emojis.
- `body` must be complete, useful copy, not instructions to a writer.
- `rationale` and `visual_brief` are the only fields allowed to contain
  internal reasoning or production instructions.
- Cite only evidence_item_ids and feature_ids present in the input.

Return ONLY one JSON object:
{"recommendations":[{
  "recommendation_key":"short-stable-slug",
  "segment":"retail|api",
  "platform":"linkedin|x|instagram|youtube",
  "format":"text_post|thread|carousel|short_video|product_demo",
  "title":"internal editorial title",
  "hook":"exact public opening",
  "body":"exact public post body",
  "cta":"soft exact CTA",
  "hashtags":["#tag"],
  "feature_ids":["feature_id"],
  "evidence_item_ids":[123],
  "rationale":"why this is useful now, grounded in evidence",
  "visual_brief":"specific image/carousel/video direction",
  "recommended_timing":"plain-language timing",
  "priority_score":0
}]}

Create at most six recommendations. Prefer three retail and three API when both
segments have enough evidence. Every recommendation must stand alone and be
immediately copyable."""

_INTERNAL_COPY_PATTERNS = [
    re.compile(pattern, re.I)
    for pattern in (
        r"\bmarketing team\b",
        r"\bsocial media team\b",
        r"\bcontent team\b",
        r"\bdesign team\b",
        r"\bcreate (?:a|an|the) (?:post|carousel|thread|video|reel)\b",
        r"\bthis post should\b",
        r"\bcontent angle\b",
        r"\bvisual direction\b",
        r"\bfeature to highlight\b",
        r"\bhighlight this feature\b",
        r"\bcta should\b",
        r"\bcampaign should\b",
        r"\bpost idea\b",
        r"(?m)^\s*(?:hook|body|caption|cta)\s*:",
    )
]


def _json_object(raw: str) -> dict[str, Any]:
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Claude response did not contain a JSON object")
    return json.loads(raw[start:end + 1])


def _stable_key(rec: GeneratedRecommendation) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", rec.recommendation_key.lower()).strip("-")[:48]
    digest = hashlib.sha1(
        f"{rec.segment}|{rec.platform}|{rec.title}|{'|'.join(rec.feature_ids)}".encode()
    ).hexdigest()[:10]
    return f"{slug or 'recommendation'}-{digest}"


def _public_copy_issue(text: str) -> str | None:
    """Return the internal/meta phrase that makes copy unsuitable to publish."""
    for pattern in _INTERNAL_COPY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _prompt_payload(days: int) -> tuple[dict[str, Any], dict]:
    evidence, candidates, stats = pack(days=days)
    context = product_context.load()
    payload = {
        "window_days": days,
        "brand": context.brand,
        "claim_guardrails": context.claim_guardrails,
        "features": {
            segment: [feature.model_dump() for feature in features]
            for segment, features in candidates.items()
        },
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
    return payload, stats


def _validate_grounding(
    envelope: GenerationEnvelope,
    payload: dict[str, Any],
) -> list[GeneratedRecommendation]:
    evidence = {item["item_id"]: item for item in payload["evidence"]}
    feature_by_id = {
        feature["id"]: feature
        for features in payload["features"].values()
        for feature in features
    }
    valid: list[GeneratedRecommendation] = []
    for rec in envelope.recommendations:
        if any(item_id not in evidence for item_id in rec.evidence_item_ids):
            log.warning("dropping social recommendation with unknown evidence ids: %s", rec.title)
            continue
        mapped = [feature_by_id.get(feature_id) for feature_id in rec.feature_ids]
        if any(feature is None for feature in mapped):
            log.warning("dropping social recommendation with unknown feature ids: %s", rec.title)
            continue
        if any(feature["segment"] not in {rec.segment, "shared"} for feature in mapped):
            log.warning("dropping cross-segment recommendation: %s", rec.title)
            continue
        if any(evidence[item_id]["segment"] != rec.segment for item_id in rec.evidence_item_ids):
            log.warning("dropping recommendation with cross-segment evidence: %s", rec.title)
            continue
        internal_phrase = _public_copy_issue(rec.exact_copy)
        if internal_phrase:
            log.warning(
                "dropping recommendation containing internal marketing instructions: %s — %r",
                rec.title, internal_phrase,
            )
            continue
        rec.recommendation_key = _stable_key(rec)
        valid.append(rec)
    return valid


def _create_run(days: int, context_version: str) -> int:
    row = db.one(
        """
        INSERT INTO social_recommendation_runs
            (status, model, prompt_version, context_version, window_days)
        VALUES ('running', %s, %s, %s, %s)
        RETURNING id
        """,
        (settings.draft_model, PROMPT_VERSION, context_version, days),
    )
    return row["id"]


def _finish_run(run_id: int, status: str, stats: dict, error: str | None = None) -> None:
    db.execute(
        """
        UPDATE social_recommendation_runs
        SET status=%s, stats=%s, error=%s, completed_at=now()
        WHERE id=%s
        """,
        (status, db.jsonb(stats), error, run_id),
    )


def _persist(run_id: int, recs: list[GeneratedRecommendation], payload: dict[str, Any]) -> int:
    evidence = {item["item_id"]: item for item in payload["evidence"]}
    feature_by_id = {
        feature["id"]: feature
        for features in payload["features"].values()
        for feature in features
    }
    today = datetime.now(timezone.utc).date()
    rows = 0
    with db.tx() as conn:
        for rec in recs:
            mapped_features = [feature_by_id[feature_id] for feature_id in rec.feature_ids]
            source_evidence = [evidence[item_id] for item_id in rec.evidence_item_ids]
            conn.execute(
                """
                INSERT INTO social_recommendations (
                    run_id, day, recommendation_key, segment, platform, post_format,
                    title, hook, body, cta, exact_copy, hashtags, mapped_features,
                    source_evidence, rationale, visual_brief, recommended_timing,
                    priority_score, compliance_status, model, prompt_version,
                    context_version
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    'passed',%s,%s,%s
                )
                """,
                (
                    run_id, today, rec.recommendation_key, rec.segment, rec.platform,
                    rec.format, rec.title, rec.hook, rec.body, rec.cta, rec.exact_copy,
                    rec.hashtags, db.jsonb(mapped_features), db.jsonb(source_evidence),
                    rec.rationale, rec.visual_brief, rec.recommended_timing,
                    rec.priority_score, settings.draft_model, PROMPT_VERSION,
                    product_context.load().version,
                ),
            )
            rows += 1
    return rows


def run(days: int = 30, *, strict: bool = False, force: bool = False) -> dict[str, Any]:
    """Generate and store a recommendation set.

    By default every failure is converted to module-local status. `strict=True`
    is reserved for tests and explicit operational debugging.
    """
    days = max(1, min(days, 90))
    context_summary = product_context.summary()
    run_id: int | None = None
    stats: dict[str, Any] = {"window_days": days, **context_summary}
    try:
        if not force:
            latest = db.one(
                """
                SELECT id, status, stats, error
                FROM social_recommendation_runs
                WHERE created_at::date = (now() AT TIME ZONE 'Asia/Kolkata')::date
                ORDER BY created_at DESC LIMIT 1
                """
            )
            if latest:
                cached_stats = latest.get("stats") or {}
                return {
                    "ok": latest["status"] == "succeeded",
                    "status": "cached",
                    "cached_status": latest["status"],
                    "run_id": latest["id"],
                    "detail": "Today's scheduled generation has already run. Use Generate latest to refresh it.",
                    **stats,
                    **cached_stats,
                }
        run_id = _create_run(days, context_summary["version"])
        if not settings.anthropic_api_key:
            stats["recommendations"] = 0
            _finish_run(run_id, "skipped", stats, "ANTHROPIC_API_KEY is not configured")
            return {"ok": False, "status": "skipped", "run_id": run_id,
                    "detail": "Claude is not configured; all other Beacon modules remain available.",
                    **stats}

        payload, evidence_stats = _prompt_payload(days)
        stats.update(evidence_stats)
        if not payload["evidence"]:
            _finish_run(run_id, "skipped", stats, "No eligible evidence in the selected window")
            return {"ok": False, "status": "skipped", "run_id": run_id,
                    "detail": "No eligible evidence is available yet.", **stats}

        raw, usage = complete(
            settings.draft_model,
            SYSTEM_PROMPT,
            "Create the social recommendations from this evidence pack:\n"
            + json.dumps(payload, ensure_ascii=False, default=str),
            max_tokens=9000,
        )
        envelope = GenerationEnvelope.model_validate(_json_object(raw))
        grounded = _validate_grounding(envelope, payload)
        passed: list[GeneratedRecommendation] = []
        rejected = 0
        for rec in grounded:
            ok, reasons = compliance_check(
                rec.exact_copy,
                "social_recommendation",
                {"kind": "social_recommendation", "key": rec.recommendation_key},
            )
            if ok:
                passed.append(rec)
            else:
                rejected += 1
                log.warning("social recommendation failed compliance: %s — %s", rec.title, reasons)
        if not passed:
            raise ValueError("Claude returned no grounded, compliance-safe recommendations")
        stored = _persist(run_id, passed, payload)
        stats.update({
            "generated": len(envelope.recommendations),
            "grounded": len(grounded),
            "compliance_rejected": rejected,
            "recommendations": stored,
            "usage": usage,
        })
        _finish_run(run_id, "succeeded", stats)
        repo.advance_state(
            "social_recommend", "ready_copy",
            watermark=datetime.now(timezone.utc), items=stored,
        )
        return {"ok": True, "status": "succeeded", "run_id": run_id, **stats}
    except Exception as exc:
        # This module is deliberately a circuit breaker: it records its own
        # failure and returns. It never raises into scraping, existing drafts,
        # the roundup, or unrelated API routes unless a test requests strict.
        log.exception("social recommendation generation failed")
        stats["recommendations"] = 0
        if run_id is not None:
            try:
                _finish_run(run_id, "failed", stats, str(exc)[:1000])
            except Exception:
                log.exception("could not record social recommendation failure")
        try:
            repo.advance_state(
                "social_recommend", "ready_copy",
                items=0, error=str(exc)[:1000],
            )
        except Exception:
            log.exception("could not record social recommendation pipeline state")
        if strict:
            raise
        return {
            "ok": False, "status": "failed", "run_id": run_id,
            "detail": "Social recommendations could not be generated. Other Beacon modules are unaffected.",
            "error": str(exc)[:300], **stats,
        }


def preview(days: int = 30) -> dict[str, Any]:
    """Read-only readiness preview; does not call Claude or write to the DB."""
    payload, stats = _prompt_payload(max(1, min(days, 90)))
    stats["candidate_features"] = {
        segment: len(features) for segment, features in payload["features"].items()
    }
    stats["claude_configured"] = bool(settings.anthropic_api_key)
    return stats
