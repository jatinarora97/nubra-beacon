# Finding and targeting API traders — market research, 2026-08-27

**What this is.** Three questions, answered with two evidence bases: (1) Beacon's corpus — ~99k items Jun–Aug 2026, of which ~4,760 classified API-trader-relevant ("lens items"); (2) live web audits run 2026-08-27 (docs portals, pricing pages, GitHub API, forum stats, t.me previews). Every claim carries a link. **Observed** = counted in data or fetched from a page. **Inferred** = our reading, labeled as such.

---

## The 10-second version

1. **Where they are**: r/IndiaAlgoTrading is the single best venue (448 lens items, 52% API-trader density, 21k members growing ~200%/yr). OpenAlgo (GitHub+Discord) is the densest developer pool — and Nubra is already on its broker list. Broker-owned forums are where first-time API users concentrate — and Nubra doesn't have one.
2. **The #1 complaint against every incumbent is API/data pricing** — and Nubra's API pricing is publicly undisclosed. That's a free positioning win being left on the table.
3. **Nubra's owned surface is good** (public docs, PyPI SDK, UAT env, tutorials); **its third-party surface is near-zero**: 0 TradingQnA posts, ~0 discoverable Reddit threads, 1 GitHub star, absent from AlgoTest/Tradetron's own broker lists, no Chittorgarh page. Dhan out-mentions Nubra ~8–11x in the corpus.
4. **The incumbents' universal weak spots — no test env (3 of 6), daily-token auth pain, websocket reliability, paywalled/removed depth — are exactly what Nubra's stack already attacks.** The story exists; the distribution doesn't.
5. **Three segments, three doors**: explorers (19%) live on YouTube/generalist subs and ask learning questions; first-timers (13%) over-index on broker forums and hit auth/data-cost walls; the 68% already building live in r/IndiaAlgoTrading + GitHub and respond to proof (latency benchmarks, live P&L, integrations), not ads.

---

# Part A — Competitors vs Nubra, from the ground up

## A1. Broker API scorecard (web audit, 2026-08-27)

Sector context: SEBI's retail-algo framework (live Apr 1, 2026) forced daily 2FA, static-IP whitelisting, 10 orders/sec caps on every broker ([Zerodha's explainer](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework)). Auth pain and static IPs are industry constants now — the differentiator is who absorbed them gracefully.

