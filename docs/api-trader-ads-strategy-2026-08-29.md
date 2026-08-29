# Acquiring API traders — ads, targeting & agentic-search strategy, 2026-08-29

**What this is.** The full ingredient list for running Meta / Google Search / YouTube ads plus agentic-search (AI-answer) visibility, aimed at converting API traders to Nubra. Evidence: (1) our lens corpus (5,242 classified items — the actual language traders use); (2) live web research 2026-08-29 (Google autocomplete gl=IN, PyPI/GitHub demand proxies, official ad-platform policy pages, SEBI/NSE circulars, GEO citation studies). **Honesty note:** Google Trends and per-keyword India volumes/CPCs were not verifiable this session (Trends rate-limited, no tool publishes India numbers for these terms) — demand signals below are hard proxies (autocomplete trees, PyPI downloads, forum sizes), labeled as such. Ad libraries (Google Transparency Center, Meta Ad Library) need a real browser — do one manual pass before launch.

---

## The 10-second version

1. **Compliance first, ~3–4 weeks of runway**: SEBI SI-portal contact sync → Google G2RS verification + Meta SEBI verification → NSE/BSE pre-approval for EVERY creative (≥7 working days). Nothing serves before this chain completes.
2. **The creative constraint that shapes everything**: NSE ad code §5.7 bans any reference to algo past performance or expected returns — no backtest screenshots, no P&L, no "X% returns". Our compliant hooks are exactly the market's measured frictions: **test without real money (UAT), automated TOTP login, transparent pricing, historical Greeks data, 20-depth**.
3. **Highest-value keyword families** (proxy-ranked): `nse api / trading api india / free trading api india` (pricing-modifier density = in-market buyers, and **no broker owns this SERP today**) → broker-conquest (`kite connect` = 371K/mo PyPI downloads + two bid-worthy verified pains: ₹500/mo data and daily 6 AM token) → `options backtesting india` / `paper trading api india` (typed Indian demand, **no Indian answer exists**).
4. **Emails cannot be harvested** (Reddit/GitHub scraping fails platform ToS + Customer Match/CA terms + DPDP — five independent grounds). The compliant machine: lead magnets + webinars + newsletter sponsorships → first-party list → Customer Match (min 100) + lookalikes (min 100/country). India has NO Meta special-ad-category restrictions for finance — lookalikes fully available.
5. **Agentic search is winnable in 4–8 weeks for retrieval engines**: ChatGPT ≈ Bing top results (87% overlap), AI Overviews ≈ Google top-12, Claude ≈ Brave. P0: publish the numbers page (pricing/rate-limits/latency — LLMs cite statistics, +33% visibility per the GEO paper), **fix the JS-invisible API landing page** (AI crawlers currently see 3.7KB), Bing Webmaster + IndexNow, get into the 10 named listicles that answer engines cite today (exactly one currently knows Nubra exists).

---

# 1. The compliance gate (do this before anything else)

Sequence, with owner-level detail:

