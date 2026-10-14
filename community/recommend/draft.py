"""⑤b draft pass — grounded brand+rep drafts, timing, content proposals (LLD-03 §2/§4/§5).

Local mode: sync Sonnet calls (prod: the 06:45 IST Batch API job). Every draft and
proposal passes the compliance gate; failures regenerate ≤2 then drop the drafts
(the opportunity itself is kept).
"""
from __future__ import annotations

import json
import pathlib
import re
from datetime import datetime, timezone, timedelta

from community.config.settings import settings
from community.llm.client import complete
from community.recommend import compliance
from community.reference import features
from community.store import db
from community.config.log import get_logger

log = get_logger("draft")

IST = timezone(timedelta(hours=5, minutes=30))

DISCLOSURE = "Full disclosure — I'm part not of the team at Nubra."

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

# ── per-source prompts ───────────────────────────────────────────────────
# `_DRAFT_SYSTEM` above is the DEFAULT, used by every source that has no prompt of its own (X today).
# A source listed in `_SOURCE_PROMPTS` is drafted from its own plain-text file instead, so editing that file
# changes that source and nothing else. To change how REDDIT replies read, edit
# community/llm/prompts/reply_reddit.txt (no Python quoting; `{DISCLOSURE}` is the only placeholder and is
# replaced by the DISCLOSURE sentence). The JSON shape at the end of the prompt is what the parser reads: keep it.
# The validator below and the compliance judge apply to every source: a style they reject is regenerated twice
# and then dropped.
_PROMPTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "llm" / "prompts"
_SOURCE_PROMPTS = {"reddit": "reply_reddit"}


def _load_prompt(name: str) -> str:
    text = (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
    return text.replace("{DISCLOSURE}", DISCLOSURE)


def _system_for(source: str) -> str:
    """The drafting prompt for one source; a missing/unreadable file falls back to the default (and says so)
    rather than stopping the whole draft stage."""
    name = _SOURCE_PROMPTS.get(source)
    if not name:
        return _DRAFT_SYSTEM
    try:
        return _load_prompt(name)
    except OSError:
        log.warning("prompt file %s.txt for source %r is unreadable - using the default prompt", name, source)
        return _DRAFT_SYSTEM


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


# ── rules for sources that have their own prompt (Reddit) ─────────────────
# Those replies are written in a plain human voice and disclose the Nubra connection only when Nubra is actually
# mentioned (or a Nubra feature is cited), in a short natural line ("I work at Nubra"). Every other source keeps the
# exact-sentence rule in `_validate_drafts`. `REPLY_MAX_WORDS` leaves headroom over the team's own example replies
# (86-159 words).
REPLY_MAX_WORDS = {"rep": 200, "brand": 100}

_NUBRA = re.compile(r"(?<![a-z])nubra(?![a-z])", re.I)
_DISCLOSURE_FORMS = re.compile(
    r"\bI\s+work\s+(?:at|for|with)\s+Nubra\b"
    r"|\bI(?:['\u2019]m|\s+am)\s+(?:on|with|part\s+of)\s+(?:the\s+)?(?:team\s+at\s+)?Nubra(?:\s+team)?\b"
    r"|\bmain\s+Nubra\s+(?:mein|me|se)\b"
    r"|\bNubra\s+(?:team\s+)?se\s+(?:hoon|hu|hun)\b", re.I)
# a "disclosure" that says the opposite (or is garbled into saying it) is not a disclosure
_DENIAL = re.compile(
    r"\bpart\s+not\b"
    r"|\bnot\s+(?:really\s+)?(?:a\s+)?(?:part\s+of|on|with|from|affiliated\s+with|connected\s+(?:to|with)"
    r"|working\s+(?:at|for|with))\s+(?:the\s+)?(?:team\s+at\s+)?Nubra\b"
    r"|\b(?:don['\u2019]t|do\s+not|doesn['\u2019]t)\s+work\s+(?:at|for|with)\s+Nubra\b"
    r"|\bunaffiliated\s+with\s+Nubra\b|\bno\s+(?:connection|affiliation)\s+(?:to|with)\s+Nubra\b", re.I)
_BOLD = re.compile(r"\*\*[^*\n]+\*\*")
_URL = re.compile(r"https?://|\bwww\.", re.I)
_HASHTAG = re.compile(r"(?<![\w&])#[A-Za-z]\w+")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF]")
_PROMO = re.compile(
    r"\b(?:game[- ]?changer|seamless(?:ly)?|best[- ]in[- ]class|cutting[- ]edge|world[- ]class"
    r"|check\s+(?:it|us|them)?\s*out|sign\s*up|download\s+our|join\s+us|we(?:'re|\s+are)\s+excited"
    r"|limited[- ]time|don'?t\s+miss|supercharge|revolutioni[sz]e|one[- ]stop)\b", re.I)