| Dimension | Zerodha | Dhan | Upstox | Angel One | Fyers | Groww |
|---|---|---|---|---|---|---|
| Docs quality | **A** | A- | A- | C+ (JS-only SPA) | B- | B+ |
| Getting started | B- | B | B | B+ | C+ | B- |
| API+data price | ₹0 exec / [₹500-mo data](https://zerodha.com/products/api/) | ₹0 exec / [₹499-mo data](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/) | [₹0 all](https://upstox.com/trading-api/) | [₹0 all](https://www.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi) | [₹0 all](https://support.fyers.in/portal/en/kb/articles/does-fyers-charge-any-subscription-fees-for-trading-api) | [₹499-mo "early bird" vs ₹2,000 list](https://groww.in/trade-api) |
| Data capability | B (5-depth, no Greeks) | **A** ([20/200-depth](https://dhanhq.co/docs/v2/full-market-depth/), Greeks) | A- (30-depth paywalled) | B- (20-depth [removed Apr 2025](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025)) | B+ ([50-depth TBT, 15 symbols](https://www.marketcalls.in/python/a-simple-guide-to-using-fyers-tbt-feed-via-websocket-with-protobuf-python-tutorial.html)) | B (5-depth, Greeks) |
| SDKs + ecosystem | **A** (8 langs) | A- (TV native) | A- (MCP leader) | B- (SDK 15 months stale) | B+ (TV full) | C+ (Python only) |
| Sandbox | C ([half-launched](https://kite.trade/docs/connect/v3/sandbox/), FAQ denies it exists) | B ([orders, no data](https://docs.openalgo.in/connect-brokers/brokers/dhan-sandbox)) | B- (payload-only) | **F** none | **F** none | **F** none |
| Dev community | **A** ([~15.3K-discussion forum](https://kite.trade/forum/)) | A- ([MadeForTrade](https://madefortrade.in/)) | B+ ([staffed Discourse](https://community.upstox.com/)) | D (spam, absent admins) | C+ (link-rotted forum) | **F** (none published) |
| 2025–26 reliability | C ([Feb-26 outage](https://www.niftytrader.in/markets/zerodha-kite-outage-traders/)) | B- ([data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053)) | C+ ([websocket pattern](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420)) | C- ([Mar-26 outage, no statement](https://www.businessupturn.com/finance/stock-market/angel-one-down-today-traders-say-they-cant-exit-positions-amid-platform-glitch/)) | C- ([21+ outages since Mar-25](https://statusgator.com/services/fyers/trading-via-apis)) | B (young) |

Second tier, one line each: **Kotak Neo** [₹0/order API brokerage since Nov 2025](https://www.kotakneo.com/support/is-neo-trade-api-free-of-cost/) — the price floor · **Flattrade** [free API + ₹0 brokerage](https://flattrade.in/algotrading/) · **Shoonya** free full stack, community-grade polish · **ICICI Breeze** free but [most restrictive rules](https://api.icicidirect.com/breezeapi/documents/index.html) (no market orders, NSE only) · **Pocketful** ₹0 APIs but [historical data "coming soon"](https://api.pocketful.in/) · **5paisa** free + [docs-trained AI assistant](https://www.5paisa.com/blog/5paisa-developer-apis-xstream-ai-assistant) · **Alice Blue / Paytm Money / IIFL** quiet or churning.

## A2. What the chatter says about them (lens corpus, Jun–Aug 2026)

| Competitor | Lens mentions | Friction | Top gripes | Showcase | Read |
|---|---|---|---|---|---|
| Zerodha/Kite | 440 | 178 | **pricing 44**, order primitives, reliability | 56 | Default incumbent; most-complained-about API pricing |
| Dhan | 244 | 90 | pricing 22, order primitives, reliability | 21 | #2 mindshare; strong own-content machine |
| Upstox | 209 | 95 | **pricing 33, reliability 24** | 17 | Highest friction ratio (45%); websocket breakage dominates its forum |
| TradingView/Pine | 146 | 29 | pricing | **52** | Loved layer — integration is the prize, not a rival |
| OpenAlgo | 103 | 26 | reliability, pricing | **50** | Community darling; de-facto multi-broker abstraction |
| Fyers | 96 | 29 | reliability, pricing, onboarding | 19 | Balanced; data-quality gripes |
| Angel One | 95 | 28 | pricing, reliability | 14 | Mid-pack; corporate-action data gaps |
| Groww | 75 | 21 | pricing | 5 | Big broker, near-zero API community (inferred from mention mix) |
| Shoonya | 34 | — | — | — | Too thin to judge; loved as "free API" option |
| Tradetron / AlgoTest / Streak | 23 / 21 / 3 | — | — | — | **Too thin to judge from chatter** — their audiences live in their own Telegram/forums, not our sources (observed absence; venue gap, not proof of irrelevance) |

**Cross-cutting (observed): cost/pricing is the #1 friction theme for every large broker; reliability is #2.** Example threads: [ "Which API is best for algo trading" — free-data ask, r/IndiaAlgoTrading](https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/which_api_is_best_for_algo_trading/) · [Upstox websocket 403 outage thread](https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193) · [daily broker-API login (TOTP) automation pain — Nubra named](https://reddit.com/r/IndiaAlgoTrading/comments/1vh3obr/how_are_you_automating_daily_broker_api_login/).

## A3. The 7 to track — verdicts (web + chatter merged)

1. **Dhan** — deepest data product in market ([20/200-level depth](https://dhanhq.co/docs/v2/full-market-depth/), Greeks, order socket), native TradingView both ways + [first-party TV webhooks](https://web.dhan.co/assets/Pdf/Webhooks.pdf), active forum. Cracks: the famous long-lived token is dead (24h now), Apr-2026 SEBI go-live was rough, and a credible ["DO NOT buy Dhan API for Data" data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053) stands unresolved. Sharpest direct rival, confirmed.
2. **AlgoTest** — [7.5+ yrs backtest data, permanent free tier](https://docs.algotest.in/product-blogs/detailed-pricing-algotest/), [45-broker integrations](https://docs.algotest.in/category/broker-setup/), honest slippage education, and the **[public Broker Speedtest leaderboard](https://algotest.in/blog/broker-speedtest-algotest/) — API latency is now third-party-benchmarked whether a broker opts in or not.** Nubra is absent from its broker list (see A6).
3. **Tradetron** — scale ([100+ brokers, 405k signups claimed](https://tradetron.tech/)) but cost stacking (plan + [₹20/backtest](https://tradetron.tech/pages/backtest) + marketplace fees + profit share), execution-failure forum categories, and a [marketplace-as-unregistered-advice controversy](https://www.caclubindia.com/forum/retail-algo-trading-scam-details-578275.asp?offset=2). Integration target, not a model to copy.
4. **OpenAlgo** — [2,520★ / 1,199 forks, pushed same-day](https://github.com/marketcalls/openalgo), [35 brokers incl. Nubra](https://docs.openalgo.in/connect-brokers/brokers), 3,000+ Discord, AGPL with [a brokers-explainer](https://www.marketcalls.in/openalgo/why-openalgo-is-licensed-under-agpl-3-0-and-what-it-means-for-brokers-and-traders.html). The credibility layer for serious Indian API traders; being well-maintained there is distribution.
5. **TradingView (+Pine)** — native execution now table stakes: Dhan, Fyers (incl. options), Paytm, Alice Blue, Motilal, [Angel One added Jul 2026](https://www.tradingview.com/blog/en/angel-one-now-on-tradingview-57852/). Zerodha still absent. Chatter loves it (52 showcases). Nubra has [a DIY webhook guide](https://nubra.io/products/api/blogs/tradingview-to-nubra-webhook-guide), no native panel.
6. **SpotGamma / MenthorQ** — $89–$349/mo dealer-gamma analytics ([SpotGamma pricing](https://spotgamma.com/subscribe/), [MenthorQ pricing](https://menthorq.com/pricing/)). **India has no equivalent at their maturity** — only indie dashboards ([StockMojo GEX](https://stockmojo.in/gamma-exposure/nifty), Vtrender, OptionsFlow.in); Sensibull/Quantsapp do OI/Greeks but no gamma-regime product. Open niche relevant to the H4 fragility thesis. (Inference: NSE flow is retail-vs-prop, not dealer-intermediated — the framing transfers imperfectly.)
7. **Zerodha (Kite+Streak+Sensibull)** — owns the whole stack: [free personal APIs + ₹500 data](https://zerodha.com/products/api/), 8 SDK languages, the [15.3K-discussion forum](https://kite.trade/forum/), Streak and Sensibull free for its users. Cracks: 5-depth max, no native Greeks, 1/sec quote limit pain, [contradictory half-launched sandbox](https://kite.trade/docs/connect/v3/sandbox/), no TradingView execution, recurring outages. The moat is community, not capability.

## A4. Where Nubra is stronger (observed on competitor surfaces)

| Nubra capability | Why it wins today |
|---|---|
| **UAT test environment** | Angel One, Fyers, Groww have **no sandbox at all**; Upstox/Dhan's are partial; Zerodha's own FAQ [denies its sandbox exists](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs) |
| **Automated TOTP login** | Zerodha = daily browser login; Upstox tokens die 3:30 AM; Dhan killed its long-lived token; Fyers killed refresh tokens Apr 2026. (Angel One + Groww also have TOTP flows — the edge is over the OAuth brokers) |
| **Primary + secondary static IP** | Everywhere else static IP is a complained-about burden ([Dhan thread, 150+ replies](https://madefortrade.in/t/update-for-api-traders-new-changes-in-dhanhq-api-authentication-process-and-updates/56286)); dual-IP-as-failover framing is unique |
| **20-level depth as standard** | Zerodha/Groww ship 5; Angel One removed 20; Upstox's 30 and Dhan's 20/200 are paywalled/plan-gated. Caveat: Nubra's own API pricing is unpublished, so "unpaywalled" is not yet a public claim |
| **Historical Greeks/IV/OI** | **No deep-audit competitor documents historical Greeks as an API product** — all Greeks elsewhere are live/snapshot. Genuine differentiator for backtesters, and backtest_trust is a top-5 friction theme (170 items) |
| **Hedge-benefit margin API + flexi/basket orders** | Only partial equivalents exist (Kite basket-margin calc, Fyers multileg) |
| **Dev AI support assistant** | Only 5paisa has a comparable docs-trained assistant |

## A5. Where competitors are stronger

1. **Community + forum**: Zerodha 15.3K discussions, Dhan and Upstox staffed forums — no Nubra dev forum exists anywhere public.
2. **SDK breadth**: Zerodha 8 languages, Upstox 6, Fyers 5 active — Nubra's public story is Python-first ([NubraAPI org: 3 repos, 1 star](https://github.com/NubraAPI)).
3. **Third-party coverage**: all six deep brokers are on AlgoTest + Tradetron + OpenAlgo; Nubra is confirmed only on OpenAlgo.
4. **Docs maturity**: Upstox ships [monthly dated announcements](https://upstox.com/developer/api-documentation/announcements/), Zerodha publishes [full rate-limit/exception tables](https://kite.trade/docs/connect/v3/exceptions/) — no public Nubra changelog or rate-limit table was findable.
5. **Historical range + raw depth ceiling**: Upstox daily candles from 2000; Dhan 200-level/Fyers 50-level beat 20 on raw levels (narrow instrument caps).
6. **Price floor**: Kotak Neo ₹0/order API brokerage, Flattrade ₹0, Upstox ₹10 promo.

## A6. Not comparable — competitors have it, Nubra has no stated equivalent

- **Native TradingView order routing** (Dhan, Fyers incl. options) and **first-party TV-alert webhooks** (Dhan)
- **MCP servers / AI-agent order execution / plugin marketplaces** ([Upstox MCP + Agent Skills + Claude plugins](https://upstox.com/developer/api-documentation/mcp-integration/), Dhan MCP, [Groww MCP](https://groww.in/updates/groww-mcp)) — and the chatter's fastest-growing G3 cluster is exactly AI/MCP/LLM workflows
- **First-party cloud strategy hosting** ([Groww Cloud](https://groww.in/updates/groww-cloud-algo-trading): no external VPS, no IP whitelisting) — attacks deployment_infra friction (136 items) at the root
- **No-code algo layer** (Streak) and **bundled options analytics** (Sensibull) free-with-broker
- **Long-lived read-only token** ([Upstox 1-yr Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/))
- **Published rate-limit tables + public changelog** — every serious competitor has these; cheap to close

## A7. Housekeeping flags found during the audit (internal)

1. **API pricing is publicly undisclosed** ([pricing page has no API line](https://nubra.io/pricing)); third parties [explicitly flag it](https://www.multibagg.ai/market-pulse/articles/zerodha-nubra-dhan-api-comparison-cmp5l0ayn000ct70j0frlhjln). Since pricing is the market's #1 friction theme, silence here reads as risk to exactly the audience being courted.
2. **AlgoTest/Tradetron listing discrepancy**: [Nubra's FAQ claims both integrations](https://nubra.io/products/api/docs/faq/integrations/index.html), but [AlgoTest's 45-broker directory doesn't list Nubra](https://docs.algotest.in/category/broker-setup/) and Tradetron's public pages don't either. A trader verifying the claim hits a dead end.
3. **"NubraOSS" is not publicly findable** — github.com/nubraoss 404s, the term returns nothing. Our own grounding doc lists it as a live feature; either it ships publicly or the grounding wording should change.
4. **PyPI package (`nubra-sdk`, [v0.5.1, actively released](https://pypi.org/pypi/nubra-sdk/json)) has no project URLs** pointing back to docs/GitHub — a 5-minute fix that helps every pip-install discovery.

---

# Part B — Where the API traders are

## B1. Venue map (lens items ÷ venue total = density; observed)

| Venue | Lens items | Density | Verdict |
|---|---|---|---|
| GitHub (all repos) | 304 | **68%** | Purest habitat, small |
| **r/IndiaAlgoTrading** | **448** | **52%** | **#1 by size AND concentration**; [21k members, ~+200%/yr](https://gummysearch.com/r/IndiaAlgoTrading/) |
| Upstox Community forum | 241 | 27% | First-timers' habitat, broker-owned |
| Zerodha TradingQnA | 235 | 12% | Large + open ([5,061-topic algo category](https://tradingqna.com/categories)) |
| YouTube | 438 | 12% | Tutorial supply; core-algo channels are 3k–56k subs, not the 1M options celebrities |
| Twitter/X | 2,488 | 7% | Biggest raw pool, heavily vendor/bot-diluted (observed in voices analysis) |
| r/IndianStockMarket · r/IndianStreetBets | 218 · 120 | 2–5% | Reach venues, incidental algo content |
| Instagram · app reviews | 28 · 31 | ~1% | Not habitats for this segment |

Not in our corpus but verified live: **OpenAlgo Discord (3,000+, highest dev density)**, **[AlgoTest support Telegram (17.5k members)](https://t.me/AlgoTest_in)**, **[kite.trade forum (15.3K discussions)](https://kite.trade/forum/)**, Dhan's MadeForTrade, [Fyers Telegram (10.9k)](https://t.me/fyersofficial), QuantInsti/EPAT + IIT quant-fest circuit. These are the venues Beacon can't see yet (backlog: Telegram/Discord/forum collectors).

## B2. Nubra visibility today (cold-eyes audit, condensed)

| Surface | Status |
|---|---|
| Google "Nubra API" · docs portal · homepage nav · PyPI · YouTube tutorials · UAT docs | **Found — owned surface is genuinely good** |
| OpenAlgo broker list | **Found** ([dedicated page](https://docs.openalgo.in/connect-brokers/brokers/nubra)) |
| GitHub traction (1★), X reach, app-store review counts (4.4★/22 iOS) | **Thin** |
| API pricing · TradingQnA (0 posts) · discoverable Reddit threads · AlgoTest/Tradetron own lists · TradingView native · Chittorgarh/comparison sites · independent API reviews on YouTube · Telegram · dev forum · "NubraOSS" | **Absent** |

Corpus benchmark (observed): Nubra 463 corpus / 31 lens mentions vs Dhan 5,178 / 244 — **~11x / ~8x gap**, and a chunk of Nubra's lens presence is its own YouTube channel (inferred from channel attribution). The few organic mentions are high-quality though: real algo traders [evaluating Nubra's broker-streamed Greeks](https://reddit.com/r/IndiaAlgoTrading/comments/1vbk8sg/brokerstreamed_greeks_vs_calculating_them_inhouse/) and [naming Nubra in TOTP-automation threads](https://reddit.com/r/IndiaAlgoTrading/comments/1vh3obr/how_are_you_automating_daily_broker_api_login/). (Note: web search finds ~none of these — they're mentions inside threads, not Nubra-titled threads, so a googling trader sees nothing.)

## B3. The targeting map — tiers and concrete plays

**Tier 1 — high density, open door (do these):**
1. **OpenAlgo**: officially own/maintain the Nubra connector (a broken community connector is worse than none), be present in Discord under disclosed broker identity, sponsor via [FOSS United channel](https://fossunited.org/fosshack/2026/partner-projects/openalgo), publish "Nubra × OpenAlgo" first-party guides.
2. **Own dev forum + SDK gravity (the kite.trade playbook)**: stand up a Discourse forum with engineers answering; get the GitHub org past 1 star by making the SDK repo the canonical support channel; add PyPI project URLs.
3. **r/IndiaAlgoTrading**: mod-approved flaired official account; monthly "ask our API engineers" thread; answer *any* broker's auth/latency/rate-limit questions, zero promotion outside the flair (90/10 rule).
4. **AlgoTest**: resolve the listing discrepancy, get integrated, then **engineer for the [Broker Speedtest](https://algotest.in/blog/broker-speedtest-algotest/)** — a top-3 latency rank there is the cheapest credible marketing asset available to an API-first broker.

**Tier 2 — reach with a moderated door**: disclosed sponsored integration tutorials with core-algo YouTube (SquareOff 56k, AlgoTest 32k, marketcalls 30k, QuantInsti 28k); educational-only presence on TradingQnA; a Quantra course on the Nubra API ([the Kite Connect course is the exact template](https://quantra.quantinsti.com/course/algo-trading-zerodha-kite)) + IIT quant-fest API-credit sponsorships; native TradingView panel (Angel One just showed the path).

**Tier 3 — monitor, don't chase**: r/algotrading (1.9M, global, strict mods), ISB/ISM (sentiment), FinTwit (founder-led commentary only), Telegram-at-large (**never the signal channels** — [SEBI is actively barring operators](https://www.moneylife.in/article/902-crore-refund-40-lakh-penalty-sebi-bars-3-telegram-channel-operators/80354.html); run an own support group instead — AlgoTest proved utility alone scales to 17.5k).

---

# Part C — The three segments, consolidated with targeting

Sizes from the lens corpus (observed); stage → segment mapping: exploring→G1, first_api→G2, building/scaling/churning→G3.

| | **G1 — want to trade with APIs** | **G2 — first time using APIs** | **G3 — already tried / using** |
|---|---|---|---|
| Size | 883 (19%) | 621 (13%) | 3,260 (68%) |
| Where | Twitter, YouTube, r/IndianStockMarket, generalist subs | **Broker-owned forums over-index**, YouTube, r/IndiaAlgoTrading | r/IndiaAlgoTrading, **GitHub**, forums, Twitter |
| What they post | 67% guidance-seeking: learning paths, "is my strategy scalable", how to go manual→systematic. Almost nothing about APIs themselves yet | 45% guidance + **41% friction**: API keys, TOTP/static-IP setup, websocket how-tos, "which API is best / has free data" | **50% showcase**: live P&L, automation running, backtest proof; plus VPS/infra, expired-options data, and a fast-growing **AI/MCP/LLM** cluster |
| What converts them (inferred from asks) | Education that meets them pre-API: manual→systematic content, strategy-validation tools, backtesting as the hook (NubraOSS story if it ships publicly) | **Time-to-first-order.** Onboarding guides, UAT sandbox (no funded account to experiment — unlike Fyers), TOTP automation, transparent pricing, responsive forum | Proof, not promises: Speedtest rank, published rate limits, historical-Greeks depth, integrations (OpenAlgo/TradingView/MCP), engineers visible in their venues |
| Concrete play | YouTube tutorial series + Quantra course + quant-fest sponsorship | Broker-forum-grade support surface of our own + "first order on UAT in one sitting" content + r/IndiaAlgoTrading answers | OpenAlgo connector ownership, AlgoTest Speedtest, MCP/agent surface (the one capability gap squarely in this segment's growth path), dev-forum AMAs |

**The consolidated read (inferred, from all observed above):** G2 is the conversion choke point (41% friction) and it congregates on *broker-owned* surfaces — a segment Nubra structurally cannot reach until it has its own forum/support surface. G3 is 68% of the market and runs on proof-artifacts (benchmarks, integrations, showcases); its two live currents — TradingView execution and AI/MCP workflows — are both currently "no Nubra equivalent stated." G1 is cheapest to reach (education scales) but longest to convert.

---

## Caveats

1. Reddit coverage in the corpus thins after Aug 10 (outage; prod is backfilled, this analysis DB was restored Aug 25) — recent reddit trends undercounted.
2. Twitter lens counts measure content *supply* (vendors/bots heavy), not organic demand; venue analysis corrected for this via density + voices inspection.
3. Tradetron/AlgoTest/Streak chatter counts are too thin to judge sentiment — their audiences live in venues Beacon doesn't collect yet (Telegram/Discord/own forums).
4. "r/algorading" (in our source list and the original brief) **does not exist** — 404s everywhere; almost certainly a typo for r/algotrading. Source-list cleanup candidate.
5. Web-audit numbers (stars, member counts, pricing) are 2026-08-27 snapshots; pricing pages behind logins are marked unverified in the agent evidence.

## Five next actions (smallest first)

1. Add project URLs to the PyPI package + decide the NubraOSS public/private wording (5 min + 1 decision).
2. Resolve the AlgoTest/Tradetron listing discrepancy (one email each).
3. Publish API pricing, rate limits, and a changelog — the three cheapest credibility artifacts every incumbent already has.
4. Assign an engineer to own the OpenAlgo Nubra connector + disclosed Discord presence.
5. Decide the two strategic gaps: TradingView native panel and an MCP/agent surface — both sit in G3's growth path.
