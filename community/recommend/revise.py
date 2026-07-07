"""Targeted content-brief revision (work plan N9).

The LLM generated a brief; the team wants surgical changes — tighten a hook,
re-platform it, swap a CTA — WITHOUT regenerating the whole thing. Manual field
edits apply directly; an instruction (or a platform change, which implies
re-tailoring) goes through a lightweight LLM call that is told to change only
what the instruction requires. Haiku first, one Sonnet retry on invalid output.
Every revised text re-passes the L1 compliance rules (same regex layer as the
draft pipeline); revision history lives in outline.revisions (last 2 shown to
the model, 10 kept).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from community.config.settings import settings
from community.llm import trace
from community.llm.client import complete
from community.recommend.compliance import l1_check
from community.store import db

# Fields the reviser may change. why/rides_signal are signal facts — locked.
_LLM_FIELDS = ("treatment", "format_family", "platform", "platform_why", "hook",
               "beats", "caption", "hashtags", "cta", "visual_direction")
_MANUAL_FIELDS = _LLM_FIELDS  # same surface; validation identical
_HISTORY_SHOWN = 2
_HISTORY_KEPT = 10

_SYSTEM = """You revise social-media content briefs for Nubra, a SEBI-regulated Indian stock broker.
You receive the CURRENT brief as JSON and an instruction. Apply the instruction with the
smallest possible change set — every field the instruction does not require you to touch
must be returned EXACTLY as given, byte for byte.

