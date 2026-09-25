# API traders — what the data says, and what we do about it

Goal: get API traders onto Nubra. This doc has two halves. Part 1 = facts
from one month of real chatter. Part 2 = the to-do list. Read either alone.

---

# PART 1 — WHAT THE DATA SAYS (analysis only, no plans)

Basis (v1, 2026-08-25): the FULL prod corpus — 99,004 items, Jul 8–Aug 25,
all sources. 24,235 screened by the lens, **4,746 relevant** (36x the first
capped sample). Every stage is now populated.

## Where people are in the journey

| Stage | Count | Meaning |
|---|---|---|
| exploring | 881 | curious, asking where to start |
| first_api | 619 | keys / auth / first order — visible now, and painful |
| building | 1,773 | strategies, code, backtests — the biggest bucket |
| scaling | 1,396 | real capital, live algos, infra concerns |
| churning | 64 | quitting or switching — small but loud |

Kinds: 1,795 guidance-seeking · 1,717 showcases · **1,032 frictions** (the
capped sample had found exactly 1) · 197 tool comparisons.

## Tool leaderboard (what relevant items actually name)

upstox 90 · **openalgo 87** · dhan 82 · zerodha 72 · sensibull 64 ·
tradingview 64 · python 42 · fyers 30. OpenAlgo at #2 confirms the
"middleware is the distribution layer" thesis. Nubra is named in 26 relevant
items — including third-party YouTube content on the Nubra Python SDK
("lowers entry friction") that already exists without us asking.

## What is working for them (from their own success posts)

1. Backtests are their bragging currency — a backtest screenshot is to an
   API trader what a P&L screenshot is to a chart trader.
2. AI is the new entry door: "Claude AI + Dhan MCP" workflow video pulled
   15k engagement. Dhan owns this story alone right now.
3. Free data turned into tools beats paid tools as content: an NSE
   open-interest screener built free (vs Rs 35k tools) pulled 42k.
4. Public algo traders post DAILY P&L with Rs 5 Cr capital — a visible,
   followable, reachable cohort.
5. No-code builders are the bridge for non-coders into systematic trading.

## Real specimens (click to verify; full set: out/api-trader-lens-all.json)

1. Flattrade + Quantman NIFTY algo, +12% in 4 months, full stack named —
   https://reddit.com/r/IndiaAlgoTrading/comments/1vbnuf1/algo_trading_doing_well_12_profit_so_far_in_4/
2. Claude + Dhan MCP AI trading workflow, 15k engagement —
   https://www.youtube.com/watch?v=1NN9HIK95gw
3. Monte-Carlo strategy simulation in Google Colab, 14k —
   https://www.instagram.com/p/DcOg4QxtOKk/
4. "ALGO UPDATE — Capital Rs 5 Cr" daily P&L accountability: @VolArbitrage
   posted 11 of these in our one-month window —
   https://x.com/VolArbitrage/status/2087844181834350681
5. Dev hunting an open-source Bloomberg alternative, asking for working
   guides, 18k — https://www.instagram.com/p/DbvqowotqJN/
6. Free NSE open-interest screener vs Rs 35k paid tools, 42k —
   https://www.instagram.com/p/DbYP6PuTEDf/

## The friction board — what actually blocks API traders (479 API-layer frictions)

1. **No atomic bracket orders in India** — entry+target+SL in one API call;
   traders openly question whether brokers fake it via GTT —
   https://reddit.com/r/IndiaAlgoTrading/comments/1v3m4e7/no_atomic_bracket_order_support_in_india/
2. **Paid data feeds at the entry stage** — "which API is best" threads turn
   on who includes data free —
   https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/which_api_is_best_for_algo_trading/
3. **Reliability incidents kill trust**: WebSocket 403/1006 halting live
   algos (Upstox forum), partial fills without auto-squareoff creating
   unintended exposure —
   https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193
   https://community.upstox.com/t/algo-trading-leg-partially-executed-auto-square-off-not-triggered/15477
4. **Data trust**: same stock, different ticks across broker APIs (>50-point
   ATH variance) —
   https://reddit.com/r/IndianStockMarket/comments/1vcbtvh/itcs_high_price_differs_across_platforms_and_by_a/
