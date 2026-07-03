"""Deterministic de-noise before any LLM call (LLD-02 §6.1 + §6.6, cost plan §2.3).

Classifier, NOT censor: rules fire only on unambiguous cases; a genuine complaint
that quotes tip language survives to Haiku enrichment.

Returns (is_noise, model_tag, reason) — model_tag distinguishes plain rules
('rule-prefilter') from the vendored comms guardrails ('rule-guardrail').
"""
from __future__ import annotations

import re

from community.lib.comms_guardrails.content_policy import mentions_crypto
from community.lib.comms_guardrails.copy_rules import (
    _BUY_SELL_CALL_PATTERNS,
    _FEAR_PHRASES,
)
from community.lib.comms_guardrails.validation import validate_text
from community.reference.taxonomy import MARKET_TERMS, SPAM_HANDLES

_URL_RE = re.compile(r"https?://\S+")
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ]{2,}")  # latin + devanagari words


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _mentions_market(text: str) -> bool:
    low = text.lower()
    return any(t in low for t in MARKET_TERMS)


def check(text: str, author: str | None = None) -> tuple[bool, str, str | None]:
    stripped = _URL_RE.sub("", text or "").strip()
    words = _words(stripped)

    # 1. plain rules — empty / emoji-only / pure-link
    if len(words) == 0:
        return True, "rule-prefilter", "empty_or_link_only"
    # 2. known spam handles
    if author and author.lower() in {h.lower() for h in SPAM_HANDLES}:
        return True, "rule-prefilter", "spam_handle"

    # 3. vendored guardrails — crypto-only chatter (off-mission for an NSE/BSE broker)
    crypto_term = mentions_crypto(text)
    if crypto_term and not _mentions_market(text):
        return True, "rule-guardrail", f"crypto_only:{crypto_term}"

    # 4. vendored guardrails — tip/pump language domination
    low = text.lower()
    hits = [p for p in (_FEAR_PHRASES + _BUY_SELL_CALL_PATTERNS) if p in low]
    if len(hits) >= 2 or (hits and len(words) <= 12):
        return True, "rule-guardrail", f"tip_pump:{','.join(hits[:3])}"

    # 5. vendored guardrails — scraper artifacts dominating the text
    issues = [i for i in validate_text(text) if i.severity == "HIGH"
              and i.code in ("nan_leak", "raw_symbol")]
    if issues and len(issues) >= max(2, len(words) // 6):
        return True, "rule-guardrail", f"artifact:{issues[0].code}"

    return False, "", None
