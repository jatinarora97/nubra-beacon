"""Compliance gate — defense-in-depth (LLD-03 §3).

L1 deterministic denylist (incl. `l1.shared` — the vendored comms guardrails, one
safety vocabulary across push + community) → L2 LLM review → every draft × layer
audited to compliance_audit. L3 is the human reading the roundup.

Entry point: check(draft_text, kind, draft_ref) -> (ok: bool, reasons: list[str])
"""
from __future__ import annotations

import json
import re

from community.config.settings import settings
from community.lib.comms_guardrails.content_policy import mentions_crypto
from community.lib.comms_guardrails.copy_rules import (
    _BUY_SELL_CALL_PATTERNS,
    _FEAR_PHRASES,
)
from community.llm.client import complete
from community.store import db

# ── L1 rules (LLD-03 §3.1; case-insensitive) ──────────────────────────────

_L1_RULES: list[tuple[str, re.Pattern]] = [
    ("l1.returns", re.compile(
        r"\b(guarantee\w*|assured|risk[- ]?free)\b.{0,40}\b(returns?|profits?|income)\b", re.I | re.S)),
    ("l1.returns", re.compile(r"\b\d{1,3}\s?%\s*(returns?|profits?|gains?)\b", re.I)),
    ("l1.tips", re.compile(r"\b(intraday|stock|option|fno|f&o)\s+(tips?|calls?)\b", re.I)),
    ("l1.tips", re.compile(r"\byou should (buy|sell|short)\b", re.I)),
    ("l1.targets", re.compile(r"\b(target|tgt)\s*[:=]\s*(₹|rs\.?)?\s?\d", re.I)),
    ("l1.targets", re.compile(r"\b(sl|stop[- ]?loss)\s*[:=]?\s*(₹|rs\.?)?\s?\d", re.I)),
    ("l1.sureshot", re.compile(r"\b(sure[- ]?shot|jackpot|multibagger|pakka profit)\b", re.I)),
    ("l1.pii", re.compile(r"\b[6-9]\d{9}\b")),                       # IN mobile
    ("l1.pii", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),               # PAN
    ("l1.pii", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")),          # email
    ("l1.shaming", re.compile(
        r"(zerodha|groww|upstox|dhan|angel\s?one)\W{0,20}(scam|fraud|chor|loot|thie\w+)", re.I)),
]

_L2_SYSTEM = """You are a compliance reviewer for Nubra, a SEBI-regulated Indian stock broker.
Review the DRAFT below against this checklist and return ONLY JSON.

Checklist (SEBI/ASCI):
- No investment advice: no buy/sell/hold recommendations, price targets, stop-losses.
- No inducement: no guaranteed/assured returns, no urgency or fear language.
- No unsubstantiated claims about Nubra or competitors.
- Comparative statements must be factual and fair; never disparage a competitor.
- Representative replies must disclose Nubra affiliation.
- Tone: educational, factual, conversational.

Return: {"verdict": "pass"|"fail", "violations": [{"rule": "...", "excerpt": "...", "reason": "..."}]}"""


def _audit(draft_ref: dict, draft_text: str, layer: str, verdict: str, reason: str | None) -> None:
    db.execute(
        "INSERT INTO compliance_audit (draft_ref, draft_text, layer, verdict, reason) "
        "VALUES (%s, %s, %s, %s, %s)",
        (db.jsonb(draft_ref), draft_text, layer, verdict, reason),
    )


def l1_check(text: str) -> list[str]:
    hits: list[str] = []
    low = text.lower()
    for rule_id, pat in _L1_RULES:
        m = pat.search(text)
        if m:
            hits.append(f"{rule_id}: {m.group(0)[:60]!r}")
    for p in _FEAR_PHRASES:
        if p in low:
            hits.append(f"l1.shared.fear: {p!r}")
    for p in _BUY_SELL_CALL_PATTERNS:
        if p in low:
            hits.append(f"l1.shared.call: {p!r}")
    term = mentions_crypto(text)
    if term:
        hits.append(f"l1.shared.crypto: {term!r}")
    return hits


def l2_check(text: str, kind: str) -> tuple[bool, list[str]]:
    raw, _usage = complete(
        settings.draft_model, _L2_SYSTEM,
        f"KIND: {kind}\nDRAFT:\n{text}\n\nReturn only the JSON verdict.",
        max_tokens=1200,
    )
    try:
        blob = raw[raw.index("{"): raw.rindex("}") + 1]
        data = json.loads(blob)
        ok = data.get("verdict") == "pass"
        reasons = [f"{v.get('rule')}: {v.get('reason')}" for v in data.get("violations", [])]
        return ok, reasons
    except (ValueError, json.JSONDecodeError):
        return False, [f"l2.unparseable: {raw[:80]!r}"]


def check(draft_text: str, kind: str, draft_ref: dict) -> tuple[bool, list[str]]:
    """Full gate: L1 then L2; both audited. Returns (ok, reasons)."""
    l1 = l1_check(draft_text)
    _audit(draft_ref, draft_text, "L1_rules", "fail" if l1 else "pass",
           "; ".join(l1) if l1 else None)
    if l1:
        return False, l1
    ok, reasons = l2_check(draft_text, kind)
    _audit(draft_ref, draft_text, "L2_llm", "pass" if ok else "fail",
           "; ".join(reasons) if reasons else None)
    return ok, reasons
