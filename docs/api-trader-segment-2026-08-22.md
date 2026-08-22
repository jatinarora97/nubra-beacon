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

## Real specimens (receipts live in out/api-trader-lens-all.json)

1. Reddit: Flattrade + Quantman NIFTY algo, +12% in 4 months, full stack named.
2. YouTube: Claude + Dhan MCP AI trading workflow (15k engagement).
3. Instagram: Monte-Carlo strategy simulation in Google Colab (14k).
4. X: "ALGO UPDATE — Aug ROI +0%, Capital Rs 5 Cr" daily accountability posts.
5. Instagram: dev hunting an open-source Bloomberg alternative, asking for
   working guides (18k).

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

## Build candidates for Nubra (rank these, leadership)

Each maps to an API feature Nubra ALREADY has (grounding v2):

1. Nubra MCP server (AI-assistant trading) — clearest gap, proven demand,
   only Dhan is there.
2. First-order-in-5-minutes developer onboarding — attacks the invisible
   first_api stage.
3. Backtest-ready historical data bundles — feeds their bragging currency.
4. OpenAlgo integration — presence in the middleware every builder uses.
5. TradingView webhook execution — catches chart traders at the exact moment
   they become API traders.

Next action: say "go" on step 3 (the prod segment build) or hand Part 1 +
the build candidates to leadership first.
