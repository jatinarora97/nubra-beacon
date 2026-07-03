"""Rising Voices — find the *people* worth engaging, not just the topics.

A community manager's other job is talent-spotting: who are the regulars producing
relevant, well-received content who could become the next finfluencers / brand
advocates? This stage scans every fetched item, aggregates per author, and scores
them on a transparent, multi-factor **Rising-Voice Score** — deliberately a different
methodology from topic-trending:

    score = 100 · relevance · quality · audience_weight · (0.45·reach + 0.40·consistency + 0.15·breadth)

  • reach        — log-scaled total engagement (rewards being heard, dampens one viral post)
  • consistency  — log-scaled contribution count (we want *regulars*, not one-hit posters)
  • breadth      — how many distinct communities they show up in (a connector signal)
  • relevance    — share of their content that's on-topic (our keyword gate)
  • quality      — 1 − noise/tip-spam ratio (filters out the "sure shot target SL" crowd)
  • audience_wt  — favours dev/algo/serious voices over generic retail

Bots, deleted, and anonymous authors are excluded. Anyone below a minimum contribution
count is dropped — a rising voice is by definition someone who shows up repeatedly.
"""
from __future__ import annotations

import json
import math
import os
from collections import defaultdict

from .classify import _kw_classify

# Never candidates: automod/megathread bots + non-identities.
_EXCLUDE = {"automoderator", "sebi-bot", "sneakpeekbot", "repostsleuthbot",
            "remindmebot", "[deleted]", "[removed]", "anon", "", None}

# Audience weights — same spirit as trend ranking (favour our core builders).
_AUD_W = {"dev": 1.5, "algo": 1.4, "serious": 1.1, "retail": 0.7}

_DEFAULT_KW = ["nifty", "banknifty", "option", "f&o", "futures", "algo", "api",
               "expiry", "straddle", "strangle", "broker", "trade", "stock",
               "portfolio", "backtest", "python", "kite", "dhan"]


def _norm(value: float, scale: float) -> float:
    """log-scaled 0..~1 normalizer."""
    return math.log10(1 + max(0.0, value)) / math.log10(1 + scale)


def find_rising_voices(items: list, cfg: dict | None = None,
                       min_contributions: int = 2, top_n: int = 25) -> list[dict]:
    cfg = cfg or {}
    keywords = [k.lower() for k in cfg.get("prefilter", {}).get("keywords", _DEFAULT_KW)] or _DEFAULT_KW

    agg: dict[str, dict] = defaultdict(lambda: {
        "posts": 0, "comments": 0, "total_eng": 0, "best": 0,
        "subs": set(), "on_topic": 0, "noise": 0, "aud": defaultdict(int),
        "samples": [], "best_item": None,
    })

    for it in items:
        author = (it.author or "").strip()
        if author.lower() in _EXCLUDE:
            continue
        a = agg[author]
        if it.source_type == "post":
            a["posts"] += 1
        else:
            a["comments"] += 1
        score = it.engagement.get("score", 0) or 0
        a["total_eng"] += score
        if score >= a["best"]:
            a["best"] = score
            a["best_item"] = {"text": it.text[:240], "url": it.url, "score": score,
                              "subreddit": (it.raw or {}).get("subreddit")}
        sub = (it.raw or {}).get("subreddit")
        if sub:
            a["subs"].add(sub)
        text = (it.text or "")
        if any(k in text.lower() for k in keywords):
            a["on_topic"] += 1
        lab = _kw_classify(text)
        if lab.get("is_noise"):
            a["noise"] += 1
        a["aud"][lab["audience"]] += 1
        if len(a["samples"]) < 3:
            a["samples"].append({"type": it.source_type, "text": text[:200],
                                 "url": it.url, "score": score,
                                 "subreddit": sub})

    voices = []
    for author, a in agg.items():
        contributions = a["posts"] + a["comments"]
        if contributions < min_contributions:
            continue
        communities = len(a["subs"]) or 1
        relevance = a["on_topic"] / contributions
        quality = 1.0 - (a["noise"] / contributions)
        dominant_aud = max(a["aud"], key=a["aud"].get) if a["aud"] else "retail"
        aud_w = _AUD_W.get(dominant_aud, 0.7)

        reach = _norm(a["total_eng"], scale=2000)          # 2000 total score ≈ 1.0
        consistency = _norm(contributions, scale=20)        # 20 contributions ≈ 1.0
        breadth = _norm(communities, scale=5)               # 5 communities ≈ 1.0

        base = 0.45 * reach + 0.40 * consistency + 0.15 * breadth
        score = 100 * relevance * max(0.15, quality) * aud_w * base

        voices.append({
            "author": author,
            "score": round(score, 1),
            "contributions": contributions,
            "posts": a["posts"], "comments": a["comments"],
            "communities": communities,
            "subreddits": sorted(a["subs"]),
            "total_engagement": a["total_eng"],
            "avg_engagement": round(a["total_eng"] / contributions, 1),
            "best": a["best"],
            "relevance": round(relevance, 2),
            "quality": round(quality, 2),
            "audience": dominant_aud,
            "components": {"reach": round(reach, 2), "consistency": round(consistency, 2),
                           "breadth": round(breadth, 2)},
            "best_item": a["best_item"],
            "samples": a["samples"],
        })

    voices.sort(key=lambda v: v["score"], reverse=True)
    return voices[:top_n]