def _disclosure_problems(rep: str, cited: list) -> list[str]:
    out = []
    has = bool(_DISCLOSURE_FORMS.search(rep))
    mentions = bool(_NUBRA.search(_DISCLOSURE_FORMS.sub(" ", rep)))     # Nubra named beyond the disclosure itself
    if _NUBRA.search(rep) and _DENIAL.search(rep):
        out.append("rep: the affiliation line contradicts itself")
    if (mentions or cited) and not has:
        out.append("rep: mentions Nubra without a disclosure of the affiliation")
    return out


def _style_problems(text: str, voice: str) -> list[str]:
    out = []
    if _BOLD.search(text):
        out.append(f"{voice}: uses **bold** markdown")
    if _URL.search(text):
        out.append(f"{voice}: contains a link")
    if _EMOJI.search(text):
        out.append(f"{voice}: contains emoji")
    if _HASHTAG.search(text):
        out.append(f"{voice}: contains a hashtag")
    hit = _PROMO.search(text)
    if hit:
        out.append(f"{voice}: marketing phrasing ({hit.group(0)!r})")
    words = len(text.split())
    if words > REPLY_MAX_WORDS[voice]:
        out.append(f"{voice}: too long ({words} words, max {REPLY_MAX_WORDS[voice]})")
    return out


def _own_prompt_problems(data: dict) -> list[str]:
    rep = (data.get("rep") or {}).get("text", "")
    brand = (data.get("brand") or {}).get("text", "")
    cited = (data.get("rep") or {}).get("features_cited") or []
    out: list[str] = []
    if rep:
        out += _disclosure_problems(rep, cited) + _style_problems(rep, "rep")
    if brand:
        out += _style_problems(brand, "brand")      # the official voice needs no disclosure line
    return out


def _validate_drafts(data: dict, valid_ids: set[str], source: str = "") -> list[str]:
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
    if source in _SOURCE_PROMPTS:
        problems += _own_prompt_problems(data)
    elif rep and DISCLOSURE not in rep:
        problems.append("rep: disclosure line missing")
    return problems


def _user_message(opp: dict, catalog: list[dict]) -> str:
    """What the model is given besides the system prompt (shared by the real stage and the preview tool)."""
    excerpt = _thread_excerpt(opp["source"], opp["thread_id"])
    return (f"NUBRA_FEATURES (is_current=true):\n{json.dumps(catalog, indent=1)}\n\n"
            f"CONVERSATION (root + top replies):\n{excerpt}\n\n"
            f"MATCHED_INSIGHT: {json.dumps(opp.get('matched_insight') or {})}\n"
            "TASK: produce a BRAND reply and a REP reply per the JSON schema.")


def _draft_one(opp: dict, catalog: list[dict]) -> tuple[dict | None, dict]:
    """Returns (drafts | None, gate_stats)."""
    valid_ids = {c["id"] for c in catalog}
    user = _user_message(opp, catalog)
    gate = {"passed": 0, "regenerated": 0, "dropped": 0}
    feedback = ""
    system = _system_for(opp["source"])
    for attempt in range(3):  # initial + 2 regenerations (D4)
        raw, _u = complete(settings.draft_model, system, user + feedback, max_tokens=1200)
        try:
            data = _parse_json(raw)
        except (ValueError, json.JSONDecodeError):
            feedback = "\n\nYour last output was not valid JSON. Return only the JSON."
            gate["regenerated"] += 1
            continue
        if data.get("skip_reason"):
            return None, gate
        problems = _validate_drafts(data, valid_ids, opp["source"])
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


