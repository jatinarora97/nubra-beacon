"""⑤b draft pass — grounded brand+rep drafts, timing, content proposals (LLD-03 §2/§4/§5).

Local mode: sync Sonnet calls (prod: the 06:45 IST Batch API job). Every draft and
proposal passes the compliance gate; failures regenerate ≤2 then drop the drafts
(the opportunity itself is kept).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

from community.config.settings import settings
from community.llm.client import complete
from community.pipeline import compliance
from community.reference import features
from community.store import db

IST = timezone(timedelta(hours=5, minutes=30))

DISCLOSURE = "Full disclosure — I'm part of the team at Nubra."

_DRAFT_SYSTEM = f"""You draft social replies for Nubra, a SEBI-regulated Indian stock broker.
HARD RULES:
- Assert ONLY facts present in NUBRA_FEATURES below. No other Nubra claims.
- status="upcoming" features: phrase as "coming soon" — never a promise or date.
- No investment advice, no buy/sell/target/SL language, no return figures.
- Never disparage a competitor by name; speak to the problem, not the brand.
- Educational, factual, conversational. India context, INR, IST.
- The text may be Hinglish if the thread is — mirror the thread's register.

Return ONLY JSON:
{{"brand": {{"text": "...", "features_cited": ["f_1"]}},
 "rep": {{"text": "...", "features_cited": ["f_1"], "disclosure_included": true}},
 "skip_reason": null}}

BRAND = official Nubra voice: crisp, factual, USP-led.
REP   = human persona: curious, peer-to-peer, helpful, soft pull; MUST include the
        disclosure line verbatim: "{DISCLOSURE}"
