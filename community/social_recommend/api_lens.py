"""API-trading content queue — the api_trading lens on the social engine.

Keeps a small stock of ready-to-post, grounded briefs per platform for the
interns seeding API/algo content (plan: docs/api-content-queue-plan-2026-09-09.md).
Evidence comes from the api_trader_items lens (real threads), features from
the product context (api/shared only), compliance from the same guardrails
as the general path. Rides the hourly compose stage via top_up(), which
generates only the per-platform shortfall — most hours it spends nothing.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from community.config.log import get_logger
from community.config.settings import settings
from community.llm.client import complete
from community.recommend.compliance import check as compliance_check
from community.social_recommend import context as product_context
from community.social_recommend.service import _json_object, _public_copy_issue
from community.store import db, repositories as repo

log = get_logger("social_recommend.api_lens")

LENS = "api_trading"
PROMPT_VERSION = "api-lens-copy-v1"
PLATFORMS = ("reddit", "x", "linkedin", "youtube_community")


class ApiLensRec(BaseModel):
    recommendation_key: str
    platform: Literal["reddit", "x", "linkedin", "youtube_community"]
    content_type: Literal["seed_reply", "standalone"]
    title: str
    hook: str
    body: str
    cta: str
    hashtags: list[str] = Field(default_factory=list, max_length=6)
    feature_ids: list[str] = Field(min_length=1, max_length=4)
    evidence_item_ids: list[int] = Field(min_length=1, max_length=6)
    seed_url: str | None = None
    rationale: str
    recommended_timing: str = ""
    priority_score: float = Field(ge=0, le=100)

    @field_validator("title", "hook", "body", "rationale")
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
        return "\n\n".join(p.strip() for p in parts if p.strip())


class ApiLensEnvelope(BaseModel):
    recommendations: list[ApiLensRec]


_SYSTEM = """You create ready-to-post content for Nubra's API/algo-trading audience:
Indian traders who trade via code, APIs and automation. The people posting are
interns — every piece must be finished, publishable copy with zero rewriting.

Two content types:
- "seed_reply": a genuinely helpful reply posted INTO the given community
  thread (seed_url). It must answer the thread's actual question first, in a
  practitioner's voice, and disclose the Nubra affiliation naturally (e.g.
  "(I work at Nubra)"). Mention Nubra only where its supplied feature honestly
  answers the question. Never more than one soft Nubra mention.
- "standalone": an original post for the platform (educational or product-fact
  led), grounded in what the evidence shows people struggle with.

Platform norms:
- reddit: plain text, no hashtags, no marketing tone, disclosure mandatory,
  markdown ok. Being useful IS the content.
- x: <= 260 chars per post or a 2-4 tweet thread (separate tweets with a line
  containing only "---"). At most 2 hashtags.
- linkedin: 80-180 words, professional but concrete, max 3 hashtags.
- youtube_community: short discussion-starter or poll-style text, no hashtags.

Hard rules (violations get the piece rejected):
- NEVER reference past performance, returns, win rates, or expected profits of
  any algo or strategy — not Nubra's, not anyone's (SEBI/exchange ad code).
- No investment advice, trade calls, predictions, urgency, FOMO.
- Never invent a Nubra capability, price, metric, date, or comparison. Map
  claims only to the supplied feature_ids; cite only supplied evidence ids.
- No competitor disparagement. Facts about Nubra only.
- No superlatives like "best" or "#1" about Nubra.
- No emojis, no corporate filler, no meta-instructions in public copy.
- `rationale` is the only field allowed to contain internal reasoning.

