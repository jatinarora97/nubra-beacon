# Finding and targeting API traders — market research, 2026-08-27

**What this is.** Three questions, answered with two evidence bases: (1) Beacon's corpus — ~112.6k items Jun–Aug 2026 (Aug-27 prod snapshot, reddit outage backfilled), of which 5,242 classified API-trader-relevant ("lens items"); (2) live web audits run 2026-08-27 (docs portals, pricing pages, GitHub API, forum stats, t.me previews). Every claim carries a link. **Observed** = counted in data or fetched from a page. **Inferred** = our reading, labeled as such.

---

## The 10-second version

1. **Where they are**: r/IndiaAlgoTrading is the single best venue (568 lens items at 38% API-trader density — ~10x denser than the big generalist subs; [21k members growing ~200%/yr](https://gummysearch.com/r/IndiaAlgoTrading/)). OpenAlgo (GitHub+Discord) is the densest developer pool — and Nubra is already on its broker list. Broker-owned forums are where first-time API users concentrate — and Nubra doesn't have one.
2. **The #1 complaint against every incumbent is API/data pricing** — and Nubra's API pricing is publicly undisclosed. That's a free positioning win being left on the table.
3. **Nubra's owned surface is good** (public docs, PyPI SDK, UAT env, tutorials); **its third-party surface is near-zero**: 0 TradingQnA posts, ~0 discoverable Reddit threads, 1 GitHub star, absent from AlgoTest/Tradetron's own broker lists, no Chittorgarh page. Dhan out-mentions Nubra ~8–11x in the corpus.
4. **The incumbents' universal weak spots — no test env (3 of 6), daily-token auth pain, websocket reliability, paywalled/removed depth — are exactly what Nubra's stack already attacks.** The story exists; the distribution doesn't.
5. **Three segments, three doors**: explorers (18%) live on YouTube/generalist subs and ask learning questions; first-timers (13%) over-index on broker forums and hit auth/data-cost walls; the 69% already building live in r/IndiaAlgoTrading + GitHub and respond to proof (latency benchmarks, live P&L, integrations), not ads.

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
| Docs | **A-** public+clean+AI assistant+[published rate limits](https://nubra.io/products/api/docs/python-sdk-v3/RateLimits.html) (10/sec prod, 100/sec UAT, 60/min historical); no dated changelog | **A** ([v3 + limits](https://kite.trade/docs/connect/v3/exceptions/)) | A- ([versioned releases](https://dhanhq.co/docs/v2/releases/)) | A- ([monthly announcements](https://upstox.com/developer/api-documentation/announcements/)) | C+ (JS-only SPA; truth lives in forum threads) | B- (JS-rendered; token validity undocumented) | B+ ([dated changelog](https://groww.in/trade-api/docs/curl/changelog)) |
| Getting started | **B+** designed-in [automated TOTP](https://nubra.io/products/api/docs/index.html) + UAT to experiment in; but issuance flow/prereqs not publicly documented | B- (daily browser login, [no retail refresh token](https://kite.trade/docs/connect/v3/user/)) | B (24h tokens since v2.4) | B (daily 3:30 AM expiry; [1-yr read-only token](https://upstox.com/developer/api-documentation/analytics-token/) mitigates) | B+ (lowest signup friction) | C+ (funded account, ~24h app approval, refresh tokens killed Apr-26) | B- (paid sub to start; TOTP flow has no expiry) |
| API+data price | **n/p — undisclosed** ([pricing page has no API line](https://nubra.io/pricing)) | ₹0 exec / [₹500-mo data](https://zerodha.com/products/api/) | ₹0 exec / [₹499-mo data](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/) | [₹0 all](https://upstox.com/trading-api/) | [₹0 all](https://www.angelone.in/knowledge-center/smartapi/detailed-introduction-to-smartapi) | [₹0 all](https://support.fyers.in/portal/en/kb/articles/does-fyers-charge-any-subscription-fees-for-trading-api) | [₹499-mo "early bird" vs ₹2,000 list](https://groww.in/trade-api) |
| Data | **A-** 20-depth standard + live AND historical Greeks/IV/OI + order socket (grounding; instrument caps unpublished) | B (5-depth, no Greeks) | **A** ([20/200-depth](https://dhanhq.co/docs/v2/full-market-depth/), live Greeks) | A- (30-depth [paywalled behind Plus](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/)) | B- (20-depth [removed Apr-25](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025)) | B+ ([50-depth TBT, 15 symbols](https://www.marketcalls.in/python/a-simple-guide-to-using-fyers-tbt-feed-via-websocket-with-protobuf-python-tutorial.html)) | B (5-depth, live Greeks) |
| SDKs + ecosystem | **C** Python-only, [1★ GitHub](https://github.com/NubraAPI), on OpenAlgo only | **A** (8 langs, [1.3k★](https://github.com/zerodha/pykiteconnect), Streak+Sensibull) | A- (TV native both ways) | A- (6 langs, MCP leader) | B- ([SDK 15 months stale](https://github.com/orgs/angel-one/repositories)) | B+ (5 active langs, TV full) | C+ (Python only) |
| Sandbox | **A** full UAT environment ([docs](https://nubra.io/products/api/docs/rest-api/UATEnvironment.html)) — best in cohort | C ([half-launched](https://kite.trade/docs/connect/v3/sandbox/); own FAQ denies it exists) | B ([orders, no data feed](https://docs.openalgo.in/connect-brokers/brokers/dhan-sandbox)) | B- (payload-validation only) | **F** none | **F** none | **F** none |
| Support/community | **D** AI assistant, but no forum, no community channel, no published dev support surface | **A** ([15.3K-discussion forum](https://kite.trade/forum/), staff daily) | A- ([MadeForTrade](https://madefortrade.in/) + apihelp@) | B+ ([staffed Discourse](https://community.upstox.com/)) | D (spam, absent admins) | C+ (link-rotted forum — 4/4 threads fetched were dead) | **F** (nothing published) |
| Reliability '25–26 | **n/a** — no public record; unproven | C ([Feb-26 outage](https://www.niftytrader.in/markets/zerodha-kite-outage-traders/)) | B- ([unresolved data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053)) | C+ ([websocket-failure pattern, 7+ threads](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420)) | C- ([Mar-26 outage, no statement](https://www.businessupturn.com/finance/stock-market/angel-one-down-today-traders-say-they-cant-exit-positions-amid-platform-glitch/)) | C- ([21+ outages since Mar-25](https://statusgator.com/services/fyers/trading-via-apis)) | B (young; [SEBI-settled 2024 glitch](https://www.business-standard.com/markets/news/groww-invest-pays-over-34-lakh-to-settle-sebi-case-linked-to-tech-glitch-125051301434_1.html)) |

**Nubra's row in one line**: product-grade cells (sandbox A, data A-, auth B+) that no incumbent matches, dragged down by the distribution cells (ecosystem C, community D, pricing n/p, reliability n/a) — all four of which are fixable without touching the product.

Second tier, one line each: **Kotak Neo** [₹0/order API brokerage since Nov 2025](https://www.kotakneo.com/support/is-neo-trade-api-free-of-cost/) — the price floor · **Flattrade** [free API + ₹0 brokerage](https://flattrade.in/algotrading/) · **Shoonya** free full stack, community-grade polish · **ICICI Breeze** free but [most restrictive rules](https://api.icicidirect.com/breezeapi/documents/index.html) (no market orders, NSE only) · **Pocketful** ₹0 APIs but [historical data "coming soon"](https://api.pocketful.in/) · **5paisa** free + [docs-trained AI assistant](https://www.5paisa.com/blog/5paisa-developer-apis-xstream-ai-assistant) · **Alice Blue / Paytm Money / IIFL** quiet or churning.

## A2. Head-to-head tables — every player vs Nubra

One table per player: the dimensions that decide adoption, them vs Nubra, chatter counts from the lens corpus (mentions / friction / showcase), verdict at the end. Nubra pricing is "n/p" (not published) throughout — see A4.

### Zerodha — 440 mentions / 178 friction / 56 showcase

| Dimension | Zerodha | Nubra |
|---|---|---|
| Data | 5-depth max, no Greeks, [quotes 1/sec](https://kite.trade/docs/connect/v3/exceptions/) | 20-depth standard; live + historical Greeks/IV/OI |
| Auth | Daily browser login, [no retail refresh token](https://kite.trade/docs/connect/v3/user/) | Automated TOTP, designed in |
| Testing | [Half-launched sandbox](https://kite.trade/docs/connect/v3/sandbox/) its [own FAQ denies exists](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs) | Full UAT env |
| Pricing | Published: [₹0 personal + ₹500/mo data](https://zerodha.com/products/api/) | n/p |
| SDKs + integrations | 8 languages, [1.3k★ SDK](https://github.com/zerodha/pykiteconnect); Streak + Sensibull free; [no TradingView execution](https://tradingqna.com/t/zerodhas-integration-with-tradingview/177136) | Python only, 1★; OpenAlgo only |
| Community | [15.3K-discussion staffed forum](https://kite.trade/forum/) | None |
| Reliability | Decade of trust; [recurring outages (Feb-26)](https://www.niftytrader.in/markets/zerodha-kite-outage-traders/) | No public record |
| Chatter says | Most-complained-about API in the lens; **#1 gripe = pricing (44 items)**; Streak's one signal is [negative](https://www.youtube.com/watch?v=G6saugMSM1Q&lc=UgxdYSIDhtsMTujUNGJ4AaABAg) | 31 mentions total |

**Verdict: their moat is community + trust, not capability. Nubra out-specs them on data/auth/testing today — and is invisible where their decade of forum gravity lives.**

### Dhan — 244 / 90 / 21 — the sharpest direct rival

| Dimension | Dhan | Nubra |
|---|---|---|
| Data | [20/200-depth](https://dhanhq.co/docs/v2/full-market-depth/) + live Greeks, behind [₹499/mo data plan](https://dhan.co/support/platforms/dhanhq-api/how-does-the-dhanhq-data-api-subscription-work/); **[unresolved historical-data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053)** | 20-depth standard; live + **historical** Greeks |
| Auth | Long-lived token killed → 24h tokens ([150+-reply churn thread](https://madefortrade.in/t/update-for-api-traders-new-changes-in-dhanhq-api-authentication-process-and-updates/56286)) | Automated TOTP |
| Testing | [Sandbox: orders only, no data feed](https://docs.openalgo.in/connect-brokers/brokers/dhan-sandbox) | Full UAT |
| Pricing | Published: ₹0 trading + ₹499/mo data | n/p |
| Integrations | [TradingView native both ways](https://dhan.co/connect-to-tradingview/) + [first-party TV webhooks](https://web.dhan.co/assets/Pdf/Webhooks.pdf) + [MCP/agent skills](https://docs.dhanhq.co/) | DIY webhook guide only |
| Community | [MadeForTrade forum](https://madefortrade.in/) + support content machine (DhanCares/DhanHQ are top lens voices) | None |
| Chatter says | ~8x Nubra's mindshare; friction: pricing 22, order primitives 13, reliability 11 | 31 mentions |

**Verdict: wins on distribution + integrations; beatable on auth, sandbox completeness, and historical-data TRUST — their open wound is exactly where Nubra's historical-Greeks story lands.**

### Upstox — 209 / 95 / 17 — highest friction ratio in the lens (45%)

| Dimension | Upstox | Nubra |
|---|---|---|
| Reliability | **Websocket failure pattern, 7+ threads in 2026** ([drops](https://community.upstox.com/t/the-websocket-connection-dropped/16056), [stale/backwards data](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420)); [token-expiry incident closed without root cause](https://community.upstox.com/t/critical-access-token-expiring-every-90-minutes-during-market-hours-disaster-risk-for-live-algo-trading/16050) | No public record — a wedge to earn, not claim |
| Data | Greeks in feed + [PoP field](https://upstox.com/developer/api-documentation/get-pc-option-chain/); [30-depth paywalled behind Plus, 50 instruments](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/) | 20-depth standard |
| Auth | Daily 3:30 AM expiry; [1-yr read-only Analytics Token](https://upstox.com/developer/api-documentation/analytics-token/) | Automated TOTP; no long-lived-token story |
| Testing | [Payload-validation sandbox only](https://upstox.com/developer/api-documentation/sandbox/) | Full UAT |
| Pricing | Published: [₹0 all + ₹10/order promo](https://upstox.com/trading-api/) — already extended 3x | n/p |
| AI/agents | **Market leader**: [MCP](https://upstox.com/developer/api-documentation/mcp-integration/) + [Agent Skills](https://upstox.com/developer/api-documentation/agent-skills/) + [Claude plugin marketplace](https://upstox.com/developer/api-documentation/announcements/plugin-marketplace-launch/) | Docs AI assistant only |
| Community | [Staffed Discourse](https://community.upstox.com/) — where our G2 first-timers congregate | None |
| Chatter says | Worst reliability count in the lens (24) + pricing 33 | 31 mentions |

**Verdict: proof that free pricing doesn't buy loyalty when the feed drops. Reliability + a real sandbox is the wedge; their MCP surface is the thing to copy.**

### Angel One — 95 / 28 / 14 — the weakest incumbent DX

| Dimension | Angel One | Nubra |
|---|---|---|
| Docs | JS-only SPA; the real truth lives in forum threads | Public, clean, [rate limits published](https://nubra.io/products/api/docs/python-sdk-v3/RateLimits.html) |
| Data | **[20-depth removed Apr-25](https://smartapi.angelone.in/smartapi/forum/topic/5217/deprecation-of-20-market-depth-from-websocket-2-0-effective-april-25-2025)**; [Greeks endpoint](https://smartapi.angelone.in/smartapi/forum/topic/4254/announcing-option-greeks-api-for-smartapi-users) | 20-depth standard; historical Greeks |
| SDKs | [Python SDK 15 months stale; Go/PHP/.NET archived](https://github.com/orgs/angel-one/repositories) | Python actively released ([PyPI v0.5.1, Aug-26](https://pypi.org/pypi/nubra-sdk/json)) |
| Testing | None — staff told a paper-trading asker to [keep their own logs](https://smartapi.angelbroking.com/topic/1395/how-to-test-paper-trade-my-script) | Full UAT |
| Pricing | Published: all free | n/p |
| Community | Forum with visible spam + "admins do not exist" complaints | None |
| Reliability | [Mar-26 outage, no official statement](https://www.businessupturn.com/finance/stock-market/angel-one-down-today-traders-say-they-cant-exit-positions-amid-platform-glitch/); throttling below stated limits reported | No public record |
| Chatter says | Pricing + reliability friction; [corporate-action data gaps](https://reddit.com/r/IndiaAlgoTrading/comments/1vixctp/cleaned_stock_data_availability/) | 31 mentions |

**Verdict: a distribution giant coasting on free while the DX decays. Winnable on every dimension except price and reach.**

### Fyers — 96 / 29 / 19

| Dimension | Fyers | Nubra |
|---|---|---|
| Data | [50-level TBT — but 15 symbols, NFO only](https://www.marketcalls.in/python/a-simple-guide-to-using-fyers-tbt-feed-via-websocket-with-protobuf-python-tutorial.html); Greeks in-app, not in API | 20-depth across the board; Greeks in API, live + historical |
| Reliability | [21+ tracked API outages since Mar-25](https://statusgator.com/services/fyers/trading-via-apis) | No public record |
| Entry | Funded account + ~24h app approval; refresh tokens killed Apr-26; [a platform operator publicly quit](https://www.linkedin.com/posts/kirubakaran-rajendran-90745a9b_fyers-just-disabled-order-placement-for-all-activity-7444217244890546176-6yPl) | TOTP + UAT: experiment without live money |
| Integrations | **Full TradingView incl. options** ([broker page](https://www.tradingview.com/broker/FYERS/)) — the envy asset | DIY webhook guide only |
| Testing | None | Full UAT |
| Community | Link-rotted forum — 4/4 threads fetched were dead | None |
| Chatter says | Friction = reliability + onboarding + [data gaps blocking backtests](https://www.youtube.com/watch?v=RuWzuzDJbOo) | 31 mentions |

**Verdict: capability without stability — the cautionary tale. Their TradingView-options integration is the one asset worth envying.**

### Groww — 75 / 21 / 5 — the disruptor shape

| Dimension | Groww | Nubra |
|---|---|---|
| Distribution | Largest broker funnel in India | [25k demat accounts (Apr-26 reporting)](https://indianstartupnews.com/funding/zanskar-tech-raises-rs-25-crore-from-blacksoil-to-scale-quant-trading-platform-nubra-11459524) |
| Cloud + agents | **[Groww Cloud](https://groww.in/updates/groww-cloud-algo-trading)** — hosted algos, no VPS, no static-IP burden — + [MCP](https://groww.in/updates/groww-mcp) | No equivalent stated |
| Data + orders | 5-depth; Greeks; [DAY-only validity, no IOC](https://groww.in/trade-api/docs/curl/annexures) | 20-depth; flexi/basket orders + hedge-benefit margin |
| Testing | None | Full UAT |
| Pricing | Published, with risk printed on the page: [₹499/mo "early bird" vs ₹2,000 list](https://groww.in/trade-api) | n/p |
| Support | **Nothing published** — no forum, no email in docs | AI assistant; no forum either |
| Chatter says | 75 mentions but only 5 showcases — no API community yet (inferred from mention mix) | 31 mentions |

**Verdict: weak DX today, but Groww Cloud attacks deployment friction (136 lens items) from a giant funnel. Watch, don't dismiss.**

### AlgoTest — 21 lens mentions (too thin; its audience lives in its own Telegram)

| | |
|---|---|
| What it is | F&O builder + options backtester (YC-backed): [7.5+ yrs data, permanent free tier](https://docs.algotest.in/product-blogs/detailed-pricing-algotest/), honest slippage education |
| Why it matters | [45-broker directory](https://docs.algotest.in/category/broker-setup/) + **[public Broker Speedtest](https://algotest.in/blog/broker-speedtest-algotest/) — API latency is third-party-benchmarked whether a broker opts in or not** + [17.5k-member support Telegram](https://t.me/AlgoTest_in) |
| Weak spots | Backtest-vs-live gripes on its own forum; otherwise a remarkably thin public complaint surface |
| Nubra angle | [Nubra's FAQ claims the integration](https://nubra.io/products/api/docs/faq/integrations/index.html); **AlgoTest's directory doesn't list Nubra** — fix the listing, then engineer for a Speedtest top-3 |

**Verdict: the layer to partner with — and the discrepancy to fix first.**

### Tradetron — 23 lens mentions (too thin)

| | |
|---|---|
| What it is | No-code automation + strategy marketplace ([claims 100+ brokers, 405k signups](https://tradetron.tech/)) |
| Weak spots | Cost stacking (plan + [₹20/backtest](https://tradetron.tech/pages/backtest) + marketplace fees + profit share); execution-failure [forum categories](https://qna.tradetron.tech/t/how-do-i-resolve-error-execution/28); [unregistered-advice controversy](https://www.caclubindia.com/forum/retail-algo-trading-scam-details-578275.asp?offset=2) |
| Nubra angle | FAQ claims integration; not verifiable on Tradetron's public pages — verify + fix |

**Verdict: integration target, not a model to copy.**

### OpenAlgo — 103 / 26 / 50 — the community darling in our lens

| | |
|---|---|
| What it is | Open-source unified API: [2,520★ / 1,199 forks, pushed same-day](https://github.com/marketcalls/openalgo), [35 brokers **including Nubra**](https://docs.openalgo.in/connect-brokers/brokers), 3,000+ Discord |
| Why it matters | The credibility layer for serious Indian API traders; AGPL with [an explainer aimed at brokers](https://www.marketcalls.in/openalgo/why-openalgo-is-licensed-under-agpl-3-0-and-what-it-means-for-brokers-and-traders.html) |
| Nubra angle | Already listed — officially own/maintain the connector, disclosed Discord presence, [FOSS United sponsorship channel](https://fossunited.org/fosshack/2026/partner-projects/openalgo) |

**Verdict: being well-maintained here IS distribution — the cheapest Tier-1 play available.**

### TradingView (+Pine) — 146 / 29 / 52 — the most-loved layer in the lens

| | |
|---|---|
| What it is | Dominant charting/signal layer; native broker execution is now table stakes — Dhan, Fyers (options), Paytm, Alice Blue, Motilal, [Angel One Jul-26](https://www.tradingview.com/blog/en/angel-one-now-on-tradingview-57852/); Zerodha still refuses |
| Nubra angle | [DIY webhook guide](https://nubra.io/products/api/blogs/tradingview-to-nubra-webhook-guide) only; a native panel is a strategic decision — Angel One just showed the path |

**Verdict: not a rival — the top-of-funnel prize.**

### SpotGamma / MenthorQ — the open niche

| | |
|---|---|
| What they are | Dealer-gamma/GEX analytics, [$89–$349/mo](https://spotgamma.com/subscribe/) ([MenthorQ pricing](https://menthorq.com/pricing/)) |
| India status | **No equivalent at their maturity** — indie dashboards only ([StockMojo GEX](https://stockmojo.in/gamma-exposure/nifty), Vtrender); Sensibull/Quantsapp stop at OI/Greeks |
| Nubra angle | Open product niche aligned with the H4 fragility thesis (inference: NSE flow is retail-vs-prop, not dealer-intermediated — the framing transfers imperfectly) |

**Verdict: open niche, no incumbent to displace.**

## A3. The pattern across all head-to-heads

**Nubra's wins cluster on the market's measured friction themes** — auth, testing, data depth/trust (G2's 41%-friction wall, G3's infrastructure pain). **Its losses cluster in distribution artifacts** — community, pricing transparency, integrations, track record — every one buildable without touching the product. The no-equivalent column converges on two strategic bets, both in G3's growth path: **TradingView execution** and **an MCP/agent + cloud-hosting surface**. The two cheap credibility artifacts still unpublished: **API pricing and a dated changelog** (rate limits, contrary to first impressions, [are published](https://nubra.io/products/api/docs/python-sdk-v3/RateLimits.html)).

## A4. Housekeeping flags found during the audit (internal)

1. **API pricing is publicly undisclosed** ([no API line on pricing](https://nubra.io/pricing)); third parties [explicitly flag it](https://www.multibagg.ai/market-pulse/articles/zerodha-nubra-dhan-api-comparison-cmp5l0ayn000ct70j0frlhjln). Since pricing is the market's #1 friction theme, silence reads as risk to exactly the audience being courted.
2. **AlgoTest/Tradetron listing discrepancy**: [Nubra's FAQ claims both](https://nubra.io/products/api/docs/faq/integrations/index.html), but [AlgoTest's 45-broker directory doesn't list Nubra](https://docs.algotest.in/category/broker-setup/) and Tradetron's public pages don't either. A verifying trader hits a dead end.
3. **"NubraOSS" is not publicly findable** — github.com/nubraoss 404s. Our grounding doc lists it as live; either it ships publicly or the grounding wording should change.
4. **PyPI package (`nubra-sdk`, [v0.5.1, actively released](https://pypi.org/pypi/nubra-sdk/json)) has no project URLs** back to docs/GitHub — a 5-minute fix that helps every pip-install discovery.

---

# Part B — Where the API traders are

## B1. Venue map (lens items ÷ venue total = density; observed)

Numbers below are from the Aug-27 snapshot (reddit backfilled; lens = 5,242).

| Venue | Lens items | Density | Verdict |
|---|---|---|---|
| GitHub (all repos) | 307 | **~68%** | Purest habitat, small |
| **r/IndiaAlgoTrading** | **568** | **38%** | **#1 by size AND concentration** — ~10x denser than the big subs; [21k members, ~+200%/yr](https://gummysearch.com/r/IndiaAlgoTrading/) |
| Upstox Community forum | 257 | 26% | First-timers' habitat, broker-owned |
| Zerodha TradingQnA | 239 | 12% | Large + open ([5,061-topic algo category](https://tradingqna.com/categories)) |
| YouTube | 471 | 12% | Tutorial supply; core-algo channels are 3k–56k subs, not the 1M options celebrities |
| Twitter/X | 2,687 | 7% | Biggest raw pool, heavily vendor/bot-diluted (observed in voices analysis) |
| r/IndianStockMarket · r/IndianStreetBets | 244 · 135 | 2–4% | Reach venues, incidental algo content |
| r/IndiaOptionsSelling · r/DalalStreetTalks | 47 · 31 | 11% · 8% | Small but dense |
| Instagram · app reviews | 32 · 56 | ~1% | Not habitats for this segment |

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
| Size | 956 (18%) | 676 (13%) — early first-API split: broker-API-first 32, any-API-first 26, rest unclear (seed rows) | 3,610 (69%) |
| Where | Twitter, YouTube, r/IndianStockMarket, generalist subs | **Broker-owned forums over-index**, YouTube, r/IndiaAlgoTrading | r/IndiaAlgoTrading, **GitHub**, forums, Twitter |
| What they post | 67% guidance-seeking: learning paths, "is my strategy scalable", how to go manual→systematic. Almost nothing about APIs themselves yet | 45% guidance + **41% friction**: API keys, TOTP/static-IP setup, websocket how-tos, "which API is best / has free data" | **50% showcase**: live P&L, automation running, backtest proof; plus VPS/infra, expired-options data, and a fast-growing **AI/MCP/LLM** cluster |
| What converts them (inferred from asks) | Education that meets them pre-API: manual→systematic content, strategy-validation tools, backtesting as the hook (NubraOSS story if it ships publicly) | **Time-to-first-order.** Onboarding guides, UAT sandbox (no funded account to experiment — unlike Fyers), TOTP automation, transparent pricing, responsive forum | Proof, not promises: Speedtest rank, published rate limits, historical-Greeks depth, integrations (OpenAlgo/TradingView/MCP), engineers visible in their venues |
| Concrete play | YouTube tutorial series + Quantra course + quant-fest sponsorship | Broker-forum-grade support surface of our own + "first order on UAT in one sitting" content + r/IndiaAlgoTrading answers | OpenAlgo connector ownership, AlgoTest Speedtest, MCP/agent surface (the one capability gap squarely in this segment's growth path), dev-forum AMAs |

**The consolidated read (inferred, from all observed above):** G2 is the conversion choke point (41% friction) and it congregates on *broker-owned* surfaces — a segment Nubra structurally cannot reach until it has its own forum/support surface. G3 is 68% of the market and runs on proof-artifacts (benchmarks, integrations, showcases); its two live currents — TradingView execution and AI/MCP workflows — are both currently "no Nubra equivalent stated." G1 is cheapest to reach (education scales) but longest to convert.

---

## Caveats

1. Corpus = the Aug-27 prod snapshot including the reddit backfill (9.2k recovered items, ~8.6k created in August). The Aug 10–25 outage window is reconstructed from listing crawls — posts carry original timestamps but comments/engagement are as-of-recovery, and low-ranking gap posts that fell off listings are gone for good.
2. Twitter lens counts measure content *supply* (vendors/bots heavy), not organic demand; venue analysis corrected for this via density + voices inspection.
3. Tradetron/AlgoTest/Streak chatter counts are too thin to judge sentiment — their audiences live in venues Beacon doesn't collect yet (Telegram/Discord/own forums).
4. "r/algorading" (in our source list and the original brief) **does not exist** — 404s everywhere; almost certainly a typo for r/algotrading. Source-list cleanup candidate.
5. Web-audit numbers (stars, member counts, pricing) are 2026-08-27 snapshots; pricing pages behind logins are marked unverified in the agent evidence.

## Five next actions (smallest first)

1. Add project URLs to the PyPI package + decide the NubraOSS public/private wording (5 min + 1 decision).
2. Resolve the AlgoTest/Tradetron listing discrepancy (one email each).
3. Publish API pricing and a dated changelog — the two cheapest credibility artifacts still missing (rate limits are already published; surface them in comparison content).
4. Assign an engineer to own the OpenAlgo Nubra connector + disclosed Discord presence.
5. Decide the two strategic gaps: TradingView native panel and an MCP/agent surface — both sit in G3's growth path.
