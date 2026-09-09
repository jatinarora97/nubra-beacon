"""Seed confirmed landscape features for the bot-gated players.

    docker compose exec -T api python scripts/seed_landscape_features.py

The weekly landscape monitor auto-populates 8 of 10 roster players from their
public pages; AlgoTest and Angel One serve JS/bot-gated pages (urls: [] in
the registry) so their catalogs stay empty unless seeded. Rows below are
verified claims from the 2026-08 web audits (evidence URL per row; see
docs/api-trader-market-research-2026-08-27.md). Idempotent: upsert on
(competitor, feature); added_by='seed' so the auto refresh never overwrites
a row's status (the monitor only overwrites added_by='auto' rows).
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from community.store import db

FEATURES = [
    # competitor, feature, status, evidence_url
    ("AlgoTest", "45+ broker integrations for execution", "shipped",
     "https://docs.algotest.in/category/broker-setup/"),
    ("AlgoTest", "Permanent free tier (25 backtests/week)", "shipped",
     "https://docs.algotest.in/product-blogs/detailed-pricing-algotest/"),
    ("AlgoTest", "7.5+ years historical NSE options backtest data", "shipped",
     "https://algotest.in/blog/free-options-backtesting/"),
    ("AlgoTest", "Public Broker Speedtest latency leaderboard", "shipped",
     "https://algotest.in/blog/broker-speedtest-algotest/"),
    ("AlgoTest", "Slippage modelling in backtests", "shipped",
     "https://algotest.in/blog/what-is-the-impact-of-slippage-on-an-algo/"),
    ("Angel One", "Free trading + historical data API (SmartAPI)", "shipped",
     "https://www.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi"),
    ("Angel One", "Option Greeks API endpoint", "shipped",
     "https://smartapi.angelone.in/smartapi/forum/topic/4254/announcing-option-greeks-api-for-smartapi-users"),
    ("Angel One", "Native TradingView order panel", "shipped",
     "https://www.tradingview.com/blog/en/angel-one-now-on-tradingview-57852/"),
    ("Angel One", "Up to 5 static IPs per API key", "shipped",
     "https://smartapi.angelone.in/smartapi/forum/topic/5254/important-updates-to-smartapi-in-compliance-with-sebi-guidelines"),
    ("Angel One", "WebSocket 2.0 streaming (1,000 subs x 3 connections)", "shipped",
     "https://smartapi.angelone.in/smartapi/forum/topic/4391/websocket-streaming-size-and-max-connections"),
]


def main() -> None:
    n = 0
    for comp, feat, status, url in FEATURES:
        n += db.execute(
            """
            INSERT INTO landscape_features (competitor, feature, status,
                                            evidence_url, added_by)
            VALUES (%s, %s, %s, %s, 'seed')
            ON CONFLICT (competitor, feature) DO UPDATE SET
                last_seen = now(), evidence_url = EXCLUDED.evidence_url
            """,
            (comp, feat, status, url))
    print(f"seeded/refreshed {n} of {len(FEATURES)} landscape features")


if __name__ == "__main__":
    main()
