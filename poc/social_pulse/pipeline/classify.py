"""Classify each item: audience / topic / sentiment / is_noise.

Primary: Claude Haiku 4.5 (cheap/fast tier) batched. Falls back to keyword rules when
ANTHROPIC_API_KEY is absent so the prototype runs fully offline.
"""
from __future__ import annotations

import json
import os

from ..pipeline.dedupe import DedupGroup

MODEL = "claude-haiku-4-5-20251001"

_DEV = ["api", "kiteconnect", "kite api", "openalgo", "python", "sdk", "websocket",
        "automate", "automated", "bot", "llm", "agent", "backtest", "code"]
_ALGO = ["algo", "straddle", "strangle", "iron condor", "theta", "delta", "hedge",
         "backtest", "expiry"]
_OPTIONS = ["option", "ce", "pe", "call", "put", "strike", "premium", "iv", "expiry",
            "straddle", "strangle", "condor"]
_NOISE = ["gm", "good morning", "sure shot", "target", "sl", "tip", "lost my", "feeling"]


def _kw_classify(text: str) -> dict:
    t = text.lower()
    if any(k in t for k in _DEV):
        audience = "dev"
    elif any(k in t for k in _ALGO):
        audience = "algo"
    elif any(k in t for k in _OPTIONS):
        audience = "serious"
    else:
        audience = "retail"
    # tip-spam ("sure shot ... target ... sl") and greetings are noise regardless of audience
    is_tip_spam = ("sure shot" in t or ("target" in t and " sl " in f" {t} "))
    is_noise = is_tip_spam or (any(k in t for k in _NOISE) and audience == "retail") or len(t) < 25
    if any(k in t for k in ["api", "kiteconnect", "sdk", "websocket", "openalgo", "dhan", "reconnect", "postback"]):
        topic = "broker API reliability"
    elif "straddle" in t or "strangle" in t or "condor" in t:
        topic = "options strategy / adjustments"
    elif "llm" in t or "agent" in t or "ai" in t:
        topic = "AI-assisted trading"
    elif "expiry" in t:
        topic = "weekly expiry"
    else:
        topic = "general market"
    sentiment = "negative" if any(k in t for k in ["lost", "error", "issue", "shortfall", "freeze", "delay"]) else "neutral"
    return {"audience": audience, "topic": topic, "sentiment": sentiment, "is_noise": is_noise}


CHUNK = 25  # items per Haiku call — keeps the JSON array well under max_tokens

_THEMES = [
    "options-strategy", "broker-api-reliability", "algo-backtesting",
    "ai-llm-trading", "market-direction-macro", "taxes-charges",
    "portfolio-investing", "ipo-listing", "specific-stock",
    "broker-comparison", "education-howto", "regulation-sebi", "memes-noise",
]

_INSTR = (
    "Classify each Indian stock-market community message. Return ONLY a JSON array, "
    "one object per message, with keys:\n"
    "- i: the integer index of the message, copied exactly from the numbered list\n"
    "- audience: one of retail|serious|algo|dev\n"
    "- topic: pick the BEST-fitting theme from this list so related messages group "
    "together: " + ", ".join(_THEMES) + ". If none fit, use 'other:<short label>'.\n"
    "- sentiment: positive|neutral|negative\n"
    "- is_noise: bool (true for spam/tips/greetings/off-topic)\n"
    "Return exactly one object per message, even if uncertain.\n\nMessages:\n"
)


def _align(parsed: list[dict], texts: list[str]) -> list[dict]:
    """Map model output back to inputs by the 'i' index; keyword-fill any gaps so a
    miscount or dropped item never aborts the whole batch."""
    aligned: list[dict | None] = [None] * len(texts)
    for obj in parsed:
        idx = obj.get("i") if isinstance(obj, dict) else None
        if isinstance(idx, int) and 0 <= idx < len(texts) and aligned[idx] is None:
            aligned[idx] = obj
    # if the model omitted indices entirely but the count matches, take it positionally
    if all(a is None for a in aligned) and len(parsed) == len(texts):
        aligned = list(parsed)
    out = []
    for j, a in enumerate(aligned):
        a = a if isinstance(a, dict) else _kw_classify(texts[j])
        out.append({k: v for k, v in a.items() if k != "i"})
    return out


def _classify_chunk(client, texts: list[str]) -> tuple[list[dict], str, str, dict]:
    numbered = "\n".join(f"{i}. {t[:400]}" for i, t in enumerate(texts))
    prompt = _INSTR + numbered
    resp = client.messages.create(
        model=MODEL, max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    body = raw[raw.find("["): raw.rfind("]") + 1]
    parsed = json.loads(body)
    labels = _align(parsed, texts)            # never raises on count mismatch
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return labels, prompt, raw, usage


def _llm_classify(texts: list[str]) -> tuple[list[dict], dict]:
    import anthropic  # lazy
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    all_labels: list[dict] = []
    in_tok = out_tok = 0
    first_prompt = first_raw = ""
    n_chunks = kw_filled = 0
    for start in range(0, len(texts), CHUNK):
        chunk = texts[start:start + CHUNK]
        try:
            labels, prompt, raw, usage = _classify_chunk(client, chunk)
            in_tok += usage["input_tokens"]
            out_tok += usage["output_tokens"]
            if n_chunks == 0:
                first_prompt, first_raw = prompt, raw
        except Exception as e:  # noqa: BLE001 — one bad chunk shouldn't sink the rest
            labels = [_kw_classify(t) for t in chunk]
            kw_filled += len(chunk)
            if n_chunks == 0:
                first_raw = f"(chunk 0 failed: {e}; keyword-filled)"
        all_labels.extend(labels)
        n_chunks += 1
    meta = {
        "method": "llm",
        "model": MODEL,
        "prompt": first_prompt,
        "raw_response": first_raw,
        "chunks": n_chunks,
        "kw_filled": kw_filled,
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }
    return all_labels, meta


def classify_with_meta(groups: list[DedupGroup]) -> tuple[list[dict], dict]:
    """Like classify() but also returns what the LLM did (prompt/response/usage)."""
    texts = [g.representative.text for g in groups]
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    meta = {"method": "keyword-fallback", "model": None}
    labels = None
    if use_llm:
        try:
            labels, meta = _llm_classify(texts)
        except Exception as e:  # noqa: BLE001 — fall back rather than crash the demo
            meta = {"method": "keyword-fallback", "model": None, "error": str(e)}
            print(f"  [classify] LLM failed ({e}); using keyword fallback")
    if labels is None or len(labels) != len(texts):
        labels = [_kw_classify(t) for t in texts]
        if meta.get("method") == "llm":
            meta = {"method": "keyword-fallback", "model": None,
                    "error": "LLM returned wrong item count; fell back"}

    out = [{"group": g, **lab} for g, lab in zip(groups, labels)]
    return out, meta


def classify(groups: list[DedupGroup]) -> list[dict]:
    out, _ = classify_with_meta(groups)
    return out
