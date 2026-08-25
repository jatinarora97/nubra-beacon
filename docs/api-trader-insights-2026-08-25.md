# API Traders in India — what the data shows, entity by entity, stage by stage

One-month analysis of Beacon's full corpus. 99,004 items collected from X,
Reddit, YouTube, GitHub, broker forums, app reviews, Instagram (Jul 8 –
Aug 25) · 24,235 screened for this lens · **4,733 relevant** · every number
below is computed over that set, links are exhibits not the evidence base.

## The five questions this document answers

1. How big and how visible is the API-trader segment in public chatter?
2. Where in their journey do people struggle, and where do they convert?
3. What does the data say about each player we committed to tracking?
4. What do these traders reward, and what do they punish?
5. What should Nubra build or package first — and what can't we see yet?

---

## Executive summary

1. **1 in 5 screened conversations is API-trader relevant** (4,733 of
   24,235). This is not a niche whisper; it is a fifth of the serious
   trading conversation across seven platforms.
2. **The funnel's choke point is the first API setup.** Friction share by
   stage: exploring 15% → **first_api 41%** → building 28% → scaling 7%.
   People do not abandon the idea of systematic trading — they hit a wall
   at keys/auth/first-order, exactly when they are choosing a broker. The
   broker that removes this wall converts the most motivated cohort at its
   moment of maximum openness.
3. **The frictions are mundane and therefore addressable**: pricing/tier
   confusion (21% of 1,031 friction items), platform reliability (18%),
   missing order primitives (16%), backtest distrust (16%), data-feed cost
   (15%). No exotic technology gap — product and packaging gaps.
4. **Competitor pain is visible in volume**: 171 friction items reference
   the Zerodha stack, 86 Upstox, 81 Dhan — much of it on their own forums.
   This is a standing supply of interceptable moments.
5. **Two of the seven players we track are nearly invisible to us**
   (AlgoTest ~21 corpus mentions, Tradetron ~24) — not because they are
   small but because their communities live where we do not yet listen.
   Visibility gaps are listed explicitly in §4.
6. **Nubra already registers**: 26 relevant mentions, 8 in genuine
   help-me-choose asks, plus unprompted third-party YouTube walkthroughs of
   the Nubra Python SDK.

---

## 1 · The journey: where 4,733 conversations sit and what each stage means

| Stage | n | % | Dominant voice | Friction share |
|---|---|---|---|---|
| exploring | 881 | 19% | questions (67%) | 15% |
| first_api | 619 | 13% | questions (45%) | **41%** |
| building | 1,773 | 37% | questions (44%) + showcases (24%) | 28% |
| scaling | 1,396 | 30% | **showcases (81%)** | 7% |
| churning | 64 | 1% | frictions (46%) | 46% |