1. **SEBI SI Portal**: confirm the email + mobile on Nubra's SI-portal record match what the Google Ads and Meta Business accounts will register with — both platforms verify against it ([SEBI advisory PR 14/2025](https://www.sebi.gov.in/media-and-notifications/press-releases/mar-2025/advisory-to-sebi-registered-intermediaries-uploading-advertisements-on-social-media-platforms-smps-_92866.html)).
2. **Google financial-services verification** (mandatory for India since Jan 2023): via third-party verifier **G2RS** ([portal](https://g2risksolutions.com/financial-services), ≤5 days) proving SEBI authorization, then Google advertiser verification (~5 business days), then the [FSV form](https://support.google.com/google-ads/contact/google_ads_financial_services_verification). Business name must exactly match the SEBI registry entry. Policy: [regulators list](https://support.google.com/adspolicy/answer/12390454).
3. **Meta SEBI verification** (mandatory for India securities ads since Jul 31, 2025): verified against SI-portal records; SEBI-registered entities clear near-instantly ([coverage](https://inc42.com/buzz/meta-mandates-sebi-verification-for-investment-ads-in-india/)). The canonical Business Help doc is login-gated — confirm inside Business Manager.
4. **Exchange pre-approval for every creative** (NSE Code of Advertisement, [NSE/COMP/55482](https://www.nseindia.com/static/trade/members-code-of-advertisement)): via ENIT-COMPLIANCE, max 5 creatives/application, **≥7 working days before release**; approved creatives reusable 180 days. Applies to search ads, YouTube ads, Meta ads, landing pages, and paid influencer videos. Penalty: ₹1 lakh/instance, escalating to new-client bans.

**Creative rules that bind every asset:**
- Standard warning verbatim, ≥10-pt: *"investments in securities market are subject to market risks, read all the related documents carefully before investing."* Video: visual AND voice-over, **≥5 seconds**. Space-constrained (search ads): hyperlink to the site carrying full details is mandatory.
- Must carry: SEBI-registered name, address, registration number, Member ID, own logo.
- **§5.7 (the big one)**: no reference, direct or indirect, to past performance or expected returns of algo strategies — anywhere publicly accessible, including association with platforms that display strategy returns. Kills P&L creatives, backtest-result hooks, marketplace-return screenshots. ⚠️ legal review on how far this reaches into docs/organic content.
- No superlatives ("best/#1") unless independently conferred · no celebrities (>10 lakh followers per handle counts as celebrity — vet every creator) · no referral incentives/cashback for account opening · brokerage mentions need the SEBI-limit line · statistics need cited sources.
- The "9 out of 10 F&O traders lose money" disclosure is a website/login-popup mandate, not an ad mandate — but F&O landing pages are approval-scoped; decide with the exchange approver.

**Prerequisite from the market-research doc: publish API pricing.** Comparison pages, "free API" positioning, and half the keyword plan collide with an unpublished price. This is the single blocking product-marketing decision.

---

# 2. Message architecture — what we're allowed to say, matched to what traders actually feel

From the lens corpus (counts = classified items) × the §5.7 constraint:

| Pain (measured) | Compliant hook | Proof asset needed | Segment |
|---|---|---|---|
| Backtest/paper-trading anxiety (85 backtest_trust + "paper trading" = top-5 bigram in G2 & G3) | **"Test your algo without real money — full UAT environment"** (competitors' own forums say "you can't": Angel One staff literally advise keeping logs) | UAT landing page + "first test order in 15 minutes" tutorial | G2, G3 |
| Daily-token/auth churn ("access token", "api key", "static ip" = top G2 bigrams; Kite daily 6 AM expiry; Dhan 150+-reply churn thread) | **"Automated TOTP login, officially supported. Primary + secondary static IP."** | Auth docs + token-lifetime comparison table | G2, G3 |
| Data cost + access (cost_pricing = #1 friction theme, 44 items against Zerodha alone; "market data feed", "historical data" dominate friction language) | **"Transparent API pricing. Historical OHLC + OI + IV + Greeks."** (only after pricing is published) | Numbers page (§6 P0) | all |
| Data depth/trust (Dhan's unresolved data-quality thread; Upstox 30-depth paywalled) | **"20-level depth, standard. Greeks live and historical."** | Spec page with dated methodology | G3 |
| Reliability (Upstox websocket pattern, Fyers 21+ outages) | Only claimable with evidence: **public status/latency page first**, then "measured, published uptime" | Status page + AlgoTest Speedtest entry | G3 |

Segment → funnel mapping: **G1 (18%)** = education creatives (YouTube/Meta) → lead magnet; **G2 (13%)** = "first order on UAT" search + broker-forum-pain conquest; **G3 (69%)** = spec/proof creatives, developer-styled, search + placements. Hindi note: "trading kaise kare" appears in our G2 corpus and Hinglish definitional queries in autocomplete — Hindi YouTube creative is worth one test cell; definitional Hindi terms are search negatives.

---

# 3. Google Search — campaigns, keywords, params

**Account settings**: Location India (presence, not interest) · Languages English + Hindi (English keywords catch Hinglish typing) · Networks: Search only, no Display expansion · Start manual CPC / maximize-clicks with caps, move to tCPA only after ≥30 conversions · **Search campaigns take exact-match priority over PMax — do NOT run PMax at launch** (uncontrollable in a niche; no placement targeting, no custom segments; [Google's own serving-priority doc](https://support.google.com/google-ads/answer/10724817)). In-market "Financial Services/Investing" segments attached as **observation only** (custom segments don't exist on Search).

**Campaign 1 — Core API intent (highest priority, protect budget):**
- Exact: `[trading api india]` `[best trading api india]` `[nse api]` `[nse api free]` `[nse api charges]` `[free trading api india]` `[broker api charges]` `[algo trading api india]` `[stock trading api india]`
- Phrase: `"trading api"` (India geo does the filtering), `"nse trading api"`, `"api trading platform india"`
- Evidence: autocomplete tree is dense with pricing modifiers (free/cost/charges/key/price = 7 of 10 `nse api` suggestions) and **no broker API landing page ranks top-10** for "trading api india" today.

**Campaign 2 — Conquest (broker-branded), one ad group per broker so copy matches the pain:**
- `[kite connect alternative]` `[kite connect pricing]` `[kite connect charges]` `[zerodha api charges]` `"kite connect" + access token/login` — copy angle: no daily browser login, sandbox included. (Largest pool: kiteconnect PyPI 371K/mo, 15.3K-thread forum.)
- `[dhan api charges]` `[dhan api alternative]` `"dhan api" historical data` — angle: historical data you can trust + Greeks history.
- `[upstox api]` variants — angle: reliability + full sandbox (their sandbox is payload-only; websocket complaints documented).
- `[groww api pricing]` `[groww api free alternative]` — angle: their ₹499 "early bird vs ₹2,000 list" uncertainty printed on their own page.
- `[smartapi alternative]` `"smartapi" totp` — angle: maintained SDK + real docs.
- `[mstock api]` watch-listed (Mirae's ₹0 API is winning autocomplete real estate — monitor, bid if volume shows).
- ⚠️ Trademark rules: bidding on competitor brand keywords is allowed; using their marks in ad copy is not. No competitor discrediting per NSE code §5.2 — copy states Nubra facts, never "X is unreliable".

**Campaign 3 — Task queries (the underserved wedges):**
- `[paper trading api india]` `[paper trading api free]` — vacuum: only global brands (Alpaca/IBKR) fill it.
- `[options backtesting india]` `[options backtesting free india]` `[historical options data nse]` `[historical options data api]` `[nifty historical options data]`
- `[websocket market data nse]` (exact only — the broad cluster is crypto-contaminated).
- `[algo trading software india]` `[algo trading platform india]` `[algo trading app india]` phrase-match with heavy negatives (biggest volume proxy, most mixed intent).

**Campaign 4 — AI-era land grab (tiny budget, cheap CPCs, strategic):**
- `[mcp trading]` `[trading mcp server]` `"automate trading with claude"` `"automate trading with ai" india` `[ai trading api india]`
- Note: four incumbents already occupy MCP (Zerodha hosted MCP, Dhan, Upstox, Groww) and Nubra has no MCP surface — this campaign should launch **with** an MCP/agent product beat, else land on the AI-assistant docs story.

**Negative keyword list (apply account-wide, seed from corpus + autocomplete):**
`course, courses, meaning, kya hai, kaise kare (search only — keep for YouTube), pdf, book, books, jobs, salary, internship, tutorial free download, mt4, mt5, forex, binance, bybit, okx, coinbase, crypto, bitcoin, olymp, quotex, telegram tips, signals provider, sure shot, guaranteed` — plus `alpaca, interactive brokers, ibkr` on Campaign 3 unless conquesting deliberately.

**Ad copy skeleton (pre-approval ready):** H: "Trading APIs for India | Full Test Environment" / "NSE F&O APIs — Greeks, 20-Depth" / D: "Automated TOTP login. UAT sandbox. Historical OHLC+OI+IV+Greeks. SEBI-registered broker." + site links (Docs / UAT / Pricing / SDK) + the mandated hyperlink-to-full-disclosures pattern for space-constrained formats. No "best", no returns, no performance.

---

# 4. YouTube — placements, segments, creative spec

**Campaign type**: standard Video (awareness/consideration subtype) — **placement targeting is not available on conversion-goal video campaigns, PMax, or Demand Gen**; run placements on a reach/consideration campaign and retarget viewers with a conversion campaign.

**Placement list (channels our audience actually watches — from corpus + verified subs):** SquareOff (56.3k), AlgoTest (32k), marketcalls (29.7k), QuantInsti (27.7k), OpenAlgo (5.93k), ALT Investor (3.15k), Code2Trade, DEMAT DOSE, Algo Trader!, NextLevelBot, plus competitor channels Dhan/DhanHQ, Zerodha, Be Sensibull (171k), Theta Gainers (455k). Placements on a channel = our ad on their videos (allowed); this is **not** the same as featuring the creator (celebrity rule untouched). Direct "viewers of competitor channel" audiences don't exist — placements + custom segments are the only mechanisms.

**Custom segments (work on YouTube, not Search):** people who searched Google for `kite connect`, `dhan api`, `algo trading india`, `nse api`, `options backtesting`, `tradingview india`; plus URL-seeded segment: kite.trade, dhanhq.co, algotest.in, tradetron.tech, docs.openalgo.in.

**Also attach**: in-market Financial Services/Investing (India — verify population in-account), Customer Match once the list exists, remarketing from docs/UAT page visitors (personalized ads for broking are NOT restricted in India).

**Formats**: skippable in-stream on placements; Shorts ads for the G1 education layer; 6s bumpers for spec-facts ("20-level depth. Historical Greeks. UAT sandbox.").

**Creative spec (compliance-locked):** first 5s hook on a friction ("Still logging in every morning to refresh your token?") → product fact montage → **≥5s standard warning, on-screen AND voice-over** → reg details end-card. No P&L, no backtest results, no returns, no celebrities. Every video pre-approved via ENIT.

**Sponsorships (non-ads)**: integrations with sub-10-lakh-follower channels (SquareOff/AlgoTest/marketcalls/QuantInsti tier) are legally possible but each video = an advertisement → exchange pre-approval + warning + §5.7 applies inside the video. No published rate benchmarks — get 3 direct quotes. P R Sundar-tier (1.22M) = celebrity ban.

---

# 5. Meta (FB/IG) — verification, targeting, lead ads

- **India is NOT a special-ad-category geo for finance** ([Meta API docs](https://developers.facebook.com/docs/marketing-api/special-ad-category/)) — age/gender/geo targeting, interests, custom audiences, and **lookalikes all available** (unlike US/CA/EU).
- Interests that exist post-2024-removals: "Investment", "Stock market", "Day trading", "Stock trader" tier — verify live in Ads Manager (no canonical list). Nothing narrower exists; the mechanism is **broad-ish interest stack + creative self-selection** (developer-styled creatives: code on screen, terminal aesthetics — non-developers scroll past) + lookalikes.
- Detailed-targeting *exclusions* are gone — suppress existing clients via a custom-audience exclusion list instead.
- **Lead ads**: instant forms with qualifying questions ("Do you trade F&O?", "Which broker API do you use today?") + **SMS-passcode verification on** (prefilled emails are junk without it) → CRM webhook. Forms must not ask for account numbers; privacy-policy link required. Follow-up calls/WhatsApp = separate TRAI DND + SEBI surface (⚠️ legal).
- Custom Audience terms: audience names/criteria must not be based on financial attributes — name lists neutrally ("newsletter-subs-aug26", not "F&O-heavy-traders").
- Role in the mix: Meta is the **G1/G2 education + lead-magnet channel** and the lookalike engine — not where G3 developers convert directly.

---

# 6. Precise targeting & the email question

**Can we get emails of API traders from Reddit/forums/GitHub? No.** Five independent grounds, each individually sufficient: GitHub AUP prohibits using scraped info for unsolicited contact · Reddit UA prohibits automated collection/commercial use · Google Customer Match requires first-party data "collected directly from customers" (auditable) · Meta CA terms require warranted consent you can't give for scraped data · DPDP (penalties to ₹250 crore) requires specific informed consent. Don't do it; don't buy lists either (same DPDP/CM problems).

**What works instead — the first-party machine:**
1. **Lead magnets** (gate on email with DPDP-itemized consent notice naming marketing use): API cookbook (Jupyter notebooks), "true cost of algo trading in India" calculator/report, latency benchmark report, UAT access itself.
2. **Webinars**: "SEBI-compliant algo setup, step by step" (the implementation-layer gap no one fills), "first API order in one sitting". Registration = consented email.
3. **Newsletter sponsorships** (rent audiences, never receive emails): Trade Brains sells directly (3M+ monthly users, advertise@tradebrains.in); Finshots (500k subs) partnership unverified — ask; dev-adjacent options exist. CTA lands on our own capture page.
4. **Customer Match** (Google: min 100 users, 540-day membership, needs consent + FSV-verified account) + **Meta lookalikes** (min 100/country; seed with activated API users, not all signups — seed quality is the whole game).
5. **Existing Nubra account holders** who haven't touched the API = the cheapest conversion pool of all — email/in-app campaigns to own users need no ad platform at all (still DPDP-scoped, still exchange-approval-exempt only if sent to existing clients via registered channels with the "for consumption by client" tag).

---

# 7. Agentic Search Optimization (Claude/ChatGPT/Gemini answering "best trading API India" with Nubra in it)

**How answers form (verified):** ChatGPT search ≈ Bing top-10 (87% citation overlap — [Seer](https://www.seerinteractive.com/insights/87-percent-of-searchgpt-citations-match-bings-top-results)); AI Overviews/Gemini ≈ Google index, top-12 organic (~75% of links), no special markup needed ([Google's own doc](https://developers.google.com/search/docs/appearance/ai-features)); Claude ≈ Brave index; Perplexity = own crawler, most Reddit-heavy. What gets cited: statistics +33%, quotable claims +41%, cited sources +28% — with the citation boost strongest for lower-ranked challengers (+115%) ([GEO paper](https://arxiv.org/abs/2311.09735)); commercial queries pull 40.9% of citations from **listicles**, 81% of those third-party ([Wix study](https://searchengineland.com/ai-citations-favor-listicles-articles-product-pages-study-472364)); Reddit is the most-cited single domain across engines ([Profound, 4B citations](https://www.tryprofound.com/blog/the-data-on-reddit-and-ai-search)) and feeds ChatGPT/Google via licensing deals.

**Where we stand today (checked live):** exactly ONE ranking page tells LLMs Nubra exists (the multibagg.ai Zerodha-vs-Nubra article — which has no Nubra pricing and no link to nubra.io). Every other ranking listicle for the four money queries: zero Nubra. robots.txt is clean (all AI bots allowed), docs are crawlable — but **the API landing page is client-rendered: AI crawlers see 3.7KB containing a title**.

**P0 (this month):**
1. **Numbers page**: "Nubra API — pricing, rate limits, latency" — one crawlable page with ₹ pricing, the already-published rate limits restated, measured latency with dated methodology, SEBI reg number. This is what listicle writers and LLMs quote; Nubra's row in every comparison is currently blank.
2. **Server-render `/products/api/`** (Next SSR/SSG). Single cheapest fix with direct retrieval impact on every engine.
3. **Bing Webmaster Tools + IndexNow + GSC**: verify, submit sitemaps, wire IndexNow pings on publish. Confirm CDN/WAF isn't blocking OAI-SearchBot/ClaudeBot/PerplexityBot (robots.txt is fine; check server logs).
4. **Comparison pages on nubra.io**: "Nubra vs Kite Connect", "Nubra vs Dhan API", "Best trading APIs in India 2026 (compared)" — tables, exact figures, dated stats, outbound links to competitors' official pages. ⚠️ NSE §5.2/§5.1 shape the wording (facts, no discrediting, no "best" claims about ourselves) — route through exchange approval.

**P1 (1–2 quarters):**
5. **Listicle outreach** (named targets, found ranking today): multibagg.ai (fix the existing article: add pricing + link; get into their Dhan-alternatives table) · moneycontain · univest · algocrab · indikator · letsthinkwise · qubera · startupog · investormoney · cernoquant · techjockey + G2 + alternativeto listings. Pitch = the numbers page, so inclusion is copy-paste.
6. **Reddit, authentically** (slowest, compounding: cited posts average ~1yr old): disclosed official account, AMAs and support in r/IndiaAlgoTrading + the broker-API threads that already name Nubra. Never astroturf.
7. **Developer UGC**: public latency-benchmark repo, Stack Overflow tag, Medium/LinkedIn engineering posts (top-5 cited domains), X threads (feeds Grok).
8. Schema.org JSON-LD (Organization/SoftwareApplication/FAQPage) — cheap insurance, inconclusive evidence.

**P2:** llms.txt + .md doc mirrors (1-hour MkDocs plugin; useful for Cursor/Claude Code users, no proven citation lift — Ahrefs: 97% of llms.txt files get zero bot requests) · Wikidata now, Wikipedia only after real press coverage (NCORP bar not met today).

**Measurement**: weekly prompt panel (15–20 prompts incl. Hindi variants) across ChatGPT/Gemini/Perplexity/Claude/Grok — **this can run as a Beacon cron job** (Gemini grounding + Perplexity Sonar expose citations via API); log Nubra mention rate + cited URLs. Server-side: log AI-bot hits on nubra.io as the leading indicator. Paid option later: Otterly $29–189/mo. Timeline reality: median time-to-first-citation ~47 days after indexing; "Nubra by default alongside Zerodha and Dhan" is a 2–4 quarter outcome gated on listicle penetration + Reddit footprint.

---

# 8. Corpus ↔ search-demand tally (the "Google Trends" section, honestly)

Google Trends itself was unfetchable (429s) — tally below maps our corpus language to verified autocomplete demand instead; re-pull Trends curves manually for launch decks.

| Our corpus signal (counted) | Public demand signal (verified) | Ad artifact |
|---|---|---|
| "paper trading" top-5 bigram in G2 AND G3 | `paper trading api india` + `free` typed in autocomplete; incumbents answer "you can't" | Campaign 3 exact keywords + UAT hero creative |
| "market data feed" / "historical data" dominate friction language | `nse api` autocomplete = 7/10 pricing/access modifiers | Campaign 1 core keywords |
| "access token" / "api key" / "static ip" top G2 bigrams | Kite daily-token docs, Dhan churn thread, `smartapi totp` autocomplete | Conquest ad-group copy per broker |
| cost_pricing #1 friction theme (223 items; 44 vs Zerodha alone) | `trading api free`, `broker api charges`, `zerodha api charges` typed | "Transparent pricing" hook — **blocked until pricing publishes** |
| backtest_trust 170 items | `options backtesting india/free` typed; Opstra the only tool brand attached | Campaign 3 + backtesting content hub |
| AI/MCP fastest-growing G3 cluster | "automate trading **with claude**" in India autocomplete; 4 incumbents ship MCP | Campaign 4 + MCP product decision |
| "trading kaise kare" (Hindi) in G2 | `algo trading kya hai` autocomplete | Hindi YouTube creative test; Hindi definitional = search negative |
| G3 = 69%, showcase-driven | Reddit = most-cited AI-answer domain; r/IndiaAlgoTrading +200%/yr | GEO P1 Reddit + placements, not search spend |

---

# 9. Budget shape + measurement (no CPC data was verifiable — shares, not rupees)

- **40% Search** (Campaign 1 core + Campaign 2 conquest; Campaign 3 at 10% inside this; Campaign 4 ≤3%)
- **25% YouTube** (placements + custom segments; Shorts test cell; Hindi test cell)
- **20% Meta** (lead ads + lookalikes once seed ≥100 activated API users)
- **15% non-ad**: newsletter sponsorships + creator integrations + GEO content production
- KPIs by funnel stage: Search → API-signup CPA and UAT-activation rate (not clicks); YouTube → view-through signups + branded-search lift; Meta → verified-lead CPA + lead→activation %; GEO → prompt-panel mention rate + AI-bot crawl volume + listicle inclusions count. Wire Enhanced Conversions/CAPI with DPDP-reviewed consent before scaling.
- Watch item: AlgoTest's public **Broker Speedtest** — a top-3 latency rank there is a free, §5.7-safe proof asset every campaign can cite ("measured by a third party").

---

## Blockers (decide these first) and next actions

**Blockers:** (1) publish API pricing — half the strategy references it; (2) SI-portal contact sync — both verifications depend on it; (3) DPDP consent wording for list uploads — before any Customer Match/CA upload; (4) §5.7 legal read — scope over docs/organic/marketplace listings.

**Five next actions (smallest first):**
1. Sync SI-portal contacts + start G2RS and Meta verification (parallel, ~2 weeks).
2. Ship the numbers page + SSR fix + Bing/IndexNow (engineering, days).
3. Draft 5 launch creatives per the skeletons above → one ENIT application (7-working-day clock).
4. Manual pass of Google Ads Transparency Center + Meta Ad Library (browser) for Dhan/Upstox/Angel One/AlgoTest + pull Google Trends IN curves for the §8 keyword families — the two things this research couldn't fetch.
5. Stand up the weekly LLM prompt panel as a Beacon cron (15 prompts, log mentions + citations).