5. **Deployment friction**: static-IP requirements, subscription tiers, and
   local-to-cloud infra stall first live deployments; corporate-actions /
   earnings-calendar data has no good API home —
   https://reddit.com/r/IndiaAlgoTrading/comments/1uq82g6/i_have_been_building_an_algo_trading_bot_on_my/
   https://reddit.com/r/IndianStockMarket/comments/1vbnz69/where_can_i_track_earnings_and_all_other/

Stage-specific extras: first_api chatter names Kite Connect registration
itself as an entry barrier (https://www.youtube.com/watch?v=r88L9AqnNaE);
churning traders ask for risk-exposure APIs / drawdown circuit-breakers
(https://reddit.com/r/IndianStreetBets/comments/1vgzjs1/thanks_a_ton_for_your_feedback_on_my_last_post_i/).

## Honest limits of this scan

1. Wide-screen precision is looser than the keyword tier — some general
   F&O-mechanics confusion rides along (counts are directional +-15%).
2. A handful of global/off-topic rows slip in (e.g. one Polymarket GitHub
   issue) — the prod segment classifier gets an India/market filter.
3. Reddit data ends Aug 19 in this corpus (collector gap; backfill planned).
4. ~100 of 24,235 items went unscreened (four parse failures).

---

# PART 2 — WHAT WE DO (plans only, no analysis)

## Done already (2026-08-22)

16 new watch sources are seeded and committed: r/algorading, r/algotrading,
keyword watch (kite connect, openalgo, algotest, tradetron, broker api),
6 YouTube queries, 3 GitHub queries. They start collecting on the next
release. Skipped for now: Telegram/Discord (user call).

## Do next, in order

1. Release + backfill (30 min of commands, then it runs itself): ships the
   new sources; the churning/first_api blind spots start filling.
2. DONE 2026-08-25: prod dump restored, full corpus scanned — Part 1 now
   carries the real numbers.
3. Build the segment as a prod system (~2 days, after leadership nods):
   - cheap keyword gate (high recall) → Haiku classifier (high precision)
     → own table `api_trader_items` with stage / layer / kind / tools /
     what-works / nubra-opening
   - "API traders" dashboard section: stage funnel, tool leaderboard,
     what-works board, openings feed, the scaling-cohort voices list
   - segment endpoints on the beacon API + its own weekly digest knob
4. Write the leadership doc v1 from the full-corpus scan (half day).

## Build candidates — checked against what Nubra ALREADY HAS (grounding v2)

What exists today, per the grounding catalog (all status LIVE): Developer
platform (automated TOTP login, static IPs, UAT test environment) ·
Historical data APIs (OHLC/OI/IV/Greeks/volume, batch queries, EOD bhavcopy)
· Realtime market-data APIs (quotes, option-chain, Greeks streams, 20-level
order book, order-update socket) · Trading/portfolio APIs with flexi orders.
That base changes the candidate list: three of five are DISTRIBUTION plays
on existing features, not new builds.

| # | Candidate | Have it? | So the work is |
|---|---|---|---|
| 1 | Nubra MCP server (AI-assistant trading) | NO — genuine gap | Build. Thin wrapper over the LIVE trading + data APIs; demand proven (Dhan's version pulls 15k engagement) |
| 2 | First-order-in-5-min onboarding | PARTIAL — dev platform + UAT env are live | Package + document the path; the tech exists, the journey does not |
| 3 | Backtest-ready data bundles | MOSTLY — historical APIs incl. Greeks/IV are live | Package + content: publish notebooks/bundles that feed their bragging-currency format |
| 4 | OpenAlgo integration | NO | Contribute a Nubra adapter to the open-source repo — distribution, not product |
| 5 | TradingView webhook execution | NO | Build; catches chart traders at the conversion moment |

## The crux — UPDATED 2026-08-25

The more-data condition is met: 4,746 relevant items, all stages populated,
1,032 frictions on the board. What remains before the segment build: ship
the pending release (new sources + reddit proxy env + backfill script), run
the reddit backfill, then leadership reads Part 1. Next action: deploy the
2026-08-25 tag, then say "go" on the segment pipeline build (~2 days).
