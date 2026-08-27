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

Sector context first: SEBI's retail-algo framework (live Apr 1, 2026) forced daily 2FA, static-IP whitelisting, and 10 orders/sec caps on every broker ([Zerodha's explainer](https://zerodha.com/z-connect/general/a-comprehensive-overview-of-nses-circular-on-the-new-retail-algo-trading-framework)). Auth pain and static IPs are industry constants now — the differentiator is who absorbed them gracefully.

## A1. Broker API scorecard — with Nubra in the frame

**How to read the grades.** Each row is graded against what the best-in-market does, from an API trader's chair:

- **Docs**: A = public without login, versioned, dated changelog, published rate-limit tables, precise reference (Kite v3 is the anchor). C = public but JS-only/stale/forum-is-the-real-docs. F = login-walled.
- **Getting started**: A = self-serve app creation, no funded account needed to experiment, minutes to first authenticated call. F = approval waits + funded account + undocumented flow.
- **Pricing**: not a grade — the published number itself. "n/p" = not published anywhere public.
- **Data**: A = deep order-book depth + Greeks + dedicated order-update socket + long history, unpaywalled. C = 5-level depth, no Greeks, short windows.
- **SDKs + ecosystem**: A = several actively-maintained official languages + present on the third-party platforms traders use (OpenAlgo/AlgoTest/Tradetron/TradingView).
- **Sandbox**: A = full test environment (orders AND market data). B = orders-only. F = none — you test with real money.
- **Support/community**: A = staffed public dev forum answering daily. F = no published channel at all.
- **Reliability '25–26**: the public incident record. "n/a" = too young / no public record (which is itself an adoption objection for G3 traders).

| Dimension | **Nubra** | Zerodha | Dhan | Upstox | Angel One | Fyers | Groww |
|---|---|---|---|---|---|---|---|
| Docs | **B+** public+clean+AI assistant; no public changelog or rate-limit table ([docs](https://nubra.io/products/api/docs/index.html)) | **A** ([v3 + limits](https://kite.trade/docs/connect/v3/exceptions/)) | A- ([versioned releases](https://dhanhq.co/docs/v2/releases/)) | A- ([monthly announcements](https://upstox.com/developer/api-documentation/announcements/)) | C+ (JS-only SPA; truth lives in forum threads) | B- (JS-rendered; token validity undocumented) | B+ ([dated changelog](https://groww.in/trade-api/docs/curl/changelog)) |
| Getting started | **B+** designed-in [automated TOTP](https://nubra.io/products/api/docs/index.html) + UAT to experiment in; but issuance flow/prereqs not publicly documented | B- (daily browser login, [no retail refresh token](https://kite.trade/docs/connect/v3/user/)) | B (24h tokens since v2.4) | B (daily 3:30 AM expiry; [1-yr read-only token](https://upstox.com/developer/api-documentation/analytics-token/) mitigates) | B+ (lowest signup friction) | C+ (funded account, ~24h app approval, refresh tokens killed Apr-26) | B- (paid sub to start; TOTP flow has no expiry) |
| API+data price | **n/p — undisclosed** ([pricing page has no API line](https://nubra.io/pricing)) | ₹0 exec / [₹500-mo data](https://zerodha.com/products/api/) | ₹0 exec / [₹499-mo data](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/) | [₹0 all](https://upstox.com/trading-api/) | [₹0 all](https://www.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi) | [₹0 all](https://support.fyers.in/portal/en/kb/articles/does-fyers-charge-any-subscription-fees-for-trading-api) | [₹499-mo "early bird" vs ₹2,000 list](https://groww.in/trade-api) |
| Data | **A-** 20-depth standard + live AND historical Greeks/IV/OI + order socket (grounding; instrument caps unpublished) | B (5-depth, no Greeks) | **A** ([20/200-depth](https://dhanhq.co/docs/v2/full-market-depth/), live Greeks) | A- (30-depth [paywalled behind Plus](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/)) | B- (20-depth [removed Apr-25](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025)) | B+ ([50-depth TBT, 15 symbols](https://www.marketcalls.in/python/a-simple-guide-to-using-fyers-tbt-feed-via-websocket-with-protobuf-python-tutorial.html)) | B (5-depth, live Greeks) |
| SDKs + ecosystem | **C** Python-only, [1★ GitHub](https://github.com/NubraAPI), on OpenAlgo only | **A** (8 langs, [1.3k★](https://github.com/zerodha/pykiteconnect), Streak+Sensibull) | A- (TV native both ways) | A- (6 langs, MCP leader) | B- ([SDK 15 months stale](https://github.com/orgs/angel-one/repositories)) | B+ (5 active langs, TV full) | C+ (Python only) |
| Sandbox | **A** full UAT environment ([docs](https://nubra.io/products/api/docs/rest-api/UATEnvironment.html)) — best in cohort | C ([half-launched](https://kite.trade/docs/connect/v3/sandbox/); own FAQ denies it exists) | B ([orders, no data feed](https://docs.openalgo.in/connect-brokers/brokers/dhan-sandbox)) | B- (payload-validation only) | **F** none | **F** none | **F** none |
| Support/community | **D** AI assistant, but no forum, no community channel, no published dev support surface | **A** ([15.3K-discussion forum](https://kite.trade/forum/), staff daily) | A- ([MadeForTrade](https://madefortrade.in/) + apihelp@) | B+ ([staffed Discourse](https://community.upstox.com/)) | D (spam, absent admins) | C+ (link-rotted forum — 4/4 threads fetched were dead) | **F** (nothing published) |
| Reliability '25–26 | **n/a** — no public record; unproven | C ([Feb-26 outage](https://www.niftytrader.in/markets/zerodha-kite-outage-traders/)) | B- ([unresolved data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053)) | C+ ([websocket-failure pattern, 7+ threads](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420)) | C- ([Mar-26 outage, no statement](https://www.businessupturn.com/finance/stock-market/angel-one-down-today-traders-say-they-cant-exit-positions-amid-platform-glitch/)) | C- ([21+ outages since Mar-25](https://statusgator.com/services/fyers/trading-via-apis)) | B (young; [SEBI-settled 2024 glitch](https://www.business-standard.com/markets/news/groww-invest-pays-over-34-lakh-to-settle-sebi-case-linked-to-tech-glitch-125051301434_1.html)) |

**Nubra's row in one line**: product-grade cells (sandbox A, data A-, auth B+) that no incumbent matches, dragged down by the distribution cells (ecosystem C, community D, pricing n/p, reliability n/a) — all four of which are fixable without touching the product.

Second tier, one line each: **Kotak Neo** [₹0/order API brokerage since Nov 2025](https://www.kotakneo.com/support/is-neo-trade-api-free-of-cost/) — the price floor · **Flattrade** [free API + ₹0 brokerage](https://flattrade.in/algotrading/) · **Shoonya** free full stack, community-grade polish · **ICICI Breeze** free but [most restrictive rules](https://api.icicidirect.com/breezeapi/documents/index.html) (no market orders, NSE only) · **Pocketful** ₹0 APIs but [historical data "coming soon"](https://api.pocketful.in/) · **5paisa** free + [docs-trained AI assistant](https://www.5paisa.com/blog/5paisa-developer-apis-xstream-ai-assistant) · **Alice Blue / Paytm Money / IIFL** quiet or churning.

## A2. Competitor deep dives — what they sell vs what traders say

Chatter numbers below are lens-corpus counts (Jun–Aug 2026): total mentions / friction items / showcase items. Cross-cutting fact framing all of them (observed): **cost/pricing is the #1 friction theme for every large broker; reliability #2.**

### Zerodha (Kite Connect + Streak + Sensibull) — 440 mentions / 178 friction / 56 showcase

**Sells**: the whole stack. Free personal APIs + [₹500/mo bundled data](https://zerodha.com/products/api/) (the old ₹2,000+₹2,000 is gone), 8 official SDK languages, [Streak](https://tradersunited.org/blog/zerodha-streak-review-algo-trading) and [Sensibull free for Zerodha users](https://sensibull.freshdesk.com/support/solutions/articles/43000586718-what-are-the-charges-of-sensibull-), and the strongest community asset in the market: a [15.3K-discussion forum with staff answering daily](https://kite.trade/forum/) and the [most-starred broker SDK by ~7x](https://github.com/zerodha/pykiteconnect).
**Cracks**: 5-level depth max, no Greeks anywhere, quote polling capped at 1/sec with [spurious-429 pain](https://kite.trade/forum/discussion/15701/clarity-on-api-rate-limit), daily browser login with refresh tokens reserved for "approved platforms" ([auth docs](https://kite.trade/docs/connect/v3/user/)), a [sandbox half-launched so quietly its own FAQ denies it exists](https://kite.trade/docs/connect/v3/sandbox/), no TradingView execution ([stated no plans](https://tradingqna.com/t/zerodhas-integration-with-tradingview/177136)), and a [recurring outage pattern (Feb 2026)](https://www.niftytrader.in/markets/zerodha-kite-outage-traders/).
**Chatter agrees**: most-complained-about broker in the lens, and pricing (44 items) is the top gripe — the ₹500 bundle didn't kill the perception. Streak's one lens signal is negative ([UX degradation video](https://www.youtube.com/watch?v=G6saugMSM1Q&lc=UgxdYSIDhtsMTujUNGJ4AaABAg)).
**The juice**: Zerodha's moat is community and trust, not capability. Its capability row is beatable today; its forum + SDK gravity took a decade.

### Dhan (DhanHQ v2) — 244 / 90 / 21 — the sharpest direct rival, confirmed

**Sells**: the deepest data product in market — [20-level and 200-level depth feeds](https://dhanhq.co/docs/v2/full-market-depth/), [option chain with full Greeks](https://dhanhq.co/docs/v2/option-chain/), dedicated order socket, 5×5,000-instrument websockets; **TradingView both ways** ([native panel + tv.dhan.co](https://dhan.co/connect-to-tradingview/)) plus [first-party TV-alert webhooks that execute orders](https://web.dhan.co/assets/Pdf/Webhooks.pdf); an [MCP server + agent skills](https://docs.dhanhq.co/); an active [forum](https://madefortrade.in/) and a real [sandbox (orders, no data)](https://docs.openalgo.in/connect-brokers/brokers/dhan-sandbox). Trading APIs free, [data ₹499/mo](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/).
**Cracks**: the famous long-lived token is dead — 24h tokens + daily session since v2.4 ([release notes](https://dhanhq.co/docs/v2/releases/), [150+-reply churn thread](https://madefortrade.in/t/update-for-api-traders-new-changes-in-dhanhq-api-authentication-process-and-updates/56286)); Apr-2026 SEBI go-live was rough (market orders stuck pending); and a credible, staff-acknowledged, **unresolved** ["DO NOT buy Dhan API for Data" thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053) — repeating dates, a missing trading day in historical data.
**Chatter agrees**: #2 mindshare, out-mentions Nubra ~8x, runs a visible support content machine (DhanCares/DhanHQ handles are top lens voices). Its friction profile matches ours: pricing 22, order primitives 13, reliability 11.
**The juice**: Dhan wins today on data ceiling + integrations + distribution. It is beatable on auth ergonomics, sandbox completeness, and — given that unresolved thread — **historical-data trust**, which is precisely where Nubra's historical Greeks/IV story lands.

### Upstox (Open API) — 209 / 95 / 17 — highest friction ratio in the lens (45%)

**Sells**: everything free ([₹0 API + data, ₹10/order promo](https://upstox.com/trading-api/)), the most active changelog of any broker ([monthly dated announcements](https://upstox.com/developer/api-documentation/announcements/)), Greeks in feed + option chain [with a PoP field](https://upstox.com/developer/api-documentation/get-pc-option-chain/), 30-level depth (paywalled behind Plus, 50 instruments), and the **clearest AI-agent lead**: [official MCP](https://upstox.com/developer/api-documentation/mcp-integration/), [Agent Skills that place orders](https://upstox.com/developer/api-documentation/agent-skills/), a [Claude plugin marketplace](https://upstox.com/developer/api-documentation/announcements/plugin-marketplace-launch/), and a [1-year read-only Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/).
**Cracks**: **websocket reliability is a pattern, not an anecdote** — 7+ independent 2026 threads on silent drops, stale LTP, backwards timestamps ([one](https://community.upstox.com/t/the-websocket-connection-dropped/16056), [two](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420), [three](https://community.upstox.com/t/unreliable-websocket-data-feed-connection/15830)); a [critical token-expiry incident closed without root cause](https://community.upstox.com/t/critical-access-token-expiring-every-90-minutes-during-market-hours-disaster-risk-for-live-algo-trading/16050); ₹10 pricing is a promo already extended three times; best depth paywalled; unexplained v2/v3 coexistence.
**Chatter agrees loudly**: highest friction share of any broker (pricing 33, **reliability 24** — the worst reliability count in the lens), and its own forum is where our G2 first-timers congregate ([the 403 websocket outage thread](https://community.upstox.com/t/websocket-market-feed-request-return-403-with-error-code-1006/16193) is a top G2 exhibit).
**The juice**: Upstox proves free pricing doesn't buy loyalty when the feed drops. Reliability + a real sandbox is the wedge against it; its MCP lead is the thing to copy.

### Fyers (API v3) — 96 / 29 / 19

**Sells**: [industry-first 50-level tick-by-tick depth](https://www.marketcalls.in/python/a-simple-guide-to-using-fyers-tbt-feed-via-websocket-with-protobuf-python-tutorial.html) (15 symbols, NFO), **full TradingView broker incl. options** ([tradingview.com/broker/FYERS](https://www.tradingview.com/broker/FYERS/)), free API/data, actively-shipped SDKs ([Python v3.1.16, Aug 2026](https://pypi.org/project/fyers-apiv3/)).
**Cracks**: [21+ tracked API outages since Mar 2025](https://statusgator.com/services/fyers/trading-via-apis); refresh tokens discontinued and the API Bridge product killed in the Apr-2026 SEBI upheaval — a platform operator [publicly quit over it](https://www.linkedin.com/posts/kirubakaran-rajendran-90745a9b_fyers-just-disabled-order-placement-for-all-activity-7444217244890546176-6yPl); funded account + ~24h approval to even start; docs don't state token validity; severe forum link rot (4/4 threads fetched were dead); no sandbox; Greeks in-app only, not in the API.
**Chatter agrees**: balanced mention profile, but its friction items are exactly reliability + onboarding + data-quality ([missing candles blocking backtests](https://www.youtube.com/watch?v=RuWzuzDJbOo)).
**The juice**: Fyers is the cautionary tale for capability-without-stability. Its TradingView-options integration is the one asset to envy.

### Angel One (SmartAPI) — 95 / 28 / 14 — the weakest deep-audit incumbent

**Sells**: completely free incl. historical, [lowest signup friction in the cohort](https://www.angelone.in/knowledge-center/smartapi/how-to-generate-smartapi-key-and-install-python-on-your-machine), an [Option Greeks endpoint](https://smartapi.angelone.in/smartapi/forum/topic/4254/announcing-option-greeks-api-for-smartapi-users), [TradingView native panel since Jul 2026](https://www.tradingview.com/blog/en/angel-one-now-on-tradingview-57852/), up to 5 static IPs per key.
**Cracks**: docs are a JS-only SPA whose real truth lives in forum threads; [Python SDK ~15 months stale, Go/PHP/.NET archived](https://github.com/orgs/angel-one/repositories) while marketing still says 8 languages; **capability removals** ([20-depth withdrawn Apr 2025](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025)); forum with visible spam and "the admins here… do not exist" complaints; no sandbox (staff told a paper-trading asker to keep their own logs); a [~30-min Mar-2026 outage with no official statement](https://www.businessupturn.com/finance/stock-market/angel-one-down-today-traders-say-they-cant-exit-positions-amid-platform-glitch/); throttling below stated limits reported.
**Chatter agrees**: mid-pack mentions, friction on pricing + reliability, [corporate-action data gaps](https://reddit.com/r/IndiaAlgoTrading/comments/1vixctp/cleaned_stock_data_availability/).
**The juice**: a distribution giant coasting on free — the DX is decaying (stale SDKs, removed features). Every dimension except price and reach is winnable against it today.

### Groww (Trade API, 2025 entrant) — 75 / 21 / 5 — the disruptor-shaped rival

**Sells**: distribution (India's largest broker by users) + two genuinely novel first-party moves: **[Groww Cloud](https://groww.in/updates/groww-cloud-algo-trading)** — hosted strategy execution with *no external VPS and no IP whitelisting* — and [Groww MCP](https://groww.in/updates/groww-mcp). Clean docs with a [dated changelog](https://groww.in/trade-api/docs/curl/changelog), option chain with full Greeks, a no-expiry TOTP auth flow.
**Cracks**: [₹499/mo labeled "early bird" against a ₹2,000 list price](https://groww.in/trade-api) — pricing risk is printed on the page; 5-depth websocket; DAY-only order validity, no IOC ([annexures](https://groww.in/trade-api/docs/curl/annexures)); tight historical windows; Python-only SDK and an [empty-shell GitHub org](https://github.com/Groww-OSS/trading-api); **no sandbox, no dev forum, no published support channel at all**.
**Chatter agrees**: 75 mentions but only 5 showcases — a big broker with near-zero API community (inferred from the mention mix: mostly cross-broker comparisons).
**The juice**: weak DX today, but Groww Cloud attacks deployment friction (136 lens items) at the root, from a giant funnel. Watch it; don't dismiss it on today's DX.

### The non-broker layers

- **AlgoTest** (21 lens mentions — too thin to judge from chatter; its audience lives in its [17.5k-member Telegram](https://t.me/AlgoTest_in)): [7.5+ yrs backtest data, permanent free tier](https://docs.algotest.in/product-blogs/detailed-pricing-algotest/), [45-broker directory](https://docs.algotest.in/category/broker-setup/), honest slippage education, and the **[public Broker Speedtest leaderboard](https://algotest.in/blog/broker-speedtest-algotest/) — API latency is now third-party-benchmarked whether a broker opts in or not**. Nubra is absent from its list (see A4-flags).
- **Tradetron** (23 — too thin): scale claims ([100+ brokers, 405k signups](https://tradetron.tech/)) but cost stacking (plan + [₹20/backtest](https://tradetron.tech/pages/backtest) + marketplace + profit share), execution-failure forum categories, and a [marketplace-as-unregistered-advice controversy](https://www.caclubindia.com/forum/retail-algo-trading-scam-details-578275.asp?offset=2). Integration target, not a model.
- **OpenAlgo** (103 / 26 / **50** — a community darling in our lens): [2,520★/1,199 forks, pushed same-day](https://github.com/marketcalls/openalgo), [35 brokers incl. Nubra](https://docs.openalgo.in/connect-brokers/brokers), 3,000+ Discord, AGPL with [a brokers-explainer](https://www.marketcalls.in/openalgo/why-openalgo-is-licensed-under-agpl-3-0-and-what-it-means-for-brokers-and-traders.html). The credibility layer; being well-maintained there IS distribution.
- **TradingView (+Pine)** (146 / 29 / **52** — the most-loved layer in the lens): native execution is table stakes now — Dhan, Fyers (options), Paytm, Alice Blue, Motilal, [Angel One Jul 2026](https://www.tradingview.com/blog/en/angel-one-now-on-tradingview-57852/). Zerodha still refuses. Nubra has [a DIY webhook guide](https://nubra.io/products/api/blogs/tradingview-to-nubra-webhook-guide), no panel.
- **SpotGamma / MenthorQ**: $89–$349/mo dealer-gamma analytics ([SpotGamma](https://spotgamma.com/subscribe/), [MenthorQ](https://menthorq.com/pricing/)). **No India equivalent at their maturity** — only indie dashboards ([StockMojo GEX](https://stockmojo.in/gamma-exposure/nifty), Vtrender, OptionsFlow.in); Sensibull/Quantsapp stop at OI/Greeks. Open niche relevant to the H4 fragility thesis. (Inference: NSE flow is retail-vs-prop, not dealer-intermediated — the framing transfers imperfectly.)

## A3. Head-to-head: Nubra vs each broker

Per broker: where Nubra wins **today** (observed on their public surfaces), where they win, and what they have that Nubra has no stated equivalent for.

**vs Zerodha**
- Nubra wins: full UAT (their sandbox is a half-launch [their own FAQ denies](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs)) · automated TOTP vs daily browser login · 20-depth vs 5 · historical AND live Greeks vs none · hedge-benefit margin API vs basket-calc only.
- They win: community (15.3K-forum, 8 SDK languages, 1.3k★) · published pricing + rate limits · a decade of trust.
- They have, Nubra doesn't: a free no-code layer (Streak) and bundled options analytics (Sensibull) — the acquisition funnel that feeds their API.

**vs Dhan**
- Nubra wins: UAT with data (their sandbox has no feed) · auth stability story (their 24h-token churn burned users publicly) · **historical Greeks/IV** (theirs are live-only) · historical-data *trust* (their unresolved data-quality thread is an open wound).
- They win: raw depth ceiling (200-level) · distribution (~8x lens mindshare) · staffed forum + support content machine.
- They have, Nubra doesn't: native TradingView both ways · first-party TV-alert webhooks · MCP server + agent skills.

**vs Upstox**
- Nubra wins: full UAT vs payload-only sandbox · 20-depth standard vs 30-depth paywalled behind Plus · historical Greeks · the reliability *opportunity* (their websocket failure pattern is the loudest in the lens — but note Nubra's own record is unproven publicly, so this is a wedge to earn, not claim).
- They win: published free pricing · changelog cadence (best in market) · 6 SDK languages · the 1-yr read-only Analytics Token.
- They have, Nubra doesn't: MCP + Agent Skills + Claude plugin marketplace — the deepest AI-agent surface any Indian broker ships.

**vs Angel One**
- Nubra wins: docs (theirs is a JS shell; truth lives in forum threads) · sandbox (they have none) · 20-depth (they *removed* theirs) · SDK freshness (theirs 15 months stale) · support surface quality.
- They win: everything-free published pricing · lowest signup friction · sheer distribution · TradingView native panel.
- They have, Nubra doesn't: the TradingView panel. Otherwise this is the incumbent Nubra can out-execute on every DX dimension today.

**vs Fyers**
- Nubra wins: UAT (none there; testing = real money) · auth (their refresh tokens died Apr-26) · docs discoverability · stability narrative (21+ outages tracked).
- They win: 50-level TBT depth (15 symbols) · full TradingView incl. options · 5 actively-shipped SDK languages.
- They have, Nubra doesn't: the TradingView options integration — the single asset worth envying there.

**vs Groww**
- Nubra wins: sandbox (none) · support (no channel published at all) · depth (20 vs 5) · docs depth for builders · order flexibility (they're DAY-only, no IOC).
- They win: distribution (largest funnel in India) · published (if "early-bird") pricing · no-expiry TOTP flow already shipped.
- They have, Nubra doesn't: **Groww Cloud** (hosted algos — no VPS, no static-IP burden; attacks deployment friction at the root) and MCP.

**Pattern across all six (inferred from the observed rows):** Nubra's wins cluster exactly on the market's measured friction themes — auth, testing, data depth/trust (G2's 41%-friction wall and G3's infrastructure pain). Its losses cluster in *distribution artifacts* — community, pricing transparency, integrations, track record — every one buildable without touching the product. And the no-equivalent column converges on two strategic bets, both sitting in G3's growth path: **TradingView execution** and **an MCP/agent + cloud-hosting surface**. Cheap credibility artifacts every competitor already publishes and Nubra doesn't: rate-limit tables, a changelog, API pricing.

## A4. Housekeeping flags found during the audit (internal)

1. **API pricing is publicly undisclosed** ([no API line on pricing](https://nubra.io/pricing)); third parties [explicitly flag it](https://www.multibagg.ai/market-pulse/articles/zerodha-nubra-dhan-api-comparison-cmp5l0ayn000ct70j0frlhjln). Since pricing is the market's #1 friction theme, silence reads as risk to exactly the audience being courted.
2. **AlgoTest/Tradetron listing discrepancy**: [Nubra's FAQ claims both](https://nubra.io/products/api/docs/faq/integrations/index.html), but [AlgoTest's 45-broker directory doesn't list Nubra](https://docs.algotest.in/category/broker-setup/) and Tradetron's public pages don't either. A verifying trader hits a dead end.
3. **"NubraOSS" is not publicly findable** — github.com/nubraoss 404s. Our grounding doc lists it as live; either it ships publicly or the grounding wording should change.
4. **PyPI package (`nubra-sdk`, [v0.5.1, actively released](https://pypi.org/pypi/nubra-sdk/json)) has no project URLs** back to docs/GitHub — a 5-minute fix that helps every pip-install discovery.

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