Return ONLY one JSON object:
{"recommendations":[{
  "recommendation_key":"short-stable-slug",
  "platform":"reddit|x|linkedin|youtube_community",
  "content_type":"seed_reply|standalone",
  "title":"internal editorial title",
  "hook":"exact public opening line",
  "body":"exact public body — continues AFTER the hook; never repeat the hook",
  "cta":"soft exact CTA ('' allowed for reddit seed replies)",
  "hashtags":["#tag"],
  "feature_ids":["feature_id"],
  "evidence_item_ids":[123],
  "seed_url":"the thread url (required for seed_reply, null otherwise)",
  "rationale":"why this, grounded in evidence",
  "recommended_timing":"plain-language timing",
  "priority_score":0
}]}"""


def _evidence(days: int = 21, limit: int = 40) -> list[dict]:
    """Fresh lens items: seedable threads (friction/guidance with a url,
    reddit/forums where a reply is possible) + inspiration (showcase asks)."""
    rows = db.query(
        """
        SELECT a.item_id, si.source, si.url, a.stage, a.kind, a.gist,
               a.friction_theme, a.working_theme, left(si.text, 500) AS text,
               coalesce((si.engagement->>'score')::float, 0) AS engagement,
               (a.kind IN ('friction','guidance_seeking')
                AND si.url IS NOT NULL
                AND si.source IN ('reddit','community_forum')) AS seedable
        FROM api_trader_items a
        JOIN social_items si ON si.item_id = a.item_id
        WHERE a.stage NOT IN ('irrelevant') AND si.duplicate_of IS NULL
          AND si.created_at >= now() - make_interval(days => %s)
          AND si.text !~* '\\ynubra\\y'
        ORDER BY seedable DESC, (si.engagement->>'score')::float DESC NULLS LAST
        LIMIT %s
        """,
        (days, limit))
    return [dict(r) for r in rows]


def _features() -> list[dict]:
    ctx = product_context.load()
    return [f.model_dump() for f in ctx.features if f.segment in ("api", "shared")]


def _ready_counts() -> dict[str, int]:
    rows = db.query(
        "SELECT platform, count(*)::int AS n FROM social_recommendations "
        "WHERE lens = %s AND status = 'draft' GROUP BY platform", (LENS,))
    counts = {p: 0 for p in PLATFORMS}
    counts.update({r["platform"]: r["n"] for r in rows})
    return counts


def _stable_key(rec: ApiLensRec) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", rec.recommendation_key.lower()).strip("-")[:48]
    digest = hashlib.sha1(
        f"{rec.platform}|{rec.title}|{rec.seed_url}|{'|'.join(rec.feature_ids)}".encode()
    ).hexdigest()[:10]
    return f"{slug or 'api-brief'}-{digest}"


def top_up(min_ready_per_platform: int = 2, max_new: int = 8,
           days: int = 21) -> dict[str, Any]:
    """Refill the queue to min_ready_per_platform drafts per platform.
    Isolated: returns a status dict, never raises into the pipeline."""
    from community.enrich.api_trader import lens_enabled
    stats: dict[str, Any] = {"lens": LENS}
    try:
        if not lens_enabled():
            return {**stats, "status": "disabled"}
        counts = _ready_counts()
        need = {p: max(0, min_ready_per_platform - n) for p, n in counts.items()}
        total_need = min(sum(need.values()), max_new)
        stats.update({"ready": counts, "need": total_need})
        if total_need == 0:
            return {**stats, "status": "stocked"}
        if not settings.anthropic_api_key:
            return {**stats, "status": "skipped", "detail": "no ANTHROPIC_API_KEY"}

        evidence = _evidence(days=days)
        if not evidence:
            return {**stats, "status": "skipped", "detail": "no fresh lens evidence"}
        features = _features()
        payload = {
            "needed_per_platform": {p: n for p, n in need.items() if n > 0},
            "max_items": total_need,
            "features": features,
            "evidence": evidence,
        }
        run_id = db.one(
            "INSERT INTO social_recommendation_runs (status, model, prompt_version, "
            "context_version, window_days) VALUES ('running', %s, %s, %s, %s) RETURNING id",
            (settings.draft_model, PROMPT_VERSION,
             product_context.load().version, days))["id"]
        raw, usage = complete(
            settings.draft_model, _SYSTEM,
            "Create at most max_items pieces, covering the platforms in "
            "needed_per_platform. Prefer seed_reply for items marked seedable. "
            "Evidence pack:\n" + json.dumps(payload, ensure_ascii=False, default=str),
            max_tokens=6000)
        envelope = ApiLensEnvelope.model_validate(_json_object(raw))

        ev_by_id = {e["item_id"]: e for e in evidence}
        feat_by_id = {f["id"]: f for f in features}
        stored, rejected = 0, 0
        today = datetime.now(timezone.utc).date()
        for rec in envelope.recommendations[:total_need]:
            if any(i not in ev_by_id for i in rec.evidence_item_ids):
                rejected += 1
                continue
            if any(f not in feat_by_id for f in rec.feature_ids):
                rejected += 1
                continue
            if rec.content_type == "seed_reply":
                # the seed target must be a real evidence thread, not invented
                urls = {ev_by_id[i]["url"] for i in rec.evidence_item_ids}
                if rec.seed_url not in urls:
                    rejected += 1
                    continue
            else:
                rec.seed_url = None
            if _public_copy_issue(rec.exact_copy):
                rejected += 1
                continue
            ok, reasons = compliance_check(
                rec.exact_copy, "social_recommendation",
                {"kind": "api_lens_brief", "key": rec.recommendation_key})
            if not ok:
                rejected += 1
                log.warning("api-lens brief failed compliance: %s — %s", rec.title, reasons)
                continue
            rec.recommendation_key = _stable_key(rec)
            db.execute(
                """
                INSERT INTO social_recommendations (
                    run_id, day, recommendation_key, segment, platform, post_format,
                    title, hook, body, cta, exact_copy, hashtags, mapped_features,
                    source_evidence, rationale, visual_brief, recommended_timing,
                    priority_score, compliance_status, model, prompt_version,
                    context_version, lens, seed_url
                )
                VALUES (%s, %s, %s, 'api', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, 'passed', %s, %s, %s, %s, %s)
                """,
                (run_id, today, rec.recommendation_key, rec.platform,
                 "seed_reply" if rec.content_type == "seed_reply" else "text_post",
                 rec.title, rec.hook, rec.body, rec.cta, rec.exact_copy,
                 rec.hashtags,
                 db.jsonb([feat_by_id[f] for f in rec.feature_ids]),
                 db.jsonb([ev_by_id[i] for i in rec.evidence_item_ids]),
                 rec.rationale, "text-only brief; no visual", rec.recommended_timing,
                 rec.priority_score, settings.draft_model, PROMPT_VERSION,
                 product_context.load().version, LENS, rec.seed_url))
            stored += 1
        stats.update({"generated": len(envelope.recommendations),
                      "stored": stored, "rejected": rejected, "usage": usage})
        db.execute("UPDATE social_recommendation_runs SET status='succeeded', "
                   "stats=%s, completed_at=now() WHERE id=%s",
                   (db.jsonb({k: v for k, v in stats.items() if k != 'usage'}), run_id))
        repo.advance_state("social_recommend", "api_lens",
                           watermark=datetime.now(timezone.utc), items=stored)
        log.info("api-lens top-up: %s", stats)
        return {**stats, "status": "succeeded"}
    except Exception as exc:  # noqa: BLE001 — never break the pipeline
        log.exception("api-lens top-up failed")
        try:
            repo.advance_state("social_recommend", "api_lens",
                               items=0, error=str(exc)[:500])
        except Exception:
            pass
        return {**stats, "status": "failed", "error": str(exc)[:300]}