# --------------------------- optional LLM enrichment ---------------------------

_INSTR = (
    "You scout 'rising voices' — Indian stock-market Reddit users who could become "
    "valuable finfluencers or brand advocates for a discount broker. For each candidate "
    "below (with their stats), return ONLY a JSON array, one object per candidate, keys:\n"
    "- i: integer index copied from the list\n"
    "- archetype: 2-4 word label (e.g. 'algo-builder educator', 'options mentor', 'macro explainer')\n"
    "- why: one sentence on why they're worth engaging, grounded in their stats\n"
    "- outreach: one concrete first-touch idea (a reply, a collab, an invite) — specific, not salesy\n"
    "Judge on relevance + consistency + how constructive they seem. Be concrete.\n\nCandidates:\n"
)


def enrich_with_llm(voices: list[dict], max_candidates: int = 12) -> tuple[list[dict], dict]:
    meta = {"method": "heuristic", "model": None}
    if not voices or not os.environ.get("ANTHROPIC_API_KEY"):
        return voices, meta
    subset = voices[:max_candidates]
    try:
        import anthropic  # lazy
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        lines = []
        for i, v in enumerate(subset):
            sample = (v.get("best_item") or {}).get("text", "")[:140]
            lines.append(
                f"{i}. u/{v['author']} | {v['contributions']} contributions "
                f"({v['posts']}p/{v['comments']}c) | {v['communities']} communities "
                f"({', '.join(v['subreddits'][:4])}) | avg_score={v['avg_engagement']} | "
                f"relevance={v['relevance']} | audience={v['audience']} | "
                f"top post: \"{sample}\""
            )
        prompt = _INSTR + "\n".join(lines)
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        body = raw[raw.find("["): raw.rfind("]") + 1]
        parsed = json.loads(body)
        by_i = {o.get("i"): o for o in parsed if isinstance(o, dict)}
        for i, v in enumerate(subset):
            o = by_i.get(i)
            if o:
                v["archetype"] = o.get("archetype")
                v["why"] = o.get("why")
                v["outreach"] = o.get("outreach")
        meta = {"method": "llm", "model": "claude-haiku-4-5-20251001",
                "prompt": prompt, "raw_response": raw,
                "usage": {"input_tokens": resp.usage.input_tokens,
                          "output_tokens": resp.usage.output_tokens}}
    except Exception as e:  # noqa: BLE001
        meta = {"method": "heuristic", "model": None, "error": str(e)}
    return voices, meta
