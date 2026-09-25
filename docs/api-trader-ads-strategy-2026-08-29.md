# API-trader ad targeting — the playbook (2026-08-29)

**Start here:** publish API pricing, then submit the first 5 creatives (skeletons in §2) for exchange approval — the 7-working-day clock is the critical path. Verification chains, ad-code rules, legal flags, and budget wiring live in the companion doc: `api-trader-ads-compliance-ops-2026-08-29.md`. This doc is only: who to target, with what message, on which platform, backed by what evidence.

Evidence base: our lens corpus (5,242 items of API-trader chatter, Jun–Aug 2026) + live web checks 2026-08-29. Volumes/CPCs for India were not verifiable anywhere — demand columns use hard proxies (our corpus counts, Google autocomplete gl=IN, PyPI downloads, forum sizes), each labeled.

---

## 1. The three audiences

Plain names (previously G1/G2/G3). Sizes = share of our classified corpus.

| Audience | Size | Who they are | Where they are | What moves them |
|---|---|---|---|---|
| **Explorers** | 18% | Want to trade via code, haven't touched an API. Ask learning questions ("how to go from manual to systematic") | YouTube, generalist subs (r/IndianStockMarket), Twitter | Education. Longest to convert — feed the funnel, don't sell |
| **First-timers** | 13% | Setting up their first API. 41% of their posts are friction: tokens, keys, static IP, "which API has free data" | **Broker-owned forums** (Upstox forum = 26% API-trader density), YouTube tutorials, r/IndiaAlgoTrading | Removing setup pain. The conversion choke point |
| **Builders** | 69% | Already running/building algos. Post proof (live P&L, showcases), ask infra questions (VPS, data, expired options) | r/IndiaAlgoTrading (568 lens items), GitHub, forums | Proof, not promises: specs, benchmarks, integrations. Immune to ads that smell like ads |

---

## 2. The five hooks — the messages, and the data behind each

These are the creative angles for every platform. Each is (a) a measured pain in our corpus, (b) something Nubra actually has, (c) sayable under the NSE ad code (which bans algo past-performance/returns claims — so P&L/backtest-result creatives are out; details in the compliance doc).

