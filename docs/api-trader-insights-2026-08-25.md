# API Traders in India — a data analysis of one summer's chatter

## Executive summary

1. **The segment is large and visible**: of 24,235 screened items from
   Beacon's 99k-item corpus (Jul 8 – Aug 25, seven platforms), **4,733 are
   API-trader relevant** — roughly 1 in 5 screened conversations.
2. **The entry moment is the pain peak**: at the first_api stage (keys,
   auth, first order) **41% of all chatter is friction** — nearly triple the
   friction share of any other pre-churn stage. People struggle most exactly
   when they choose a broker.
3. **The top frictions are fixable product/pricing issues, not exotic
   tech**: pricing/tiers (21% of frictions), reliability/outages (18%),
   order-type gaps (16%), backtest trust (16%), data-feed cost (15%).
4. **Success culture = public, reproducible proof**: 42% of showcases are
   running automations, 33% live P&L, 14% backtests. The segment markets
   itself; a broker only needs to supply the raw material.
5. **Middleware and charting layers are named as often as brokers**:
   OpenAlgo is the #1 named tool at the building stage; TradingView appears
   across every stage. Distribution runs through layers brokers don't own.
6. **Nubra is already in the conversation** — 26 relevant mentions, 8 of
   them genuine "help me choose/fix" asks, plus organic third-party YouTube
   SDK walkthroughs.

---

## 1 · Data basis

| | |
|---|---|
| Corpus | 99,004 items, 2026-07-08 → 2026-08-25 |
| Screened by this lens | 24,235 (keyword gate 3,866 + intent-based wide screen 20,369) |
| Relevant | **4,733** |
| Classifier | two-tier Haiku (full lens on gated items; relevance screen on the rest) |

Relevant items by platform: X 2,471 · Reddit 988 · broker forums 486 ·
YouTube 434 · GitHub 304 · app reviews 29 · Instagram 21.
(X skews showcase/self-promotion; Reddit and broker forums carry most of the
friction signal.)

## 2 · The journey: five stages, and what each stage talks about

| Stage | n | % of relevant | Guidance | Showcase | Friction | Comparison |
|---|---|---|---|---|---|---|
| exploring | 881 | 19% | **67%** | 6% | 15% | 10% |
| first_api | 619 | 13% | 45% | 9% | **41%** | 4% |
| building | 1,773 | 37% | 44% | 24% | 28% | 2% |
| scaling | 1,396 | 30% | 8% | **81%** | 7% | 2% |
| churning | 64 | 1% | 14% | 34% | **46%** | 4% |

Reading the table:
1. **Exploring is a question market** (67% guidance) — whoever answers the
   "how do I start systematic trading" question owns the funnel's mouth.
2. **first_api is where intent meets a wall** — friction share jumps 15% →
   41% precisely at the broker-choice moment, then halves once people are
   through. The wall, not the wish, filters the funnel.
3. **Scaling is a stage, literally** — 81% showcases; established algo
   traders perform their success in public (daily P&L threads with named
   stacks). They are identifiable partners/advocates, not support tickets.
4. Churning is numerically tiny (64) but its frictions are the most
   actionable: risk-control asks from people leaving.