"""

_WINDOWS = {"pre_open": "08:30–09:15 IST", "open": "09:15–10:00 IST",
            "post_close": "15:30–17:00 IST", "evening": "20:00–22:30 IST"}


def _parse_json(raw: str) -> dict:
    blob = raw[raw.index("{"): raw.rindex("}") + 1]
    return json.loads(blob)


def _thread_excerpt(source: str, thread_id: str, limit_chars: int = 1500) -> str:
    rows = db.query(
        "SELECT text FROM social_items WHERE source=%s AND thread_id=%s "
        "AND duplicate_of IS NULL ORDER BY created_at LIMIT 8",
        (source, thread_id),
    )
    out, used = [], 0
    for r in rows:
        t = (r["text"] or "").strip()
        if used + len(t) > limit_chars:
            t = t[: limit_chars - used]
        out.append(f"- {t}")
        used += len(t)
        if used >= limit_chars:
            break
    return "\n".join(out)


def _timing(opp: dict) -> dict:
    conv = db.one(
        "SELECT velocity, last_seen, dominant_topic_key FROM conversations "
        "WHERE source=%s AND thread_id=%s", (opp["source"], opp["thread_id"]),
    ) or {}
    now = datetime.now(timezone.utc)
    age_h = ((now - conv["last_seen"]).total_seconds() / 3600.0) if conv.get("last_seen") else 99
    accel = conv.get("velocity") or 0
    topic = conv.get("dominant_topic_key")
    z = None
    if topic:
        td = db.one("SELECT velocity_z FROM topic_daily WHERE topic_key=%s AND day=%s",
                    (topic, now.date()))
        z = (td or {}).get("velocity_z")
    evergreen = bool(db.one(
        "SELECT 1 AS x FROM topic_taxonomy WHERE topic_key=%s AND evergreen", (topic,)
    )) if topic else False

    if (accel >= 2 or (z or 0) >= 1.5) and age_h < 12:
        return {"action": "now", "window": "live",
                "why": f"thread accel {accel:.1f}x, {age_h:.0f}h old"}
    if evergreen:
        return {"action": "schedule", "window": _WINDOWS["pre_open"], "why": "evergreen topic"}
    if age_h < 24:
        return {"action": "today", "window": _next_window(), "why": "recent thread"}
    return {"action": "schedule", "window": _WINDOWS["pre_open"], "why": "next pre-open reach"}


def _next_window() -> str:
    h = datetime.now(IST).hour + datetime.now(IST).minute / 60
    for start, key in [(8.5, "pre_open"), (9.25, "open"), (15.5, "post_close"), (20.0, "evening")]:
        if h < start:
            return _WINDOWS[key]
    return _WINDOWS["pre_open"]


def _validate_drafts(data: dict, valid_ids: set[str]) -> list[str]:
    problems = []
    for voice in ("brand", "rep"):
        d = data.get(voice) or {}
        if not d.get("text"):
            problems.append(f"{voice}: empty")
            continue
        bad = [c for c in d.get("features_cited", []) if c not in valid_ids]
        if bad:
            problems.append(f"{voice}: unknown features_cited {bad}")
    rep = (data.get("rep") or {}).get("text", "")
    if rep and DISCLOSURE not in rep:
        problems.append("rep: disclosure line missing")
    return problems


def _draft_one(opp: dict, catalog: list[dict]) -> tuple[dict | None, dict]:
    """Returns (drafts | None, gate_stats)."""
    valid_ids = {c["id"] for c in catalog}
    excerpt = _thread_excerpt(opp["source"], opp["thread_id"])
    user = (f"NUBRA_FEATURES (is_current=true):\n{json.dumps(catalog, indent=1)}\n\n"
            f"CONVERSATION (root + top replies):\n{excerpt}\n\n"
            f"MATCHED_INSIGHT: {json.dumps(opp.get('matched_insight') or {})}\n"
            "TASK: produce a BRAND reply and a REP reply per the JSON schema.")
    gate = {"passed": 0, "regenerated": 0, "dropped": 0}
    feedback = ""
    for attempt in range(3):  # initial + 2 regenerations (D4)
        raw, _u = complete(settings.draft_model, _DRAFT_SYSTEM, user + feedback, max_tokens=1200)
        try:
            data = _parse_json(raw)
        except (ValueError, json.JSONDecodeError):
            feedback = "\n\nYour last output was not valid JSON. Return only the JSON."
            gate["regenerated"] += 1
            continue
        if data.get("skip_reason"):
            return None, gate
        problems = _validate_drafts(data, valid_ids)
        if not problems:
            reasons_all = []
            for voice in ("brand", "rep"):
                ok, reasons = compliance.check(
                    data[voice]["text"], f"{voice}_reply",
                    {"kind": "opportunity", "id": opp["id"], "voice": voice})
                if not ok:
                    reasons_all += reasons
            if not reasons_all:
                gate["passed"] += 1
                return data, gate
            problems = reasons_all
        feedback = ("\n\nYour previous draft failed validation/compliance because: "
                    + "; ".join(problems) + ". Fix and return the full JSON again.")
        gate["regenerated"] += 1
    gate["dropped"] += 1
    return None, gate


def _content_proposals(catalog: list[dict]) -> int:
    today = datetime.now(timezone.utc).date()
    # "Day's signal" tolerates quiet mornings/backfill: trailing 14d window,
    # today's rows naturally rank first via velocity/count.
    topics = db.query(
        "SELECT t.topic_key, x.label, SUM(t.count)::int AS count, MAX(t.velocity_z) AS velocity_z "
        "FROM topic_daily t JOIN topic_taxonomy x ON x.topic_key = t.topic_key "
        "WHERE t.day > %s::date - 14 GROUP BY t.topic_key, x.label "
        "ORDER BY velocity_z DESC NULLS LAST, count DESC LIMIT 5", (today,))
    issues = db.query(
        "SELECT broker, issue_key, SUM(count)::int AS count FROM issue_rollup "
        "WHERE day > %s::date - 14 GROUP BY broker, issue_key "
        "ORDER BY count DESC LIMIT 5", (today,))
    feats = db.query(
        "SELECT canonical_label, SUM(count)::int AS count FROM feature_rollup "
        "WHERE day > %s::date - 14 GROUP BY canonical_label "
        "ORDER BY count DESC LIMIT 5", (today,))
    if not topics and not issues and not feats:
        return 0
    system = ("You propose social content for Nubra, an Indian stock broker. NOT buy/sell "
              "content — relevant presence around trending topics. Ground any Nubra claim in "
              "NUBRA_FEATURES. Return ONLY JSON: {\"candidates\": [{\"format\": "
              "\"infographic|reel|short|post|thread\", \"hook\": \"...\", \"outline\": "
              "[\"beat1\",\"beat2\",\"beat3\"], \"why\": \"...\", \"recommended_window\": "
              "\"HH:MM–HH:MM IST\", \"scores\": {\"impact\":0.0,\"reach_fit\":0.0,"
              "\"timeliness\":0.0,\"effort_inv\":0.0,\"on_brand\":0.0}}]}  (~8 candidates)")
    user = (f"NUBRA_FEATURES: {json.dumps(catalog)}\n\nTODAY'S SIGNAL:\n"
            f"rising topics: {json.dumps(topics, default=str)}\n"
            f"broker issues: {json.dumps(issues, default=str)}\n"
            f"feature requests: {json.dumps(feats, default=str)}")
    raw, _u = complete(settings.draft_model, system, user, max_tokens=6000)
    try:
        cands = _parse_json(raw)["candidates"]
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"[recommend] content proposals: LLM output unparsable ({e}) — 0 proposals this run")
        return 0

    def score(c):
        s = c.get("scores", {})
        return (0.30 * s.get("impact", 0) + 0.25 * s.get("reach_fit", 0)
                + 0.20 * s.get("timeliness", 0) + 0.15 * s.get("effort_inv", 0)
                + 0.10 * s.get("on_brand", 0))

    cands.sort(key=score, reverse=True)
    chosen, per_format = [], {}
    for c in cands:
        f = c.get("format")
        if f not in ("infographic", "reel", "short", "post", "thread"):
            continue
        if per_format.get(f, 0) >= 2:
            continue
        text = f"{c.get('hook','')} | {' / '.join(c.get('outline', []))}"
        ok, _ = compliance.check(text, "content_proposal", {"kind": "content_proposal", "hook": c.get("hook", "")[:60]})
        if not ok:
            continue
        chosen.append(c)
        per_format[f] = per_format.get(f, 0) + 1
        if len(chosen) == 3:
            break

    db.execute("DELETE FROM content_proposals WHERE day=%s", (today,))
    for rank, c in enumerate(chosen, 1):
        db.execute(
            "INSERT INTO content_proposals (day, rank, format, hook, outline, why, "
            "rides_signal, recommended_timing) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (today, rank, c["format"], c.get("hook", ""), db.jsonb(c.get("outline", [])),
             c.get("why"), db.jsonb({"signal": "day_mix"}),
             db.jsonb({"action": "schedule", "window": c.get("recommended_window", "")})),
        )
    return len(chosen)


def run(limit: int | None = None) -> dict:
    catalog = features.catalog_for_prompt()
    stats = {"drafted": 0, "dropped": 0, "skipped": 0, "proposals": 0,
             "compliance": {"passed": 0, "regenerated": 0, "dropped": 0},
             "grounding": features.current_version() or "NONE — run scripts/seed_features.py"}
    if not catalog:
        return stats
    n = limit or settings.registry["recommend"]["max_drafted"]
    opps = db.query(
        "SELECT * FROM opportunities WHERE status='suggested' AND priority >= %s "
        "AND brand_reply IS NULL ORDER BY priority DESC LIMIT %s",
        (settings.registry["recommend"]["thresholds"]["secondary"], n),
    )
    for opp in opps:
        drafts, gate = _draft_one(opp, catalog)
        for k in stats["compliance"]:
            stats["compliance"][k] += gate[k]
        if drafts is None:
            stats["dropped" if gate["dropped"] else "skipped"] += 1
            continue
        db.execute(
            "UPDATE opportunities SET brand_reply=%s, rep_reply=%s, recommended_timing=%s, "
            "updated_at=now() WHERE id=%s",
            (drafts["brand"]["text"], drafts["rep"]["text"],
             db.jsonb(_timing(opp)), opp["id"]),
        )
        stats["drafted"] += 1

    stats["proposals"] = _content_proposals(catalog)
    from community.store.repositories import advance_state
    advance_state("recommend", "", items=stats["drafted"])
    return stats