def _repeat_flags(cands: list[dict], recent: list[dict]) -> list[bool]:
    """LLM repeat-judge (one cheap Haiku call for all candidates). Embeddings
    were tried first and CANNOT separate repeats here — real July 13/14/15
    briefs all sit ~0.87 cosine whether same-idea or different-topic (long
    F&O brief texts cluster in a narrow cone). Rules encoded: a topic already
    covered twice in the window is exhausted; covered once = allowed only
    with a different format_family AND a materially different idea. Errors
    fail open (a judge hiccup must not block the day's briefs)."""
    try:
        recent_s = [{"day": str(r["day"]), "treatment": r["treatment"],
                     "format_family": r["format_family"]} for r in recent]
        cand_s = [{"i": i, "treatment": c.get("treatment", ""),
                   "format_family": c.get("format_family", ""),
                   "hook": c.get("hook", "")} for i, c in enumerate(cands)]
        raw, _u = complete(
            settings.enrich_model,
            "You judge content-brief repetition for a brand's content calendar. "
            "RECENT lists briefs already published. For each CANDIDATE decide "
            "repeat=true when ANY holds: (a) its core topic already appears "
            "twice or more in RECENT; (b) its core topic appears once in RECENT "
            "and the candidate has the same format_family; (c) it is essentially "
            "the same content idea as any RECENT brief even if reworded or "
            "reformatted. A genuinely different angle on a once-covered topic "
            "in a different format is NOT a repeat. Return ONLY JSON: "
            '{"repeats": [{"i": 0, "repeat": true, "why": "..."}]} covering every candidate.',
            f"RECENT: {json.dumps(recent_s)}\n\nCANDIDATES: {json.dumps(cand_s)}",
            max_tokens=800)
        verdicts = {v["i"]: bool(v.get("repeat")) for v in _parse_json(raw)["repeats"]}
        return [verdicts.get(i, False) for i in range(len(cands))]
    except Exception:  # noqa: BLE001
        log.warning("repeat-judge failed — allowing all candidates", exc_info=True)
        return [False] * len(cands)


# Daily content briefs. The model is asked for more candidates than are kept, because the taxonomy check, the
# per-family cap, the repeat-judge and the compliance gate each drop some (the table's rank rule: migration 0024).
MAX_PROPOSALS = 5
CANDIDATES_ASKED = 8
CONTENT_MAX_TOKENS = 13000      # ~1,600 tokens per candidate brief


def _content_system(fams: list[str], plats: list[str]) -> str:
    return (
        "You are a senior creative strategist writing CONTENT BRIEFS for Nubra's content "
        "creators and community managers (Nubra = SEBI-regulated Indian stock broker). "
        "NOT buy/sell content — relevant, useful presence around what traders discuss "
        "today. Ground any Nubra claim ONLY in NUBRA_FEATURES. "
        "HARD CONSTRAINTS (a compliance gate rejects violations): never anchor content "
        "on a named competitor or their bad news; no directional/predictive market "
        "claims; no trade setups, levels, targets or stop-losses — not even as chart "
        "examples; no urgency/FOMO/social-proof pressure. NO EMOJIS anywhere. "
        "Safe angles: educational explainers, process/tooling walkthroughs, myth-busting "
        "with public facts, feature demos, community questions. "
        "ANTI-REPETITION: RECENT_BRIEFS lists what we already published. A topic "
        "covered there may be revisited AT MOST once more within a week and ONLY "
        "with a genuinely different angle AND a different format_family — never "
        "another variation of the same idea. When today's top signal is already "
        "well covered, prefer the next-best uncovered signal instead. "
        "Invent the creative TREATMENT freely — do not limit yourself to generic "
        "formats; propose the specific creative vehicle (e.g. 'split-screen myth-vs-"
        "reality reel with on-screen calculator', 'founder-voice teardown thread'). "
        f"Pick format_family from {fams} and platform from {plats} — say WHY that "
        "platform fits this audience/signal. Each brief must be executable without "
        "follow-up questions: concrete beats a creator can shoot/write directly "
        "(video: shot-by-shot with on-screen text; threads: tweet-by-tweet with the "
        "first two written; image/carousel: exact data points and layout). Reference "
        "the actual signal from TODAY'S SIGNAL. Return ONLY JSON: "
        '{"candidates": [{"format_family": "...", "platform": "...", '
        '"treatment": "one-line creative vehicle", "platform_why": "...", '
        '"hook": "exact opening line/cover text", "brief": {"beats": ["..."], '
        '"caption": "ready-to-paste", "hashtags": ["#tag"], "cta": "one CTA", '
        '"visual_direction": "..."}, "why": "tied to the signal", '
        '"recommended_window": "HH:MM-HH:MM IST", "scores": {"impact":0.0,'
        '"reach_fit":0.0,"timeliness":0.0,"effort_inv":0.0,"on_brand":0.0}}]} '
        f"(exactly {CANDIDATES_ASKED} candidates)")


