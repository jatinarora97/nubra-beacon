"""Turn ranked trends into a concrete marketing action plan.

The rest of the pipeline answers *"what is the community talking about?"*. This stage
answers the question a community manager / brand builder actually has: *"so what do we
DO about it, in what format, on which channel, and why — backed by the numbers?"*

For every rising topic we emit an **action plan**: a recommended primary play plus a
menu of format-specific plays (infographic, educational carousel/thread, trendy reel,
open-source/GitHub, community engagement). Each play carries a data-backed rationale,
a ready-to-use hook, and effort/impact tags so the team can triage.

Heuristics run fully offline. When ANTHROPIC_API_KEY is set we make ONE batched Haiku
call to ghost-write punchier hooks/captions over the same plans.
"""
from __future__ import annotations

import json
import os

MODEL = "claude-haiku-4-5-20251001"

# Channel fit by dominant audience — where this audience actually hangs out.
_CHANNELS = {
    "dev": ["GitHub", "X/Twitter", "LinkedIn", "r/algotrading"],
    "algo": ["X/Twitter", "YouTube", "LinkedIn", "Discord/Telegram"],
    "serious": ["YouTube", "X/Twitter", "Instagram", "LinkedIn"],
    "retail": ["Instagram", "YouTube Shorts", "X/Twitter", "WhatsApp"],
}


def _kind(topic: str) -> str:
    """Coarse bucket from the topic label — drives which plays make sense."""
    t = (topic or "").lower()
    if any(k in t for k in ("api", "broker", "kite", "dhan", "openalgo", "websocket", "sdk")):
        return "api"
    if any(k in t for k in ("algo", "backtest", "quant")):
        return "algo"
    if any(k in t for k in ("ai", "llm", "agent")):
        return "ai"
    if any(k in t for k in ("option", "straddle", "strangle", "condor", "theta", "delta", "expiry", "strike")):
        return "options"
    if any(k in t for k in ("tax", "charge", "brokerage", "stt")):
        return "charges"
    if any(k in t for k in ("ipo", "listing")):
        return "ipo"
    if any(k in t for k in ("regulation", "sebi")):
        return "regulation"
    if any(k in t for k in ("portfolio", "invest", "macro", "direction")):
        return "investing"
    return "general"


