"""nubra_features access + the assumed-v0 catalog (engineering-drafted).

v1 ships on our own assumed catalog (team decision 2026-07-03): live USPs +
upcoming features drafted from public product knowledge, SEO keywords = a starter
F&O-trader set. Marketing's vetted cut publishes later as a new version and flips
`is_current` — a data swap, not a code change. The roundup flags `grounding:
assumed-v0` until then.
"""
from __future__ import annotations

from community.store import db

ASSUMED_VERSION = "assumed-v0"

# (feature, description, status, category, seo_keywords)
ASSUMED_V0: list[tuple[str, str, str, str, list[str]]] = [
    ("F&O trading on NSE & BSE",
     "Trade futures and options on NSE and BSE with a fast, reliable order flow built for derivatives traders.",
     "live", "trading",
     ["fno", "f&o", "futures", "options", "banknifty", "nifty options", "expiry", "expiry day trading"]),
    ("Flat low brokerage",
     "Flat, transparent per-order brokerage — no percentage cuts, no surprise charges on your contract note.",
     "live", "pricing",
     ["brokerage", "brokerage charges", "flat brokerage", "lowest brokerage", "charges", "hidden charges"]),
    ("Option-chain analytics",
     "Live option chain with OI, IV and greeks at a glance so option sellers and buyers can read the market quickly.",
     "live", "analytics",
     ["option chain", "open interest", "oi data", "implied volatility", "greeks", "option selling"]),
    ("Basket orders",
     "Build and fire multi-leg baskets in one shot — spreads, straddles and strangles without leg risk.",
     "live", "trading",
     ["basket order", "multi leg order", "straddle", "strangle", "iron condor", "spread order"]),
    ("API & algo trading access",
     "REST/websocket APIs for order placement and market data so you can run your own algos on your own account.",
     "live", "platform",
     ["algo trading", "trading api", "api trading", "websocket market data", "automated trading"]),
    ("Fast digital KYC",
     "Open an account fully online in minutes — Aadhaar-based digital KYC, no branch visits or paperwork.",
     "live", "onboarding",
     ["account opening", "kyc", "open demat account", "instant account opening"]),
    ("Margin trading facility",
     "Margin against holdings and clear, upfront margin requirements for intraday and carry-forward F&O positions.",
     "live", "trading",
     ["margin", "margin requirement", "mtf", "leverage", "intraday margin", "span margin"]),
    ("Advanced charts",
     "Institutional-grade charting with indicators, multi-timeframe layouts and drawing tools that persist.",
     "live", "platform",
     ["charts", "charting", "technical analysis", "indicators", "tradingview style charts"]),
    ("Options strategy builder",
     "Visual strategy builder that prices multi-leg option strategies with payoff graphs before you place them.",
     "upcoming", "analytics",
     ["strategy builder", "payoff graph", "options strategy", "max pain"]),
    ("Portfolio risk analyzer",
     "One-view risk analysis of your F&O portfolio — exposure, concentration and scenario moves.",
     "upcoming", "analytics",
     ["portfolio risk", "risk analysis", "exposure", "hedging"]),
]


def current() -> list[dict]:
    return db.query(
        "SELECT id, feature, description, status, category, seo_keywords, version "
        "FROM nubra_features WHERE is_current ORDER BY status, feature"
    )


def current_version() -> str | None:
    row = db.one("SELECT version FROM nubra_features WHERE is_current LIMIT 1")
    return row["version"] if row else None


def seo_keywords() -> list[str]:
    rows = db.query("SELECT unnest(seo_keywords) AS kw FROM nubra_features WHERE is_current")
    return sorted({r["kw"].lower() for r in rows})


def catalog_for_prompt() -> list[dict]:
    """The shape passed to the draft LLM: id, feature, description, status, category."""
    return [
        {"id": f"f_{r['id']}", "feature": r["feature"], "description": r["description"],
         "status": r["status"], "category": r["category"]}
        for r in current()
    ]