Representative exhibits: entry-barrier content on Kite Connect registration
(https://www.youtube.com/watch?v=r88L9AqnNaE) · a scaling-stage trader
posting 11 daily "ALGO UPDATE" P&L threads on Rs 5 Cr capital in our window
(https://x.com/VolArbitrage/status/2087844181834350681) · a churning trader
asking for drawdown circuit-breakers on the way out
(https://reddit.com/r/IndianStreetBets/comments/1vgzjs1/thanks_a_ton_for_your_feedback_on_my_last_post_i/).

## 3 · The friction board (1,031 friction items, theme-tagged; multi-label)

| Theme | Items | Share | What it sounds like |
|---|---|---|---|
| Cost / pricing / tiers | 223 | 21% | API access fees, plan confusion, "why pay for data" |
| Reliability / outages | 188 | 18% | WebSocket 403s, feed drops, halted live algos |
| Order types / execution | 172 | 16% | no atomic brackets, partial-fill square-off gaps |
| Backtest trust | 170 | 16% | overfitting skepticism, backtest-vs-live gap |
| Data feeds / access | 158 | 15% | paid feeds at entry, historical depth |
| Deployment / infra | 136 | 13% | static-IP rules, local-to-cloud stalls |
| Onboarding / auth | 119 | 11% | registration, keys, token churn |
| Regulation / SEBI | 67 | 6% | rule changes hitting algos |
| Risk controls | 54 | 5% | circuit-breakers, exposure limits |
| Data quality | 43 | 4% | cross-broker tick variance |

Exhibits (one per top theme): atomic-bracket gap thread
(https://reddit.com/r/IndiaAlgoTrading/comments/1v3m4e7/no_atomic_bracket_order_support_in_india/) ·
WebSocket outage halting live algos, on a competitor's own forum
(https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193) ·
"which API is best" decided by free data
(https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/which_api_is_best_for_algo_trading/) ·
cross-broker tick variance
(https://reddit.com/r/IndianStockMarket/comments/1vcbtvh/itcs_high_price_differs_across_platforms_and_by_a/).

## 4 · What's working for people (1,712 showcases, theme-tagged)

| Theme | Items | Share |
|---|---|---|
| Automation running live | 727 | 42% |
| Live P&L / results | 578 | 33% |
| Backtests as proof | 252 | 14% |
| Free/open-data builds | 194 | 11% |
| AI-assisted building | 129 | 7% |
| No-code builders | 118 | 6% |

The pattern across all six: **reproducible proof is the segment's social
currency**. Exhibits: 88%-win-rate option algo with live validation
(https://reddit.com/r/IndiaAlgoTrading/comments/1v66kr8/option_buying_algo_88_win_rate/) ·
free NSE OI screener vs Rs 35k tools, 42k engagement
(https://www.instagram.com/p/DbYP6PuTEDf/) · Claude+Dhan MCP AI workflow,
15k (https://www.youtube.com/watch?v=1NN9HIK95gw) · 123-ETF systematic
backtest (https://www.youtube.com/watch?v=B6gxK84ffHg).

## 5 · Tools: who is named, and where in the journey

Overall mentions: Upstox 90 · **OpenAlgo 87** · Dhan 82 · Zerodha 72 ·
Sensibull 64 · TradingView 64 · Python 42 · Fyers 30 · **Nubra 26**.

| Stage | Most-named tools (top 3) | Read |
|---|---|---|
| exploring | strykex, upstox, dhan | discovery content decides first impressions |
| first_api | **upstox 35, dhan 27**, zerodha | onboarding content war is two-horse today |
| building | **openalgo 39**, tradingview 32, dhan/zerodha 29 | middleware + charting own the build stage |
| scaling | sensibull 61, openalgo 35 | analytics + middleware at size |

Two conclusions: OpenAlgo (open-source, 33+ broker adapters) is effectively
a broker-distribution channel — being absent from it is being absent from
the building stage. And in pure help-me asks, Nubra already draws 8
mentions with zero outbound effort.

## 6 · Build candidates — demand patterns inferred from the data

Sized by the theme counts above; grounding hooks reference Nubra's
capability catalog (grounding v2).

| Candidate | Demand evidence (from §2-5) | Grounding hooks |
|---|---|---|
| **A. AI-native trading access** (assistant/MCP path) | AI-assisted building 129 showcases and growing; MCP content pulls 15k engagement; AI codegen is the first_api self-rescue | Developer platform · Trading/portfolio APIs · data APIs. Note: an internal Nubra MCP already exists (marketing-shaped, github.com/anuragsrivastava-zanskar/nubra-marketing-mcp-deploy) — in-house pattern experience |
| **B. Zero-friction first order** | 41% friction at first_api; onboarding/auth theme 119 items; testnet uptake wherever offered | Developer platform (UAT env, TOTP automation) |
| **C. Risk primitives as API calls** | order-type gaps 172 + risk-control asks 54, incl. churners' circuit-breaker requests | Trading APIs with flexi orders |
| **D. Data that feeds the proof culture** | data-cost 158 + backtest-trust 170 + data-quality 43; free-data builds are 11% of all showcases | Historical (OHLC/OI/IV/Greeks/bhavcopy) + realtime APIs |
| **E. Presence in the layers they build in** | OpenAlgo #1 at building stage; TradingView named across all stages | Developer platform |

## 7 · Method and caveats

1. Two-tier classification (Haiku): full lens on keyword-gated items;
   relevance screen on question-family items. Theme tallies are keyword
   buckets over classifier gists + text, multi-label; ~31% of frictions
   remain unthemed (long tail).
2. Counts directional (+-15%): the wide screen admits some general F&O
   confusion; a handful of global rows slip in.
3. Reddit has a collection gap Aug 10-25 (collector outage, since fixed;
   backfill in progress) — Reddit-heavy numbers (frictions especially) are
   UNDERCOUNTED in this snapshot.
4. Full classified dataset: out/scan-v1-all.json (4,733 rows, internal).