def _priority(rank: int, total: int) -> str:
    if rank == 0:
        return "🔥 High"
    if rank < max(1, total // 3):
        return "High"
    if rank < max(2, (2 * total) // 3):
        return "Medium"
    return "Low"


def _rationale(r: dict) -> str:
    spread = r.get("spread", 1)
    spread_bit = (f"across {spread} communities" if spread > 1 else "in one community")
    sent = r.get("sentiment", "neutral")
    sent_bit = {
        "negative": "frustration is high — an empathetic, helpful angle will land",
        "positive": "momentum is positive — amplify and ride it",
        "neutral": "curiosity is the driver — lead with a clear explainer",
    }.get(sent, "")
    return (f"{r.get('mentions', 0)} mentions {spread_bit}, dominated by "
            f"**{r.get('audience', 'retail')}** voices; {sent_bit}.")


def _plays(r: dict, kind: str) -> list[dict]:
    topic = r["topic"]
    aud = r.get("audience", "retail")
    sent = r.get("sentiment", "neutral")
    pain = sent == "negative"

    plays: list[dict] = []

    # 1) Infographic — always a fit; one-glance data is shareable everywhere.
    plays.append({
        "format": "Infographic", "icon": "📊",
        "title": f"One-pager: “{topic}” in numbers",
        "hook": (f"Turn the {r.get('mentions',0)} community mentions into a single "
                 f"stat card — what's happening, why it matters, what to do."),
        "why": "Highest reach-per-effort; screenshots travel across X, LinkedIn, WhatsApp.",
        "effort": "Low", "impact": "Medium",
    })

    # 2) Educational carousel / thread — depth for the serious crowd.
    fmt = "Twitter/X thread" if aud in ("dev", "algo") else "Instagram carousel"
    plays.append({
        "format": "Educational", "icon": "📚",
        "title": f"{fmt}: explain “{topic}” properly",
        "hook": (f"5-slide breakdown of {topic} — myth vs reality, with one worked example. "
                 + ("Lead by acknowledging the pain people are posting about." if pain else
                    "Lead with the question everyone's actually asking.")),
        "why": "Builds authority and saves. The audience is already searching for this.",
        "effort": "Medium", "impact": "High",
    })

    # 3) Trendy reel / short — reach the retail top-of-funnel.
    plays.append({
        "format": "Reel / Short", "icon": "🎬",
        "title": f"30s reel: the “{topic}” take",
        "hook": (f"Hook in 3s: “Everyone's talking about {topic} — here's what they're "
                 f"getting wrong.” Fast cuts, one chart, one punchline."),
        "why": "Cheap top-of-funnel reach; algorithm-friendly; humanises the brand.",
        "effort": "Medium", "impact": "Medium" if aud in ("dev", "algo") else "High",
    })

    # 4) Open-source / GitHub — only credible for dev/algo/api/ai topics.
    if kind in ("api", "algo", "ai") or aud in ("dev", "algo"):
        snippet = {
            "api": "a tiny resilient-reconnect wrapper / order-status reconciler",
            "algo": "a clean backtest notebook for the strategy being discussed",
            "ai": "a minimal LLM-reads-your-positions demo with the broker SDK",
        }.get(kind, "a small, well-documented utility for what people are struggling with")
        plays.append({
            "format": "Open-source / GitHub", "icon": "💻",
            "title": f"Ship {snippet}",
            "hook": (f"Publish {snippet} addressing “{topic}”. README + 1 blog post. "
                     f"Devs trust code over copy."),
            "why": "Earns deep credibility with the dev/algo segment; compounding inbound via search/GitHub.",
            "effort": "High", "impact": "High",
        })

    # 5) Community engagement — start a conversation, harvest more signal.
    eng = (f"Reply helpfully in the original threads about “{topic}” (no hard sell), "
           f"then run a poll: ") if pain else f"Run a poll / open question on “{topic}”: "
    poll = {
        "options": "“Which expiry-day strategy do you actually trade?”",
        "api": "“What breaks most in your algo setup — fills, ticks, or margins?”",
        "ai": "“Would you let an AI agent place orders for you? Y/N/Only-suggest.”",
        "charges": "“What's your monthly brokerage+charges as % of profit?”",
    }.get(kind, f"“What do you want to know about {topic}?”")
    plays.append({
        "format": "Community engagement", "icon": "💬",
        "title": "Seed the conversation where it started",
        "hook": eng + poll,
        "why": "Free reach inside the exact communities, plus fresh first-party signal for the next cycle.",
        "effort": "Low", "impact": "Medium",
    })

    return plays


def _pick_primary(plays: list[dict], r: dict, kind: str) -> str:
    """The single best first move given audience + sentiment."""
    aud = r.get("audience", "retail")
    if kind in ("api", "algo", "ai") and aud in ("dev", "algo"):
        return "Open-source / GitHub"
    if r.get("sentiment") == "negative":
        return "Educational"      # acknowledge + teach beats promo when people are frustrated
    if aud == "retail":
        return "Reel / Short"
    return "Educational"


def build_actions(ranked: list[dict], cfg: dict | None = None) -> list[dict]:
    """Heuristic action plans, one per ranked topic. No network calls."""
    total = len(ranked)
    plans = []
    for rank, r in enumerate(ranked):
        kind = _kind(r["topic"])
        plays = _plays(r, kind)
        primary = _pick_primary(plays, r, kind)
        plans.append({
            "topic": r["topic"],
            "score": r.get("score"),
            "mentions": r.get("mentions"),
            "spread": r.get("spread"),
            "audience": r.get("audience"),
            "sentiment": r.get("sentiment"),
            "engagement": r.get("engagement"),
            "priority": _priority(rank, total),
            "rationale": _rationale(r),
            "channels": _CHANNELS.get(r.get("audience", "retail"), _CHANNELS["retail"]),
            "primary": primary,
            "plays": plays,
            "examples": r.get("examples", []),
        })
    return plans


# --------------------------- optional LLM ghost-writer ---------------------------

_GW_INSTR = (
    "You are the social/brand lead for an Indian discount stock broker (NSE/BSE, F&O, "
    "algo/API traders). For each rising community topic below, write punchy, specific "
    "marketing copy. Return ONLY a JSON array, one object per topic, keys:\n"
    "- i: integer index copied from the list\n"
    "- headline: a scroll-stopping post headline (<=90 chars)\n"
    "- caption: a ready-to-post caption (<=240 chars), Indian-trader voice, no hype/SEBI-risky claims\n"
    "- infographic: one concrete data-viz idea for this topic\n"
    "- reel: a 1-line reel/short concept with a 3-second hook\n"
    "- hashtags: array of 3-5 relevant hashtags (strings, with #)\n"
    "Be concrete to THIS topic and its numbers; never generic.\n\nTopics:\n"
)


def enrich_with_llm(plans: list[dict]) -> tuple[list[dict], dict]:
    """Overlay LLM-written headline/caption/ideas onto the heuristic plans.

    Returns (plans, meta). On any failure the plans are returned untouched so the tab
    still renders. meta carries prompt/response/usage for the LLM diagnostics tab.
    """
    meta = {"method": "heuristic", "model": None}
    if not plans or not os.environ.get("ANTHROPIC_API_KEY"):
        return plans, meta
    try:
        import anthropic  # lazy
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        lines = [
            f"{i}. topic=\"{p['topic']}\" | mentions={p['mentions']} | "
            f"communities={p['spread']} | audience={p['audience']} | sentiment={p['sentiment']}"
            for i, p in enumerate(plans)
        ]
        prompt = _GW_INSTR + "\n".join(lines)
        resp = client.messages.create(
            model=MODEL, max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        body = raw[raw.find("["): raw.rfind("]") + 1]
        parsed = json.loads(body)
        by_i = {o.get("i"): o for o in parsed if isinstance(o, dict)}
        for i, p in enumerate(plans):
            o = by_i.get(i)
            if not o:
                continue
            p["copy"] = {
                "headline": o.get("headline"),
                "caption": o.get("caption"),
                "infographic": o.get("infographic"),
                "reel": o.get("reel"),
                "hashtags": o.get("hashtags") or [],
            }
        meta = {
            "method": "llm", "model": MODEL, "prompt": prompt, "raw_response": raw,
            "usage": {"input_tokens": resp.usage.input_tokens,
                      "output_tokens": resp.usage.output_tokens},
        }
    except Exception as e:  # noqa: BLE001 — copy is a nice-to-have; never break the tab
        meta = {"method": "heuristic", "model": None, "error": str(e)}
    return plans, meta