HARD RULES:
- Return ONLY a JSON object with exactly these keys: treatment, format_family, platform,
  platform_why, hook, beats (array of strings), caption, hashtags (array of strings,
  each starting with #), cta, visual_direction.
- format_family must be one of: {families}
- platform must be one of: {platforms}
- Product claims must stay within the grounding list below — never invent features,
  pricing, or performance numbers.
- No buy/sell/hold calls, no guaranteed-return language, no fear-mongering, no crypto.
- If the platform changes, adapt lengths/format norms/caption+hashtag conventions to the
  new platform while preserving the core idea.

GROUNDING (the only product facts you may use):
{grounding}"""


def _taxonomy() -> tuple[list[str], list[str]]:
    c = settings.registry.get("content", {})
    return list(c.get("format_families", [])), list(c.get("platforms", []))


def _grounding_lines() -> str:
    rows = db.query("SELECT feature, description, status FROM nubra_features "
                    "WHERE is_current ORDER BY feature")
    return "\n".join(f"- {r['feature']} ({r['status']}): {r['description']}" for r in rows)


def _load(day: date, rank: int) -> dict:
    row = db.one("SELECT id, day, rank, format, hook, outline, why, rides_signal, "
                 "recommended_timing, format_family, platform "
                 "FROM content_proposals WHERE day=%s AND rank=%s", (day, rank))
    if not row:
        raise LookupError(f"no proposal day={day} rank={rank}")
    return row


def _brief_dict(row: dict) -> dict:
    outline = row["outline"] or {}
    if isinstance(outline, list):  # pre-taxonomy rows stored beats as a bare list
        outline = {"beats": outline}
    return {
        "treatment": row["format"],
        "format_family": row["format_family"],
        "platform": row["platform"],
        "platform_why": outline.get("platform_why"),
        "hook": row["hook"],
        "beats": outline.get("beats", []),
        "caption": outline.get("caption"),
        "hashtags": outline.get("hashtags", []),
        "cta": outline.get("cta"),
        "visual_direction": outline.get("visual_direction"),
    }


def _validate(brief: dict) -> list[str]:
    fams, plats = _taxonomy()
    problems = []
    for k in _LLM_FIELDS:
        if k not in brief:
            problems.append(f"missing field {k}")
    if brief.get("format_family") not in fams:
        problems.append(f"format_family {brief.get('format_family')!r} not in taxonomy")
    if brief.get("platform") not in plats:
        problems.append(f"platform {brief.get('platform')!r} not in taxonomy")
    if not isinstance(brief.get("beats"), list) or not isinstance(brief.get("hashtags"), list):
        problems.append("beats/hashtags must be arrays")
    if not (brief.get("hook") or "").strip():
        problems.append("hook is empty")
    text = " ".join([brief.get("hook") or "", brief.get("caption") or "",
                     brief.get("cta") or ""] + [str(b) for b in brief.get("beats", [])])
    problems += [f"compliance {h}" for h in l1_check(text)]
    return problems


def _llm_revise(current: dict, instruction: str, history: list[dict]) -> dict:
    fams, plats = _taxonomy()
    system = _SYSTEM.format(families=", ".join(fams), platforms=", ".join(plats),
                            grounding=_grounding_lines())
    hist_txt = "\n".join(
        f"- {h.get('ts', '?')[:16]}: {h.get('instruction')!r}" for h in history[-_HISTORY_SHOWN:]
        if h.get("instruction"))
    user = (f"CURRENT BRIEF:\n{json.dumps(current, ensure_ascii=False, indent=1)}\n\n"
            + (f"RECENT REVISIONS (context, already applied):\n{hist_txt}\n\n" if hist_txt else "")
            + f"INSTRUCTION:\n{instruction}\n\nReturn the full revised brief JSON.")
    last_problems: list[str] = []
    with trace.stage_context("api"):
        for model in (settings.enrich_model, settings.draft_model):
            raw, _u = complete(model, system, user, max_tokens=4000)
            try:
                revised = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            except (ValueError, json.JSONDecodeError):
                last_problems = [f"unparseable output from {model}"]
                continue
            problems = _validate(revised)
            if not problems:
                return {k: revised[k] for k in _LLM_FIELDS}
            last_problems = problems
    raise ValueError("revision rejected: " + "; ".join(last_problems[:6]))


def revise_brief(day: date, rank: int, instruction: str | None = None,
                 platform: str | None = None, manual: dict | None = None,
                 by: str = "local-dev") -> dict:
    """Apply manual edits and/or an LLM instruction to one brief; persist and
    return the updated row (raw columns — the API flattens it)."""
    row = _load(day, rank)
    outline = row["outline"] if isinstance(row["outline"], dict) else {"beats": row["outline"] or []}
    history = outline.get("revisions", [])
    current = _brief_dict(row)
    before = dict(current)

    if manual:
        bad = set(manual) - set(_MANUAL_FIELDS)
        if bad:
            raise ValueError(f"not editable: {sorted(bad)}")
        current.update({k: v for k, v in manual.items()})

    effective_instruction = instruction
    if platform and platform != current.get("platform"):
        adapt = (f"Change the platform to {platform} and adapt lengths, format norms and "
                 f"caption/hashtag conventions accordingly, preserving the core idea.")
        effective_instruction = f"{instruction}\n{adapt}" if instruction else adapt

    if effective_instruction:
        current = _llm_revise(current, effective_instruction, history)
    else:
        problems = _validate(current)
        if problems:
            raise ValueError("manual edit rejected: " + "; ".join(problems[:6]))

    changed = {k: before[k] for k in _LLM_FIELDS if before.get(k) != current.get(k)}
    if not changed:
        return _load(day, rank)  # nothing to persist

    history.append({"ts": datetime.now(timezone.utc).isoformat(),
                    "instruction": effective_instruction, "by": by,
                    "previous": changed})
    new_outline = {**outline,
                   "beats": current["beats"], "caption": current["caption"],
                   "hashtags": current["hashtags"], "cta": current["cta"],
                   "visual_direction": current["visual_direction"],
                   "platform_why": current["platform_why"],
                   "revisions": history[-_HISTORY_KEPT:]}
    db.execute(
        "UPDATE content_proposals SET format=%s, hook=%s, format_family=%s, "
        "platform=%s, outline=%s WHERE day=%s AND rank=%s",
        (current["treatment"], current["hook"], current["format_family"],
         current["platform"], db.jsonb(new_outline), day, rank))
    return _load(day, rank)
