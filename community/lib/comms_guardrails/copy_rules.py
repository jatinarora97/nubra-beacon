# VENDORED from /Users/jatin/nubra/1.Communication/nubra-ai-personalization/nubraai-comms/intelligence/notifications/guardrails.py
# Do not edit here; run scripts/sync_guardrails.py to refresh.
# One safety vocabulary across push + community surfaces (LLD-02 §6.6).
from dataclasses import dataclass


_FEAR_PHRASES = [
    "act now", "don't miss", "last chance", "limited time",
    "before it's too late", "act fast", "hurry", "must buy", "guaranteed",
    "you'll regret", "miss out",
]


_BUY_SELL_CALL_PATTERNS = [
    "buy now", "sell now", "load up on", "back up the truck",
]


@dataclass
class ValidationResult:
    ok: bool
    reason: str = ""


def validate_copy(title: str, body: str) -> ValidationResult:
    """Run the deterministic phrase blacklist + simple heuristics on copy.
    Caller drops the candidate if `ok == False`.
    """
    text = (title + " " + body).lower()
    for p in _FEAR_PHRASES:
        if p in text:
            return ValidationResult(False, f"fear_phrase: {p!r}")
    for p in _BUY_SELL_CALL_PATTERNS:
        if p in text:
            return ValidationResult(False, f"unhedged_call: {p!r}")
    # Push-notification length policy (revised 2026-05-29 after on-device
    # testing): title ≤ 60 chars, body 60-220 chars. Body upper bound
    # bumped from 180 → 220 to give ~10 more words for context lines.
    if len(title) > 60:
        return ValidationResult(False, "title_too_long")
    if len(body) > 220:
        return ValidationResult(False, "body_too_long")
    if len(body) < 60:
        return ValidationResult(False, "body_too_short")
    # Defensive: title == body is bad copy regardless of length. Happens
    # when a bucket's body fallback ended up re-using the title (e.g.
    # an article without a summary). Catch it here so the audience
    # never sees a notification where the headline and body are identical.
    if title.strip().lower() == body.strip().lower():
        return ValidationResult(False, "title_equals_body")
    return ValidationResult(True)
