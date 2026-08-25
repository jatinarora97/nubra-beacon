# API Traders in India — what the chatter says

Basis: Beacon's full corpus — 99,004 items across X, Reddit, YouTube, GitHub,
broker forums, app reviews, Instagram (Jul 8 – Aug 25). 24,235 screened for
this lens; **4,746 relevant items**. Every claim below links to its source.

---

## 1 · The five stages of an API trader (from raw data)

### exploring (881 items) — "how do I trade with data, not vibes?"
People teaching themselves systematic thinking before touching code.
- Learning option-chain analysis with OI data for systematic strategies —
  https://www.youtube.com/watch?v=fnV3TnPwcMs
- Backtesting long-term vs tactical timing to understand cost of errors —
  https://www.youtube.com/watch?v=nkemNaHjrEg
- A developer hunting a free "Bloomberg alternative" and asking for working
  guides (18k engagement) — https://www.instagram.com/p/DbvqowotqJN/

### first_api (619 items) — keys, auth, first order
The conversion moment. The chatter names the pain precisely.
- Kite Connect registration + credential onboarding called out as THE entry
  barrier — https://www.youtube.com/watch?v=r88L9AqnNaE
- AI code generation is how non-programmers now cross this stage —
  https://www.youtube.com/watch?v=V9Ra8klDzrM
- Screener-to-algo bridges as the on-ramp for scanner users —
  https://www.youtube.com/watch?v=IvSnlbt89yw
- High testnet uptake wherever low-friction API onboarding exists —
  https://x.com/Loafmarkets/status/2071188435927449620

### building (1,773 items) — strategies, code, backtests. The biggest stage.
- Connecting AI models to broker APIs via MCP servers for natural-language
  portfolio building — https://www.youtube.com/watch?v=MiBzyZwAnyk
- "Claude AI + Dhan MCP" AI trading workflow (15k engagement) —
  https://www.youtube.com/watch?v=1NN9HIK95gw
- AI + broker-API tutorials: LLM as the code generator for bots —
  https://www.youtube.com/watch?v=UgWQtQ3MEVE
- One strategy backtested across 123 Indian ETFs —
  https://www.youtube.com/watch?v=B6gxK84ffHg
- 45-DTE options selling backtested on Nifty (realistic CAGR framing) —
  https://www.youtube.com/watch?v=z9nviVN6pa8

### scaling (1,396 items) — live capital, infra, risk
- "ALGO UPDATE" daily P&L posts, Rs 5 Cr capital — @VolArbitrage posted 11
  in one month — https://x.com/VolArbitrage/status/2087844181834350681
- Live algo showcase: +12% in 4 months, Flattrade + Quantman, full stack
  named — https://reddit.com/r/IndiaAlgoTrading/comments/1vbnuf1/algo_trading_doing_well_12_profit_so_far_in_4/
