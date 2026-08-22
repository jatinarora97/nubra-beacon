# API traders — what the data says, and what we do about it

Goal: get API traders onto Nubra. This doc has two halves. Part 1 = facts
from one month of real chatter. Part 2 = the to-do list. Read either alone.

---

# PART 1 — WHAT THE DATA SAYS (analysis only, no plans)

Basis: 2,000 items, Jul 23–Aug 22, all sources. 130 matched the API-trader
lens (~60 high-confidence). Small sample — treat as directional.

## Where people are in the journey

| Stage | Count | Meaning |
|---|---|---|
| exploring | ~50 | curious, asking where to start (noisiest bucket) |
| first_api | 11 | setting up keys / first order — ALMOST INVISIBLE |
| building | 45 | writing strategies, backtesting — richest bucket |
| scaling | 24 | real capital, live algos, public P&L |
| churning | 0 | tool-switching pain — WE CANNOT SEE IT YET |

The two zeros-and-elevens are the story: the entry moment (first_api) and
the frustration moment (churning) are exactly where a broker wins customers,
and exactly where our current sources are blind.

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

## Honest limits of this scan

1. Export was capped at 2,000 items — the full corpus is ~10x and unscanned.
2. "Exploring" bucket is ~half noise (generic finfluencer content).
3. churning = 0 means our sources cannot see pain, not that pain is absent.
4. ~50 items went unscreened (two parse failures).

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
2. `make dump` on the VM when reachable → restore locally → re-run the scan
   on the FULL corpus (~1 hr) → Part 1's numbers get real depth.
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

## The crux (agreed 2026-08-22)

More data BEFORE building: steps 1-2 above (release + backfill + full-corpus
scan) come first; the segment pipeline and any build-candidate pitch stand on
that. Next action: run the release when the VM is reachable.
