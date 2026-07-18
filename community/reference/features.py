"""nubra_features access + the grounded seed catalog.

Catalog source: nubra_product_context.md (product team, received 2026-07-17) —
synthesized 1:1, no invented capabilities. Status mapping from the doc's own
language: "Available"/current app surfaces -> live; "Upcoming Retail Features"
-> upcoming; Partial / Internal-unverified / Proposed items are EXCLUDED from
grounding entirely (drafts must never claim them; the doc says so explicitly).
The doc's qualifier on historical-data coverage is baked into that feature's
description. Publishes after this seed mint v2, v3, ... via the Grounding page.
"""
from __future__ import annotations

from community.store import db

CONTEXT_VERSION = "context-v2"

# (feature, description, status, category, seo_keywords)
CONTEXT_V1: list[tuple[str, str, str, str, list[str]]] = [
    # ── live: current retail app surfaces ────────────────────────────────
    ("Option chain",
     "Full option chain with max pain, PCR, total put context, expiry selector, "
     "lot size, strike ladder and an Option Buyer mode dropdown — backed by "
     "realtime option-chain data with IV and Greeks.",
     "live", "options",
     ["option chain", "max pain", "pcr", "open interest", "oi", "strike",
      "iv", "implied volatility", "greeks", "expiry"]),
    ("Options strategies with risk shown before the trade",
     "Pre-built strategies, My Strategies and Create Strategy — every strategy "
     "card shows legs, payoff, max profit, max loss, breakeven, funds required "
     "and a probability badge. Users have publicly highlighted saving a strategy "
     "like a watchlist instrument and viewing it as a live chart.",
     "live", "options",
     ["options strategy", "payoff", "breakeven", "max loss", "max profit",
      "probability", "multi leg", "strategy"]),
    ("Scalper mode",
     "Landscape mode with a one-tap fast buy/sell ladder for active intraday "
     "traders.",
     "live", "trading",
     ["scalper", "scalping", "one tap", "fast orders", "intraday"]),
    ("Ask AI",
     "AI-assisted stock screening and analysis inside the app.",
     "live", "ai",
     ["ask ai", "ai screener", "stock screening", "ai analysis"]),
    ("Chart Analyser with F&O analytics",
     "Chart tab plus an F&O analytics tab covering OI, volatility, premium, "
     "volume and PCR with a bottom action bar.",
     "live", "analytics",
     ["chart analyser", "chart analysis", "f&o analytics", "oi chart",
      "volatility", "premium"]),
    ("Technical alerts",
     "Price, RSI, SMA and EMA alerts.",
     "live", "alerts",
     ["price alert", "rsi alert", "ema alert", "sma alert", "alerts"]),
    ("Options heat map with Volume & OI shockers",
     "Index-wise heat map with volume/OI and calls/puts toggles, ranked option "
     "rows, and High Profitable Strategies Today cards showing max profit, "
     "breakeven, max loss, funds required, probability and a trade action.",
     "live", "options",
     ["oi shockers", "volume shockers", "heat map", "options heatmap",
      "high profitable strategies"]),
    ("Per-stock F&O analytics and fundamentals",
     "Stock detail combines chart, fundamentals (financials, key ratios, "
     "shareholding pattern, corporate actions, P&L), AI signal cards, option "
     "chain, scalper, strategies and F&O analytics with OI bar chart by strike, "
     "volatility, premium, volume and an ATM line.",
     "live", "analytics",
     ["fundamentals", "key ratios", "shareholding pattern", "stock analysis",
      "oi by strike", "corporate actions"]),
    ("Advanced order entry",
     "Order entry with Apply Preset, buy/sell and delivery/intraday toggles, "
     "stoploss and target-profit expansion, advanced entry/exit, trigger, "
     "iceberg and validity controls with required-amount and balance shown.",
     "live", "trading",
     ["iceberg order", "stoploss", "target order", "trigger order",
      "order entry"]),
    ("Portfolio with pledge",
     "Holdings with P&L summary, investment/current value per holding and a "
     "detail sheet with Add, Exit and Pledge Holdings; positions across stocks, "
     "F&O and commodities.",
     "live", "portfolio",
     ["pledge", "pledge holdings", "portfolio", "holdings", "positions"]),
    ("Commodities, mutual funds, IPOs, ETFs and G-Sec",
     "MCX commodities alongside NSE/BSE stocks and F&O; discovery for mutual "
     "funds, IPOs, ETFs and G-Sec in Explore.",
     "live", "platform",
     ["mcx", "commodities", "mutual funds", "ipo", "etf", "gsec"]),
    ("Realtime market-data APIs",
     "Realtime quote, OHLCV, option-chain, order-book and Greeks streams plus an "
     "order-update socket; 20-level quote depth, multi-strike OI/volume/IV (with "
     "futures mode), ATM strike, CE/PE data, and WebSocket depth/interval "
     "controls.",
     "live", "api",
     ["market data api", "websocket", "20 depth", "option chain api",
      "greeks api", "live data", "order updates"]),
    ("Historical data APIs",
     "Historical OHLC, OI, IV, Greeks, volume and index values with batch "
     "queries and EOD bhavcopy reports. State exact range, intervals and "
     "expired-contract coverage explicitly before making strong claims.",
     "live", "api",
     ["historical data", "historical oi", "historical iv", "bhavcopy",
      "backtest data", "ohlc"]),
    ("Trading and portfolio APIs with flexi orders",
     "Single and multi order placement, modify/cancel (single and bulk), orders "
     "by status/tag, flexi orders with flexi basket state, funds, holdings, "
     "positions, and a margin API with hedge benefit, leg-level breakdown and "
     "portfolio-aware margin. Flexi order has drawn positive public feedback on "
     "perceived slippage reduction.",
     "live", "api",
     ["trading api", "algo trading", "flexi order", "basket", "margin api",
      "hedge benefit", "api trading"]),
    ("Developer platform",
     "Automated TOTP login, primary and secondary static IP support, "
     "multi-session support, Nubra UAT test environment, the NubraOSS "
     "backtesting engine and a developer AI support assistant.",
     "live", "api",
     ["totp", "static ip", "uat", "backtesting", "nubraoss", "sdk",
      "api login", "paper trading"]),
    # v2 additions (2026-07-18, user-authorized from the teammate's social
    # context after reconciliation): genuinely-live capabilities absent from
    # the product doc. Excluded from the same source and NOT added: OMS V3 +
    # News API (doc: internal/unverified), flexible brokerage as live (doc:
    # upcoming), retail basket orders (doc lists it as a competitor strength).
    ("Digital account opening and KYC",
     "Fully digital account opening and KYC.",
     "live", "platform",
     ["account opening", "kyc", "demat account", "open account"]),
    ("Transparent account and transaction charges",
     "Clear, published account and transaction charges.",
     "live", "pricing",
     ["charges", "transaction charges", "account charges", "hidden charges"]),
    ("Advanced charts",
     "Advanced charting available free — called out by users in app-store "
     "reviews ('the advanced charts are free here').",
     "live", "analytics",
     ["advanced charts", "charting", "free charts", "tradingview style"]),

    # ── upcoming: planned/documented, never to be described as live ──────
    ("Option-chain custom layouts and side views",
     "Customizable option-chain layouts with reorderable, saveable variables "
     "(OI bars, PCR, max pain, VWAP, IV change, Greeks, bid/ask spread, OI "
     "concentration and more) plus dedicated Call View and Put View.",
     "upcoming", "options",
     ["option chain customization", "custom layout", "call view", "put view"]),
    ("Buyer, seller and OI-trader option-chain modes",
     "Option-chain presets per persona: buyer mode (premium, momentum, "
     "liquidity, strike selection), seller mode (OI concentration, IV, theta, "
     "margin, strike safety) and OI-trader mode (buildup classification, PCR, "
     "max pain, volume spikes) with total call/put OI context.",
     "upcoming", "options",
     ["option buyer mode", "option seller mode", "oi trader", "oi buildup",
      "long buildup", "short covering"]),
    ("Persona-based app modes and homepage customization",
     "App modes for option sellers, option buyers, investors and OI traders "
     "changing visible tools, defaults, layouts and guidance; customizable "
     "homepage widgets and shortcuts.",
     "upcoming", "personalization",
     ["trader modes", "customize app", "investor mode", "persona"]),
    ("F&O analytics plotted against price",
     "OI, IV, premium and volume plotted against live underlying price; "
     "straddle and strangle premium charts; futures analytics across expiries "
     "(rollover and expiry pressure); buy/sell actions inside analytics views.",
     "upcoming", "analytics",
     ["straddle premium", "strangle chart", "oi vs price", "futures oi",
      "rollover"]),
    ("Strategy appstore and live risk recalculation",
     "A 40+ strategy library classified by market view, trader outcome and "
     "instrument set; leg-by-leg strategy building with payoff, max profit/loss, "
     "breakeven, probability and margin impact recalculating live and shown "
     "upfront.",
     "upcoming", "options",
     ["strategy library", "prebuilt strategies", "strategy builder",
      "live payoff", "margin impact"]),
    ("Strategy-level portfolios, SL/TP and charts",
     "Positions and performance grouped by strategy (not just legs), stop-loss "
     "and target at strategy level via P&L and risk-reward rules, and strategy "
     "time-series charts combining linked instruments.",
     "upcoming", "options",
     ["strategy pnl", "strategy stoploss", "strategy sl", "strategy chart",
      "strategy portfolio"]),
    ("One-click chart and bid/ask trading",
     "Direct trade actions from bid/ask or LTP cells across option-chain "
     "strikes, live bid/ask on charts, quick exit, re-entry and reverse for "
     "scalpers.",
     "upcoming", "trading",
     ["one click trading", "bid ask", "chart trading", "reverse trade"]),
    ("250-instrument watchlists with auto-refresh",
     "Watchlists holding up to 250 instruments with automatic quote refresh.",
     "upcoming", "platform",
     ["watchlist", "250 stocks", "auto refresh"]),
    ("OMS upgrades: presets, GTT, AMO and iceberg modes",
     "Saved order presets, flexible order-type modification (including iceberg "
     "conversion where rules permit), two configurable iceberg modes, GTT and "
     "AMO support, and removal of unnecessary app-level price restrictions.",
     "upcoming", "trading",
     ["gtt", "amo", "order presets", "iceberg modes", "after market order"]),
    ("Instant fund addition and withdrawal",
     "Instant withdrawals and instant fund additions up to Rs 5 lakh, subject "
     "to banking, risk and regulatory limits.",
     "upcoming", "platform",
     ["instant withdrawal", "instant funds", "add funds", "fund withdrawal"]),
    ("Flexible brokerage plan",
     "Pricing aligned to trading personas and usage patterns — investors, "
     "option buyers, option sellers and scalpers choose pricing that matches "
     "how they trade.",
     "upcoming", "pricing",
     ["brokerage", "low brokerage", "charges", "pricing", "brokerage plan"]),
    ("Natural-language AI scans",
     "Plain-language queries converted into market scans with visible "
     "conditions and editable filters — discovery without scanner logic.",
     "upcoming", "ai",
     ["ai scan", "natural language screener", "scanner", "stock scan"]),
    ("Option-chain and analytics alerts",
     "Alerts expanding beyond price/RSI/SMA/EMA to OI, volume, IV, Greeks, "
     "PCR, strike activity and option-chain conditions.",
     "upcoming", "alerts",
     ["oi alert", "iv alert", "pcr alert", "volume alert", "greeks alert",
      "strike alert"]),
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