**Exploring — a question market.** Two of three items are someone asking
how to start trading with data/code instead of chart-watching. Nobody owns
the answer today; the highest-engagement exploring item in our window is a
developer hunting a free "Bloomberg alternative" (18k interactions —
https://www.instagram.com/p/DbvqowotqJN/). Meaning: the funnel's mouth is
won with education and tooling content, not ads.

**first_api — the wall.** Friction share nearly triples versus exploring
and is the highest of any pre-churn stage. The named culprits are concrete:
broker registration/credential flows (a whole YouTube genre exists to walk
people through Kite Connect signup — https://www.youtube.com/watch?v=r88L9AqnNaE),
API-key/auth churn, and paid data at the door. Two accelerants appear on
the way in: AI code generation as the non-programmer's bridge
(https://www.youtube.com/watch?v=V9Ra8klDzrM) and sandbox/testnet access
wherever offered. Meaning: onboarding is not hygiene — it is the
acquisition weapon for this segment.

**Building — the biggest room.** 37% of everything. The mix flips toward
making: backtests, strategy code, AI-assisted bots, no-code builders. This
is also where middleware appears: OpenAlgo is the single most-named tool at
this stage (39 mentions), ahead of every broker. Meaning: at the building
stage traders talk to their TOOLS, and brokers reach them through those
tools.

**Scaling — public performance.** 81% showcases: live P&L threads, named
stacks, real capital (one account posted 11 daily "ALGO UPDATE" threads on
Rs 5 Cr capital in our window —
https://x.com/VolArbitrage/status/2087844181834350681). Meaning: this
cohort is identifiable, followable, and does a broker's marketing for it —
partnership material, not support load.

**Churning — few but instructive.** 64 items, half friction. The asks on
the way out are risk primitives: drawdown circuit-breakers, exposure caps
(https://reddit.com/r/IndianStreetBets/comments/1vgzjs1/thanks_a_ton_for_your_feedback_on_my_last_post_i/).
Meaning: retention features are named by the people leaving.

---

## 2 · The friction economics (1,031 items, theme-tagged, multi-label)

| Theme | Items | Share | What it means for a broker |
|---|---|---|---|
| Cost / pricing / tiers | 223 | 21% | Confusing/pay-walled API access is the #1 stated pain. Simple, generous API pricing is a differentiator you can ship without engineering. |
| Reliability / outages | 188 | 18% | WebSocket drops halt live algos and the complaints land publicly on broker forums. Uptime + honest incident comms = trust. |
| Order primitives | 172 | 16% | Atomic bracket orders (entry+SL+target in one call) are asked for and doubted; partial-fill auto-square-off gaps create real losses. |
| Backtest distrust | 170 | 16% | The community polices overfit claims. Credible, standardized backtest data is wanted infrastructure. |
| Data feed cost/access | 158 | 15% | "Which API is best" threads are decided by who bundles data free. |
| Deployment/infra | 136 | 13% | Static-IP mandates and local-to-cloud friction stall the first live deployment. |
| Onboarding/auth | 119 | 11% | Registration and token churn — the first_api wall quantified. |
| Regulation/SEBI · risk controls · data quality | 67/54/43 | 6/5/4% | Long tail; risk-control asks overlap churn retention. |

Exhibits: the atomic-bracket thread
(https://reddit.com/r/IndiaAlgoTrading/comments/1v3m4e7/no_atomic_bracket_order_support_in_india/),
a WebSocket outage halting algos on Upstox's own forum
(https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193),
free-data deciding broker choice
(https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/which_api_is_best_for_algo_trading/),
cross-broker tick variance
(https://reddit.com/r/IndianStockMarket/comments/1vcbtvh/itcs_high_price_differs_across_platforms_and_by_a/).

## 3 · What this segment rewards (1,712 showcases, theme-tagged)

| Theme | Items | Share | Reading |
|---|---|---|---|
| Automations running live | 727 | 42% | The aspiration is a bot that runs; content proves it. |
| Live P&L / results | 578 | 33% | Public accountability culture — receipts or it didn't happen. |
| Backtests as proof | 252 | 14% | The segment's resume format. |
| Free/open-data builds | 194 | 11% | "Institutional data, retail price" resonates loudly (42k-engagement NSE screener build — https://www.instagram.com/p/DbYP6PuTEDf/). |
| AI-assisted building | 129 | 7% | Small but the fastest-moving theme; MCP content pulls 15k (https://www.youtube.com/watch?v=1NN9HIK95gw). |
| No-code builders | 118 | 6% | The non-coder bridge into the segment. |

One sentence for a senior: **this segment's social currency is reproducible
proof, and whoever supplies the raw materials of proof — data, backtests,
uptime — gets talked about for free.**

---

## 4 · The landscape we said we'd track: what we see, what we don't

Numbers = mentions in the full 99k corpus / in the 4,733 relevant items /
in friction items. Grade = our visibility today.

### The 7 to track closely

| Player | Corpus / Relevant / Frictions | Visibility | What our data says |
|---|---|---|---|
| **Dhan** | 5,178 / 216 / 81 | STRONG | The loudest API-first rival, and it owns the AI-trader narrative today (Claude+Dhan MCP content). 81 friction items = its pain is also visible and interceptable. |
| **Zerodha stack** | 3,113 / 494 / 171 | STRONG | The default starting point and the biggest friction target (171). Kite Connect onboarding is a named entry barrier — the incumbent's moat leaks exactly at first_api. |
| **TradingView/Pine** | 465 / 111 / 26 | STRONG | Present at every journey stage; chart-to-execution threads (TFC) run on Zerodha's own forum. The top-of-funnel layer as promised. |
| **OpenAlgo** | 85 / 99 / 22 | GOOD, and dense | Rare pattern: more relevant mentions than raw corpus hits (every mention is on-topic). #1 named tool at the building stage. The bellwether claim checks out. |
| **AlgoTest** | 21 / 17 / 3 | **THIN — blind spot** | A $6.9M-revenue, 13k-trader company barely registers in our venues. Its community lives on its own platform/Telegram/YouTube comments — places we don't listen yet. |
| **Tradetron** | 24 / 20 / 3 | **THIN — blind spot** | Same story: broker-agnostic marketplace with 70+ integrations, near-zero footprint in our sources. |
| **SpotGamma/MenthorQ/GEX** | 67 / 10 / 0 | THIN (expected) | Global + niche; Indian retail chatter barely touches dealer-gamma. Watch via global sources, not Indian socials. |

### The rest, by layer (corpus / relevant / frictions)

| Layer | Visible to us | Nearly/fully invisible |
|---|---|---|
| Broker APIs | Upstox 780/177/**86** · Angel One 1,029/78 · Fyers 881/74 · Groww 2,333/68 · Kotak Neo 110 · Shoonya 52 · Flattrade 31 | Alice Blue 13 · ICICI Breeze 16 · IIFL XTS 36 · Paytm Money 52/1 · **Pocketful 0** |
| No-code builders | Sensibull (in Zerodha stack) · Streak (ditto) | **uTrade, AlgoBulls, Quantiply, Algomojo, Speedbot: 0 combined** — the whole independent no-code layer is dark |
| Backtesting/quant | — | Amibroker 12 · QuantConnect 46/3 · Backtrader/Zipline 4 — code-level quant talk happens off our venues |
| Charting/screeners | TradingView strong | Chartink 14 · GoCharting 3 |
| Data vendors | — | GlobalDatafeeds/TrueData 12 combined |
| Global direction-setters | IBKR 95/33 · Alpaca 41/23 (notable: 12 Alpaca frictions — devs comparing global DX) | tastytrade 3 · Composer 0 |
| Communities | r/IndiaAlgoTrading etc. (watched) | **Marketcalls/Rajandran 7** · QuantInsti 3 · Telegram/Discord: no collector |

### Addressed already vs still dark

**Instrumented (2026-08-22, live after current release):** r/algorading +
r/algotrading subreddits · keyword watch: kite connect, openalgo, algotest,
tradetron, broker api (X+Reddit) · 6 YouTube api_algo queries · 3 GitHub
queries. These directly grow AlgoTest/Tradetron/OpenAlgo/quant-code
coverage in the coming weeks.

**No visibility yet (decision needed per row):**
1. Telegram/Discord groups — no collector (consciously skipped; still the
   single biggest dark pool for this segment).
2. Marketcalls forum + QuantInsti blog — need a forum/blog adapter each.
3. AlgoTest & Tradetron own communities — their chatter stays on their
   platforms; options: scrape their public forums, or track via YouTube
   comments and app reviews (we have both collectors).
4. TradingView public scripts/comments (Pine ecosystem) — no collector.
5. FinTwit curated handle list — we watch keywords, not the specific
   algo-trader handle graph; the @VolArbitrage find suggests curating one.

---

## 5 · Build candidates — demand patterns, sized by the data above

| # | Pattern | Demand evidence | Grounding hooks (Nubra capability catalog v2) |
|---|---|---|---|
| A | **AI-native trading access** (assistant/MCP) | AI-building 129 showcases + 15k-engagement MCP content + AI codegen as the first_api bridge; Dhan alone owns this narrative today | Developer platform · Trading/portfolio APIs · data APIs. An internal Nubra MCP exists already (marketing-shaped: github.com/anuragsrivastava-zanskar/nubra-marketing-mcp-deploy) — pattern experience in-house |
| B | **Zero-friction first order** | 41% friction at first_api; onboarding theme 119; testnet demand visible | Developer platform (UAT env, TOTP automation) |
| C | **Risk primitives as API calls** | Order-primitive gaps 172 + risk-control asks 54, incl. churners' circuit-breaker requests | Trading APIs with flexi orders |
| D | **Data that feeds the proof culture** | Data-cost 158 + backtest-distrust 170 + quality 43; free-data builds = 11% of all showcases | Historical (OHLC/OI/IV/Greeks/bhavcopy) + realtime APIs |
| E | **Presence in the layers they build in** | OpenAlgo #1 at building stage; TradingView across all stages | Developer platform |

Ranking logic: A and B attack the funnel's proven choke point and the
fastest-moving theme; C and D convert the two biggest friction themes into
differentiators; E is distribution leverage on everything above.

## 6 · Method, honesty, next

1. Two-tier Haiku classification (full lens on 3,866 keyword-gated items;
   relevance screen on 20,369 question-family items). Theme tallies are
   keyword buckets over classifier output + text, multi-label; ~31% of
   frictions sit in the unthemed long tail. Counts are directional (+-15%).
2. **Reddit is undercounted**: collection gap Aug 10-25 (outage, fixed;
   backfill pending one release). Reddit carries disproportionate friction
   signal — every friction number here is a floor, not a ceiling.
3. Dataset: out/scan-v1-all.json (4,733 classified rows, internal).
4. Next: ship the release (session-pinned proxy) → run the Reddit backfill
   → close the §4 dark rows worth closing → stand up the segment as a
   permanent Beacon pipeline (design approved-in-principle, ~2 days).