- Chart-to-execution becoming table stakes (TradingView TFC thread on
  Zerodha's own forum) — https://tradingqna.com/t/tradingview-trade-from-chart-tfc-beta-now-live/180530
- 24/7 autonomous AI agents handling execution infra —
  https://www.youtube.com/watch?v=6MC1XqZSltw

### churning (64 items) — quitting or switching. Small count, loudest lessons.
- "Leaving trading" after volatility losses — the ask hidden inside: risk
  circuit-breakers — https://reddit.com/r/IndianStockMarket/comments/1v9y6wz/leaving_trading_ghee_khatam/
- Algo trader scaling capital, asking for risk-exposure APIs and drawdown
  limits — https://reddit.com/r/IndianStreetBets/comments/1vgzjs1/thanks_a_ton_for_your_feedback_on_my_last_post_i/
- Stuck in the F&O loss cycle, explicitly seeking a SYSTEMATIC approach —
  https://reddit.com/r/IndianStockMarket/comments/1uw650p/i_am_tired_of_this_endless_fo_loss_cycle_how_do/

---

## 2 · Tool leaderboard (what relevant items actually name)

| Tool | Mentions | In pure "help me choose/fix" asks |
|---|---|---|
| Upstox | 90 | 28 |
| **OpenAlgo** | 87 | 21 |
| Dhan | 82 | 24 |
| Zerodha / Kite | 72 | 18 |
| Sensibull | 64 | — |
| TradingView | 64 | 12 |
| Python (as the stack) | 42 | 18 |
| Fyers | 30 | 9 |
| **Nubra** | 26 | 8 |

Two reads: open-source middleware (OpenAlgo) is named as often as the top
brokers — it IS a distribution channel, not a side project. And Nubra
already appears in 8 genuine help-me asks plus organic third-party YouTube
walkthroughs of the Nubra Python SDK.

---

## 3 · What's working for people (their own success posts)

1. Switched to algo trading, "going good" — backtest-to-live credibility as
   the narrative — https://reddit.com/r/IndiaAlgoTrading/comments/1upl9lq/switched_to_algo_trading_and_it_is_going_good/
2. Option-buying algo with claimed 88% win rate — backtest + live validation
   as proof — https://reddit.com/r/IndiaAlgoTrading/comments/1v66kr8/option_buying_algo_88_win_rate/
3. No-code AI terminals for custom option-chain tools —
   https://www.youtube.com/watch?v=ria60hCiv0Q
4. Free NSE open-interest data turned into a screener (vs Rs 35k paid
   tools), 42k engagement — https://www.instagram.com/p/DbYP6PuTEDf/
5. Monte-Carlo strategy simulation in a free Colab notebook, 14k —
   https://www.instagram.com/p/DcOg4QxtOKk/
6. Honest backtests of popular strategies (including failures) as trusted
   content — https://www.youtube.com/watch?v=Ydwyc130wJY

Pattern: the segment's currency is REPRODUCIBLE PROOF — backtests, live
P&L, free-data builds. Whoever supplies the raw material for that proof
earns the audience.

---

## 4 · The friction board (1,032 friction items; the API-layer top)

1. No atomic bracket orders (entry+target+SL in one call); traders suspect
   brokers simulate them — https://reddit.com/r/IndiaAlgoTrading/comments/1v3m4e7/no_atomic_bracket_order_support_in_india/
2. Paid data feeds at the entry stage decide "which API is best" threads —
   https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/which_api_is_best_for_algo_trading/
3. WebSocket 403/1006 outages halting live algos (competitor's own forum) —
   https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193
4. Partial fills without auto square-off = unintended overnight exposure —
   https://community.upstox.com/t/algo-trading-leg-partially-executed-auto-square-off-not-triggered/15477
5. Same stock, different ticks across brokers (>50-point ATH variance) —
   data trust — https://reddit.com/r/IndianStockMarket/comments/1vcbtvh/itcs_high_price_differs_across_platforms_and_by_a/
6. Deployment friction: static-IP requirements and infra stall the
   local-to-live jump — https://reddit.com/r/IndiaAlgoTrading/comments/1uq82g6/i_have_been_building_an_algo_trading_bot_on_my/
7. No good API home for corporate actions / earnings calendars —
   https://reddit.com/r/IndianStockMarket/comments/1vbnz69/where_can_i_track_earnings_and_all_other/
8. Backtest-overfitting skepticism — trust gap between claimed and real
   edge — https://reddit.com/r/IndiaAlgoTrading/comments/1uznt9g/backtest_of_01st_to_17th_july/

---

## 5 · Build candidates — inferred purely from what people seek and use

Each candidate = a demand pattern in the data. Grounding references show
which existing Nubra capabilities each pattern touches (catalog: grounding
v2).

### A. AI-native trading access
People already wire LLMs to broker APIs and film it (MCP portfolio building,
Claude+Dhan workflows, AI codegen at the entry stage — links in §1). The
demand is "talk to my broker through my AI assistant."
Grounding hooks: Developer platform · Trading and portfolio APIs · Realtime
+ Historical data APIs. Note: an internal Nubra MCP server already exists
(marketing-shaped: github.com/anuragsrivastava-zanskar/nubra-marketing-mcp-deploy)
— the in-house pattern experience is there; the demand is for a
trading-facing one.

### B. Zero-friction first order
Registration/credential flows are named as THE entry barrier; testnets see
high uptake wherever offered; AI codegen is how non-coders self-rescue.
Demand: keys-to-first-order in minutes, with a sandbox.
Grounding hooks: Developer platform (UAT environment, automated TOTP login).

### C. Risk primitives as API calls
Atomic brackets, auto square-off on partials, and — straight from churning
traders — drawdown circuit-breakers and risk-exposure endpoints. Demand:
safety as a first-class API, not a UI feature.
Grounding hooks: Trading and portfolio APIs with flexi orders.

### D. Data that feeds the proof culture
Free/bundled feeds decide entry choices; tick consistency decides trust;
corporate-actions/earnings data has no API home; backtests (with Greeks/IV
history) are the segment's content format.
Grounding hooks: Historical data APIs (OHLC/OI/IV/Greeks, bhavcopy) ·
Realtime market-data APIs.

### E. Presence where they already build
OpenAlgo is named as often as top brokers; TradingView chart-to-execution
threads run on competitors' forums. Demand: my broker available inside the
middleware and charting layer I already use.
Grounding hooks: Developer platform.

---

## Data notes (read before quoting numbers)

1. Counts are directional (+-15%): the wide screen admits some general F&O
   confusion; a handful of global rows slip in.
2. Reddit has a collection gap Aug 10-25 (fixed; backfill in progress) — the
   friction board will only get richer.
3. Receipts file with all 4,746 classified items:
   out/scan-v1-all.json (internal).
