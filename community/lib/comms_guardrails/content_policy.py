# VENDORED from /Users/jatin/nubra/1.Communication/nubra-ai-personalization/nubraai-comms/intelligence/lib/content_policy.py
# Do not edit here; run scripts/sync_guardrails.py to refresh.
# One safety vocabulary across push + community surfaces (LLD-02 §6.6).
"""Content policy — keep crypto / bitcoin / cryptocurrency OUT of every
customer-facing surface (push notifications, reports, emails, WA images).

Single source of truth for the crypto denylist + helpers, used two ways:
  1. FETCH FILTER  — strip crypto news items at every fetch choke point so the
                     data never enters the pipeline (the primary omission).
  2. VALIDATOR     — a backstop `mentions_crypto()` check on composed copy/prose,
                     in case the LLM free-associates a crypto term that wasn't in
                     its (already-stripped) input.

Toggle off with NUBRA_BLOCK_CRYPTO=0. Extend coverage by editing _CRYPTO_TERMS
(one place — every surface picks it up).
"""
from __future__ import annotations

import os
import re

# Word-boundary, case-insensitive. Multi-char/unambiguous terms + the two crypto
# tickers (btc/eth) which, word-bounded, don't match inside other words. Bare
# ambiguous tokens (sol, doge, ether) are intentionally excluded — the spelled-out
# forms (solana, dogecoin, ethereum) cover them without equity false-positives.
_CRYPTO_TERMS = [
    "crypto", "cryptos", "cryptocurrency", "cryptocurrencies",
    "bitcoin", "btc", "ethereum", "eth", "altcoin", "altcoins",
    "stablecoin", "stablecoins", "dogecoin", "solana", "ripple", "xrp",
    "blockchain", "web3", "defi", "nft", "nfts", "memecoin",
    "binance", "coinbase", "satoshi",
]
_CRYPTO_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in _CRYPTO_TERMS) + r")\b", re.IGNORECASE)


def _enabled() -> bool:
    """Crypto blocking is ON by default; NUBRA_BLOCK_CRYPTO=0 disables it."""
    return os.environ.get("NUBRA_BLOCK_CRYPTO", "1").strip().lower() not in ("0", "false", "no")


def mentions_crypto(*texts) -> str | None:
    """Return the first crypto term found across the given text(s), else None.
    No-op (returns None) when blocking is disabled."""
    if not _enabled():
        return None
    for t in texts:
        if not t:
            continue
        m = _CRYPTO_RE.search(str(t))
        if m:
            return m.group(1).lower()
    return None


def is_crypto_news(item: dict) -> bool:
    """True if a news item's text fields mention crypto. Tolerant of the two
    item shapes in the codebase ({title,source,url,published_ts} and
    {title,source,time,url,image}) plus enriched {read,impact,signal,summary}."""
    if not isinstance(item, dict):
        return False
    return mentions_crypto(
        item.get("title"), item.get("summary"), item.get("description"),
        item.get("read"), item.get("impact"), item.get("signal"),
    ) is not None


def strip_crypto_news(items):
    """Drop crypto news items from a list. No-op when disabled / empty / not a
    list (returned unchanged so callers can wrap a fetch return inline)."""
    if not _enabled() or not items or not isinstance(items, list):
        return items
    return [it for it in items if not is_crypto_news(it)]