| # | Hook (headline idea) | Corpus demand (lens items matching the language) | Real thread example | Nubra proof asset |
|---|---|---|---|---|
| 1 | **"Test your algo without real money"** (UAT) | **256** — largest cluster; 119 guidance-seeking, 74 from first-timers. Typical ask: ["how long should I paper trade before going live?"](https://reddit.com/r/IndiaAlgoTrading/comments/1vtk5b8/) | ["realistic paper fills are the bottleneck for NSE F&O entrants"](https://reddit.com/r/IndiaAlgoTrading/comments/1urgx3q/) | Full UAT env — only A-grade sandbox in the market; Angel One staff literally tell users ["keep your own logs"](https://smartapi.angelbroking.com/topic/1395/how-to-test-paper-trade-my-script) |
| 2 | **"Deploy without the static-IP headache"** | **232** — 114 guidance, 62 first-timers (SEBI static-IP + VPS/cloud setup questions) | [SEBI static-IP setup as onboarding friction](https://www.youtube.com/watch?v=m3Hxodja7_0) | Primary + secondary static IP designed in |
| 3 | **"No 6 AM token ritual"** (auth) | **119** — 64 friction; access-token/TOTP/daily-login language | [r/IndiaAlgoTrading TOTP-automation thread — already names Nubra](https://reddit.com/r/IndiaAlgoTrading/comments/1vh3obr/) | Automated TOTP login, officially supported (Kite = daily browser login; Dhan killed its long-lived token) |
| 4 | **"Historical data you can backtest on"** (incl. Greeks) | **145** hist-data + **105** Greeks/depth; 61+49 guidance | [expired-options data asks](https://reddit.com/r/IndiaAlgoTrading/comments/1vixctp/); [broker-streamed Greeks thread evaluating Nubra](https://reddit.com/r/IndiaAlgoTrading/comments/1vbk8sg/) | Historical OHLC+OI+IV+**Greeks** — no competitor documents historical Greeks; Dhan's data trust is [publicly wounded](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053) |
| 5 | **"Transparent API pricing"** | **134** cost-language items; cost_pricing = #1 friction theme market-wide (223 items; 44 against Zerodha alone) | ["which API is best / has free data"](https://reddit.com/r/IndiaAlgoTrading/comments/1uqfozi/) | **Blocked until pricing publishes** — then it's the sharpest hook in the deck |

Audience→hook mapping: First-timers → 1, 3, 5. Builders → 2, 4, and hook 1 reframed as "forward-test before deploying". Explorers → none of these directly; they get education content that ends at hook 1.

---

## 3. Google Search

Search = First-timers + Builders at the moment of intent. Search-only at launch (no PMax — uncontrollable in a niche; Google's own docs say search campaigns keep exact-match priority). In-market finance segments attached as observation only.

### Campaign 1 — Core API intent (protect this budget)

| Keyword (match) | Demand evidence | Copy hook |
|---|---|---|
| [trading api india], [best trading api india] | gl=IN autocomplete tree exists for both; **no broker API page ranks top-10 today** (checked live) | 1+4 |
| [nse api], [nse api free], [nse api charges] | 7 of 10 `nse api` autocomplete suggestions are pricing/access modifiers — active buyers | 5 (after pricing) / 4 |
| [free trading api india], [broker api charges] | "trading api **free**" is the top autocomplete modifier | 5 |
| [algo trading api india], [stock trading api india] | autocomplete-verified variants | 1 |

### Campaign 2 — Conquest (one ad group per broker; copy = their verified pain, stated as OUR facts, never theirs)

| Ad group / keywords | Why this broker's users are winnable (evidence) | Copy hook |
|---|---|---|
| [kite connect alternative], [kite connect pricing], [zerodha api charges], "kite connect" | Biggest pool: kiteconnect PyPI **371K downloads/mo**, 15.3K-thread forum. Pains: [₹500/mo data](https://zerodha.com/products/api/), [daily 6 AM token](https://kite.trade/docs/connect/v3/user/), [sandbox its own FAQ denies](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs) | 1 + 3 |
| [dhan api charges], [dhan api alternative], "dhan api" historical | dhanhq PyPI 86K/mo; [unresolved data-quality thread](https://madefortrade.in/t/do-not-buy-dhan-api-for-data/91053); [token churn, 150+ replies](https://madefortrade.in/t/update-for-api-traders-new-changes-in-dhanhq-api-authentication-process-and-updates/56286) | 4 + 3 |
| [upstox api], "upstox api" websocket | [7+ websocket-failure threads in 2026](https://community.upstox.com/t/broken-tokens-ws-failures-lagging-data-inconsistent-feed-v3/16420); sandbox is payload-only | 1 (real sandbox) |
| [groww api pricing], [groww api free alternative] | Their page prints the risk: [₹499 "early bird" vs ₹2,000 list](https://groww.in/trade-api) | 5 |
| [smartapi alternative], "smartapi" totp | [SDK 15 months stale](https://github.com/orgs/angel-one/repositories); TOTP dominates their variant queries | 3 |
| watchlist: [mstock api] | Mirae's ₹0 API is winning autocomplete real estate — monitor before bidding | — |

### Campaign 3 — Task wedges (underserved intents)

| Keywords | Evidence of vacuum | Copy hook |
|---|---|---|
| [paper trading api india], [paper trading api free] | Typed India demand; only global brands (Alpaca/IBKR) appear in autocomplete — no Indian answer | 1 |
| [options backtesting india], [historical options data nse], [historical options data api] | India variants autocomplete-confirmed; only one tool brand (Opstra) attached; Dhan owns "historical options data **dhan**" mentally — conquest | 4 |
| [algo trading software india], [algo trading platform india] (phrase, heavy negatives) | Biggest volume proxy, most mixed intent | 1 |

### Campaign 4 — AI-era land grab (≤3% of search budget)

[mcp trading], "automate trading with claude", [ai trading api india] — "automate trading **with claude**" appears in India autocomplete; four incumbents already ship MCP, Nubra has none. Run only alongside an MCP/agent product beat.

**Negatives (account-wide):** course · meaning · kya hai · pdf · book · jobs · salary · tutorial download · mt4 · mt5 · forex · binance · bybit · coinbase · crypto · bitcoin · quotex · telegram tips · signals · sure shot · guaranteed. Campaign 3 also: alpaca, ibkr, interactive brokers.

**Copy skeleton (approval-ready):** H1 "Trading APIs for NSE F&O" · H2 "Full Test Environment Included" / "Automated TOTP Login" · D "Historical OHLC+OI+IV+Greeks. UAT sandbox. SEBI-registered broker." · sitelinks Docs / UAT / Pricing / SDK · standard-warning link pattern. No "best", no returns.

---

## 4. YouTube

Two mechanisms, two tables. Both feed remarketing lists for a follow-up conversion campaign.

### 4a. Keyword targeting (ads on YouTube search results + watch pages — in-feed and in-stream on standard video campaigns)

| Keyword theme | Evidence | Audience |
|---|---|---|
| kite connect tutorial · upstox api tutorial · dhan api python | Tutorial supply is a top lens-content category (471 YouTube lens items); [Kite onboarding walkthroughs are themselves entry barriers](https://www.youtube.com/watch?v=r88L9AqnNaE) | First-timers |
| algo trading for beginners · api trading tutorial | G1/G2 autocomplete + corpus "trading for beginners" bigram | Explorers→First-timers |
| **algo trading kaise kare** (Hindi cell) | "trading kaise kare" appears verbatim in our first-timer corpus; Hindi walkthroughs of competitor apps exist | First-timers (Hindi) |
| python trading bot · backtesting options india | Dev-tutorial demand (corpus + autocomplete); crypto-contaminated on search but clean on YouTube content | Builders |
| paper trading india · virtual trading | Hook-1 cluster (256 corpus items) | First-timers |

### 4b. Channel placements (our ad on their videos — allowed; distinct from featuring creators)

| Channel | Subs (verified) | Why — Beacon/web evidence |
|---|---|---|
| **SquareOff** | 56.3k | Core algo audience; web-verified top India algo channel (its founder publicly quit Fyers' API over reliability — switch-minded viewers) |
| **AlgoTest** | 32k | Backtesting-intent viewers = hook 1+4 audience |
| **marketcalls / OpenAlgo** | 29.7k / 5.9k | The self-hosting builder crowd; OpenAlgo already lists Nubra |
| **QuantInsti** | 27.7k | Structured algo learners (explorer→first-timer pipeline) |
| **Dhan / Zerodha channels** | large | **Beacon evidence**: 6 and 3 lens items with the highest avg engagement of any channels in our corpus (6.3 / 6.6) — their API tutorial viewers are exactly our conquest pool |
| **Code2Trade, DEMAT DOSE, MarketXLS, NextLevelBot, Algo Trader!, OptionX, Kapil Zone** | small | **Beacon evidence**: each produced 3–8 API-trader lens items — small but purest-intent placements |
| Adjacent reach: Be Sensibull (171k), Theta Gainers (455k) | — | Options-analytics viewers; test cell only — density unproven in our corpus |

### 4c. Creative spec (compliance-locked)

5s hook on a friction ("Still logging in every morning to refresh your token?") → product-fact montage (UAT order placed on screen, docs, Greeks stream) → **≥5s standard warning, on-screen + voice-over** → reg-details end card. Formats: skippable in-stream on placements; in-feed on keywords; 6s bumpers with single facts ("Historical Greeks. Via API."); one Shorts cell; one Hindi cell. No P&L, no backtest results, no celebrities (>10 lakh followers = banned in-ad). Creator *sponsorships* are a separate lane: possible with the sub-10-lakh channels above, but each video needs exchange pre-approval — see compliance doc.

---

## 5. Meta (FB/IG)

Meta can't find "API traders" by interest — nothing narrower than "Investment"/"Stock trading" exists. Its three real jobs here:

| Play | Audience definition | Creative | CTA / capture |
|---|---|---|---|
| **1. Lead capture** (First-timers + Explorers) | Interest stack: Stock market + Day trading + Investment (verify live in Ads Manager — no canonical list), 20–45, metros first | Developer-styled (code on screen, terminal aesthetic) — the targeting is broad, the creative does the filtering: non-developers scroll past | Instant form with qualifiers ("Do you trade F&O?", "Which broker API today?") + **SMS verification on** (prefilled emails are junk) → CRM webhook |
| **2. Lookalikes** (scale what works) | Seed = **activated API users** (not all signups; seed quality is the whole game), min 100; India has NO Meta finance-category restrictions — lookalikes fully available ([Meta API docs](https://developers.facebook.com/docs/marketing-api/special-ad-category/)) | Same as play 1 | Same form or direct signup |
| **3. Retargeting** | Docs/UAT page visitors + lead-form openers; suppress existing clients via custom-audience exclusion (interest exclusions no longer exist) | Hook-specific: visited UAT docs → hook 1 creative | Signup |

Lead magnets that earn the email (DPDP-consented, itemized for marketing use): API cookbook (notebooks) · "true cost of algo trading in India" calculator · latency benchmark report · UAT access. Follow-up calling/WhatsApp has its own TRAI/SEBI surface — compliance doc §3.

---

## 6. Agentic search (Claude/ChatGPT/Gemini naming Nubra next to Zerodha and Dhan)

**How answers form:** ChatGPT ≈ Bing top-10 ([87% citation overlap](https://www.seerinteractive.com/insights/87-percent-of-searchgpt-citations-match-bings-top-results)) · Gemini/AI Overviews ≈ Google top-12 ([Google's doc](https://developers.google.com/search/docs/appearance/ai-features): normal indexing is the only requirement) · Claude ≈ Brave index · Perplexity = own crawler, most Reddit-heavy. What gets cited: **statistics +33%, quotable claims +41%, cited sources +28% — the citation boost is largest for challengers (+115%)** ([Princeton GEO paper](https://arxiv.org/abs/2311.09735)); commercial answers pull **40.9% of citations from listicles, 81% third-party** ([Wix study](https://searchengineland.com/ai-citations-favor-listicles-articles-product-pages-study-472364)); **Reddit is the most-cited domain overall** ([Profound, 4B citations](https://www.tryprofound.com/blog/the-data-on-reddit-and-ai-search)).

**Where we stand (checked live):** exactly one ranking page tells LLMs Nubra exists ([the multibagg comparison](https://www.multibagg.ai/market-pulse/articles/zerodha-nubra-dhan-api-comparison-cmp5l0ayn000ct70j0frlhjln) — no pricing, no link to nubra.io). robots.txt clean, docs crawlable — but **`/products/api/` is client-rendered: AI crawlers see 3.7KB**.

| Priority | Action | Why (evidence) | Effort |
|---|---|---|---|
| **P0** | Numbers page: pricing + rate limits + dated latency methodology | LLMs cite statistics (+33%); every comparison's Nubra column is currently blank | days |
| **P0** | Server-render `/products/api/` | AI crawlers don't execute JS; the API pitch is invisible to all of them | days |
| **P0** | Bing Webmaster + IndexNow + GSC; confirm CDN isn't blocking AI bots | ChatGPT ≈ Bing; median time-to-first-citation ~47 days after indexing | hours |
| **P0** | "Nubra vs Kite Connect" / "vs Dhan API" / "Best trading APIs India 2026" pages with tables + outbound citations | Cite-sources +115% for challengers; needs exchange-approval-safe wording | 1–2 wks |
| **P1** | Outreach to the listicles that rank today: multibagg (fix + Dhan-alternatives table), moneycontain, univest, algocrab, indikator, letsthinkwise, qubera, startupog, investormoney, cernoquant + techjockey/G2/alternativeto listings | These are the literal pages engines cite; pitch = the numbers page so inclusion is copy-paste | ongoing |
| **P1** | Reddit, authentic + disclosed: r/IndiaAlgoTrading AMAs, answer the threads that already name Nubra | Most-cited domain; cited posts average ~1yr old — compounding, start now | ongoing |
| **P1** | Dev UGC: public latency-benchmark repo, Stack Overflow, Medium/LinkedIn engineering posts, X threads (feeds Grok) | Top-5 cited domains per citation studies | ongoing |
| **P2** | Schema.org JSON-LD; llms.txt + .md doc mirrors (1-hr MkDocs plugin); Wikidata now, Wikipedia after real press | Cheap insurance; llms.txt has no proven citation lift ([Ahrefs: 97% get zero bot hits](https://ahrefs.com/blog/llmstxt-study/)) | hours |

Measure with a weekly 15-prompt panel across ChatGPT/Gemini/Perplexity/Claude/Grok (runs as a Beacon cron; Gemini + Perplexity expose citations via API) + AI-bot hits in server logs. Realistic: first citations 4–8 weeks after indexing; default inclusion next to Zerodha/Dhan is a 2–4 quarter outcome.

---

## 7. Where each hook comes from (consistency across the three analyses)

| Hook | insights doc (08-25) | market-research doc (08-27) | this doc |
|---|---|---|---|
| UAT / test-safely | backtest_trust friction theme (170 items); onboarding friction chain | Sandbox = Nubra's A-grade cell; 3 of 6 brokers have none; "keep your own logs" | 256 corpus items match test/paper language; keyword vacuum for `paper trading api india` |
| Static IP / deploy | deployment_infra theme (136) | SEBI framework = industry constant; dual-IP = unique framing | 232 corpus items; setup-friction YouTube evidence |
| Auth / tokens | onboarding_auth theme (119) | Auth = Nubra's B+ vs daily-login incumbents | 119 corpus items; conquest ammo per broker |
| Historical data + Greeks | data_access (158) + data_quality themes | Historical Greeks = only-in-market differentiator; Dhan's open wound | 145+105 corpus items; `historical options data nse` autocomplete |
| Pricing transparency | cost_pricing #1 theme (223) | Pricing n/p flagged as blocker | 134 corpus items; "free" = top autocomplete modifier; still blocked |

**Next action:** publish API pricing → draft the 5 creatives from §2 → one ENIT application. Everything else in this doc can start the same week.
