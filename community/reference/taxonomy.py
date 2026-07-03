"""Seeded topic taxonomy, issue types, broker gazetteer, spam handles (LLD-02 §6.4/§8).

Stable snake_case keys — velocity/longitudinal tracking depends on them (arch §4.2).
"""
from __future__ import annotations

import re

from community.store import db

# topic_key -> (label, evergreen)
TOPICS: dict[str, tuple[str, bool]] = {
    # market action / instruments
    "fo_expiry": ("F&O expiry action", False),
    "option_selling": ("Option selling strategies", False),
    "option_buying": ("Option buying / weekly plays", False),
    "intraday_trading": ("Intraday trading", False),
    "swing_trading": ("Swing trading", False),
    "algo_trading": ("Algo / API trading", False),
    "futures_trading": ("Futures trading", False),
    "commodity_trading": ("Commodity trading (MCX)", False),
    "currency_trading": ("Currency derivatives", False),
    "market_crash": ("Market fall / correction talk", False),
    "market_rally": ("Market rally / all-time highs", False),
    "nifty_banknifty_levels": ("Nifty/BankNifty levels & views", False),
    "stock_picks": ("Stock discussion / picks", False),
    "ipo": ("IPO listings & GMP", False),
    "smallcap_midcap": ("Small/midcap moves", False),
    "global_markets": ("Global market cues", False),
    # broker experience
    "broker_reliability": ("Broker app reliability / outages", False),
    "brokerage_charges": ("Brokerage & charges", False),
    "broker_comparison": ("Broker comparisons / switching", False),
    "order_execution": ("Order execution & slippage", False),
    "margin_rules": ("Margin & leverage rules", False),
    "account_opening_kyc": ("Account opening / KYC", False),
    "funds_withdrawal": ("Funds settlement & withdrawal", False),
    "broker_support": ("Broker customer support", False),
    "trading_api": ("Broker APIs / websockets", False),
    "charting_tools": ("Charting & analysis tools", False),
    # investing
    "mutual_funds": ("Mutual funds & SIPs", False),
    "sip_investing": ("SIP / long-term investing basics", True),
    "etf_index": ("ETFs & index investing", True),
    "portfolio_review": ("Portfolio reviews", False),
    "dividend_investing": ("Dividend investing", True),
    "gold_bonds": ("Gold / SGB / bonds", False),
    # education / evergreen
    "option_greeks_basics": ("Options education / greeks", True),
    "technical_analysis": ("Technical analysis education", True),
    "fundamental_analysis": ("Fundamental analysis education", True),
    "trading_psychology": ("Trading psychology & discipline", True),
    "beginner_questions": ("Beginner how-do-I questions", True),
    # regulation / money
    "sebi_regulation": ("SEBI rules & regulation", False),
    "tax_filing": ("Trading taxes & ITR filing", True),
    "trading_scams": ("Tip scams / fraud warnings", False),
    "pnl_sharing": ("P&L screenshots & journals", False),
}

ISSUE_TYPES = [
    "outage", "order_reject", "charges", "kyc",
    "app_crash", "api_websocket", "funds_settlement", "support",
]

# canonical broker key -> aliases (matched word-boundary, case-insensitive)
BROKER_GAZETTEER: dict[str, list[str]] = {
    "nubra": ["nubra"],
    "zerodha": ["zerodha", "kite", "coin app"],
    "groww": ["groww"],
    "upstox": ["upstox"],
    "dhan": ["dhan"],
    "angel_one": ["angel one", "angelone", "angel broking"],
    "icici_direct": ["icici direct", "icicidirect"],
    "kotak_securities": ["kotak securities", "kotak neo"],
    "hdfc_securities": ["hdfc securities", "hdfc sky"],
    "paytm_money": ["paytm money"],
    "fyers": ["fyers"],
    "shoonya": ["shoonya", "finvasia"],
    "5paisa": ["5paisa"],
    "sbi_securities": ["sbi securities", "sbicap"],
    "motilal_oswal": ["motilal oswal"],
    "sharekhan": ["sharekhan"],
}

_ALIAS_RES = {
    key: re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in aliases) + r")(?![A-Za-z])", re.I)
    for key, aliases in BROKER_GAZETTEER.items()
}

# Known tip/pump spam handles — placeholder, extended from ops experience.
SPAM_HANDLES: list[str] = []

# Small market-term list used by the prefilter to tell "crypto-only chatter"
# from "crypto mentioned in a market debate" (classifier, not censor).
MARKET_TERMS = [
    "nifty", "banknifty", "sensex", "nse", "bse", "mcx", "f&o", "fno", "option",
    "futures", "intraday", "broker", "demat", "sebi", "stock", "share", "equity",
    "mutual fund", "sip", "ipo", "trading", "zerodha", "groww", "upstox", "dhan",
]


def resolve_broker(text: str | None) -> str | None:
    """Gazetteer-only broker linking (LLD-02 §6.4): the LLM's free-text broker
    string must resolve against an alias or it becomes None — never guessed."""
    if not text:
        return None
    for key, rx in _ALIAS_RES.items():
        if rx.search(text):
            return key
    return None


def brokers_in(text: str) -> list[str]:
    return [k for k, rx in _ALIAS_RES.items() if rx.search(text)]


def taxonomy_keys() -> set[str]:
    return set(TOPICS)


def seed_taxonomy() -> int:
    rows = [(k, label, ever) for k, (label, ever) in TOPICS.items()]
    db.executemany(
        """
        INSERT INTO topic_taxonomy (topic_key, label, evergreen)
        VALUES (%s, %s, %s)
        ON CONFLICT (topic_key) DO UPDATE SET label = EXCLUDED.label,
                                              evergreen = EXCLUDED.evergreen
        """,
        rows,
    )
    return len(rows)