def _content_proposals(catalog: list[dict]) -> int:
    today = datetime.now(timezone.utc).date()
    # Once per day: briefs regenerate with the morning build only. The hourly
    # draft stage must NOT delete+regenerate — that would destroy human edits
    # (Ask-Beacon revisions, outline.revisions history) and burn Sonnet 18x/day.
    # Manual re-generation = delete today's rows first, then rerun the stage.
    existing = db.one(
        "SELECT count(*) AS n FROM content_proposals WHERE day=%s", (today,))["n"]
    if existing:
        return existing
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
    # Repetition guard (user feedback 2026-07-17: 13th+14th July both produced
    # tax-myth carousels off the same trending topic). Recent briefs are shown
    # to the model with explicit anti-repeat rules, and candidates too similar
    # to any recent brief are dropped deterministically below (embeddings).
    rep_days = int(settings.registry["content"].get("repetition_lookback_days", 7))
    recent = db.query(
        "SELECT day, format AS treatment, hook, format_family FROM content_proposals "
        "WHERE day > %s::date - %s AND day < %s ORDER BY day DESC",
        (today, rep_days, today))
    fams = settings.registry["content"]["format_families"]
    plats = settings.registry["content"]["platforms"]
    system = _content_system(fams, plats)
    recent_summary = [{"day": str(r["day"]), "treatment": r["treatment"],
                       "format_family": r["format_family"]} for r in recent]
    user = (f"NUBRA_FEATURES: {json.dumps(catalog)}\n\nTODAY'S SIGNAL:\n"
            f"rising topics: {json.dumps(topics, default=str)}\n"
            f"broker issues: {json.dumps(issues, default=str)}\n"
            f"feature requests: {json.dumps(feats, default=str)}\n\n"
            f"RECENT_BRIEFS (already published — do not repeat): "
            f"{json.dumps(recent_summary)}")
    raw, _u = complete(settings.draft_model, system, user, max_tokens=CONTENT_MAX_TOKENS)
    try:
        cands = _parse_json(raw)["candidates"]
    except (ValueError, KeyError, json.JSONDecodeError) as e:
        log.error("content proposals: LLM output unparsable (%s) — 0 proposals this run", e)
        return 0

    def score(c):
        s = c.get("scores", {})
        return (0.30 * s.get("impact", 0) + 0.25 * s.get("reach_fit", 0)
                + 0.20 * s.get("timeliness", 0) + 0.15 * s.get("effort_inv", 0)
                + 0.10 * s.get("on_brand", 0))

    cands.sort(key=score, reverse=True)
    repeats = _repeat_flags(cands, recent) if recent else [False] * len(cands)
    chosen, per_family = [], {}
    for idx, c in enumerate(cands):
        fam, plat = c.get("format_family"), c.get("platform")
        if fam not in fams or plat not in plats:   # taxonomy = the control layer
            continue
        if per_family.get(fam, 0) >= 2:
            continue
        if repeats[idx]:
            log.info("proposal dropped as repeat of a recent brief: %s",
                     (c.get("treatment") or "")[:80])
            continue
        brief = c.get("brief") or {}
        text = " | ".join([c.get("hook", ""), " / ".join(brief.get("beats", [])),
                           brief.get("caption", "")])
        ok, _ = compliance.check(text, "content_proposal", {"kind": "content_proposal", "hook": c.get("hook", "")[:60]})
        if not ok:
            continue
        chosen.append(c)
        per_family[fam] = per_family.get(fam, 0) + 1
        if len(chosen) == MAX_PROPOSALS:
            break

    db.execute("DELETE FROM content_proposals WHERE day=%s", (today,))
    for rank, c in enumerate(chosen, 1):
        db.execute(
            "INSERT INTO content_proposals (day, rank, format, format_family, platform, "
            "hook, outline, why, rides_signal, recommended_timing) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (today, rank, (c.get("treatment") or c["format_family"]),
             c["format_family"], c.get("platform"),
             c.get("hook", ""), db.jsonb({**c.get("brief", {}),
                                          "platform_why": c.get("platform_why")}),
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
