# Nubra organic AI visibility — master plan (v3, 2026-08-30)

Combines the crawl audit (2026-08-29), the 10-query × 4-engine experiment the user ran (2026-08-30, extraction in `ai-search-experiment-results-2026-08-30.md`), and the GEO research. One goal: Nubra named and cited when people ask Google/ChatGPT/Claude/Gemini about API/algo trading in India — organically.

**Baseline (measured):** Nubra = 0 of 40 AI-answer slots, 0 of 155 citations. Candidate set today: Zerodha (32/40), Dhan (28), Fyers (25), Upstox (20), Angel One (20) — and Pocketful, a younger broker, already in 5 of Claude's 10 answers. Entry is provably possible.

**One term — "JS-only page":** HTML arrives empty; a browser draws content via JavaScript. Humans see everything; AI bots that fetch directly (GPTBot, ChatGPT-User, ClaudeBot, PerplexityBot) get the empty shell; Google/Bing render it only via a delayed queue; Brave (Claude's index) never does.

---

## 1. The five citation patterns (from the experiment's actual winning URLs)

Each pattern = what engines demonstrably cited in OUR panel + the Nubra artifact that copies it.

| # | Pattern | The evidence (actual cited pages) | The Nubra artifact to ship |
|---|---|---|---|
| 1 | **The regulatory explainer** — biggest single winner: 16 citations across 3 sites, all small brands | tradejini.com "What SEBI's new algo trading rules mean for you" (**7×**, cited by Claude in 6 questions) · blog.liquide.life "SEBI algo trading regulations 2026" (**6×**) · sahi.com "SEBI algo rules 2026 — what every retail trader must know" (3×) | **"SEBI's retail algo rules, explained — and how to set up compliantly"** with working code (static IP, TOTP, 10 orders/sec in practice). Every "how do I start" answer needs this explanation; engines grab whoever explains it best. Small brands win it — authority not required |
| 2 | **The broker's own FAQ/pricing page** — 15 citations for Zerodha | support.zerodha.com "Kite Connect API FAQs" (5×) · "historical data payment plan" (3×) · "what are the charges for Kite APIs" | **Question-titled crawlable pages**: "What does the Nubra API cost?" · "Does Nubra have a paper-trading/test environment?" · "Nubra API rate limits" — title = the literal question, first lines = the direct answer with numbers |
| 3 | **The keyword-titled listicle** | algotest.in "Best brokers for algo trading in India" (4×, plus AI Overview's favorite domain) · fintegrationfs.com "Top 5 APIs for building a stock trading app in India" (3×) | (a) Own comparison hub "Best trading APIs in India 2026 — compared" with tables + links to competitors' official docs; (b) outreach so third-party lists add Nubra (81% of commercial citations are third-party lists — Wix study) |
| 4 | **The pricing-news thread** — engines cite it to stay current | kite.trade forum "Revising Kite Connect fees from ₹2000 to ₹500" (4×) — cited because engines' memory is stale (Gemini still quoted ₹2,000) | Publish pricing/changes as dated announcement pages. Fresh, dated numbers beat stale memory — and get cited as the correction |
| 5 | **The Reddit thread matching the query** — reddit appeared in 7/10 questions | r/IndiaAlgoTrading: "best free API for Indian algo trading" · "Zerodha vs Dhan for algo trading" · "paper trading via Python script" · "reliable NSE options data API" · r/developersIndia "free real-time NSE data API" | Disclosed official account answering **these exact threads** (each maps to a panel query); two threads already name Nubra unprompted — start there |

## 2. Per-engine reality (from the experiment) — where to win first

| Engine | Observed behavior | Play |
|---|---|---|
| **Claude** | Cites the most; sources = Brave-index long-tail blogs nobody optimizes for; widest brand set (incl. Pocketful) | **Beachhead.** Crawlable pattern-1/2/3 pages + Brave indexing → expect first mentions here |
| **Google AI Overview** | Cites Google top organic: algotest.in (5), groww blog, reddit | Normal Google SEO on our pages + reddit threads + AlgoTest listing |
| **ChatGPT** | Few citations; mostly model memory + light fetch (nseindia, zerodha support, sebi) | Bing Webmaster + IndexNow for the fetch path; patterns 1–2 for citability; UGC for the memory path |
| **Gemini** | Almost no citations; stale memory (₹2,000 Kite price) | Slowest — don't measure early progress here; wins come via training-data presence (Reddit/press), quarters not weeks |

## 3. The steps, sequenced

### Weeks 1–2 — make Nubra quotable (site)

| Step | Detail |
|---|---|
| 1. Numbers page | API pricing (needs the pricing decision — still the #1 blocker) + rate limits + session rules + UAT, one crawlable static page |
| 2. Server-render `/products/api/*` | Landing, blog posts, insti page currently serve 70 chars to direct AI fetchers. Acceptance: `curl -A GPTBot <url>` returns full text |
| 3. Sitemaps + indexes | Add all API URLs to sitemaps; Bing Webmaster Tools + IndexNow; GSC; verify AI bots aren't WAF-blocked; submit to Brave |
| 4. Pattern-2 FAQ pages | The question-titled pages from §1 row 2 — cheap, directly copies Zerodha's 15-citation play |

### Weeks 2–6 — the citation magnets (content)

| Step | Detail |
|---|---|
| 5. SEBI-rules explainer (pattern 1) | The proven 16-citation content type; ours adds working code — no one has the implementation layer |
| 6. Comparison hub (pattern 3a) | "Best trading APIs in India 2026" + "Nubra vs Kite Connect" + "Nubra vs Dhan API"; tables, exact ₹, dated stats, outbound links (GEO paper: cite-sources = +115% visibility for challengers); exchange-approval-safe wording |
| 7. Reddit answers (pattern 5) | Disclosed account; answer the 6 named threads + the 2 that already mention Nubra; never astroturf |
| 8. Dated announcements (pattern 4) | Pricing/feature changes as dated pages from day one |

### Weeks 6–12 — third-party spread

| Step | Detail |
|---|---|
| 9. Listicle outreach, reordered by observed citation power | algotest.in blog (in 7/10 questions) > fintegrationfs > tradejini blog & blog.liquide.life & sahi.com (Claude's favorites — small sites, likely reachable) > chittorgarh, indianbrokertest > techjockey/G2/alternativeto listings. multibagg demoted — never appeared |
| 10. Developer UGC | Public latency-benchmark repo, engineering posts (Medium/LinkedIn = top-5 cited domains), Stack Overflow, X (feeds Grok) |
| 11. AlgoTest listing + Speedtest | Resolve the listing discrepancy; a top-3 Speedtest rank = third-party citable proof |

### Ongoing — measure

| Step | Detail |
|---|---|
| 12. Re-run the frozen 10-query panel ~6 weeks after steps 1–4 ship | Success v1: Nubra named in ≥1 engine on Q2/Q3/Q4, cited ≥1× (today 0 and 0). Then a 15-prompt weekly cron (Gemini/Perplexity expose citations via API) |
| 13. Watch server logs | GPTBot/ClaudeBot/PerplexityBot hits on the new pages = leading indicator before answers change |

Expectations, sourced: first citations ~47 days median after indexing ([Xale](https://www.xale.ai/studies/geo-time-before-results)); Claude/AI-Overview movement in weeks; Gemini/ChatGPT-memory in quarters; Reddit citations mature ~1 year ([Profound](https://www.tryprofound.com/blog/the-data-on-reddit-and-ai-search)).

---

## 4. Crawl audit — what Claude faces when crawling/searching Nubra

Measured 2026-08-29 by fetching each page exactly as an AI bot does (no JavaScript).

### The gap: what a visitor sees vs what an AI bot receives

| Page | What a human visitor sees | What an AI bot receives (measured) | Severity |
|---|---|---|---|
| `/products/api/` (API landing) | Full marketing page: SDK pitch, feature list, CTAs | **70 characters** — just the words "Nubra API - Python SDK for Algorithmic Trading on Indian Stock Markets" | High |
| `/products/api/blogs/...` (every API blog post, e.g. the TradingView-webhook guide) | Complete how-to article — exactly the content AI answers like to cite | **70 characters** — the same title-only shell | High |
| `/insti/trading-apis.html` | Institutional pitch: REST, WebSocket & FIX APIs, co-location | **34 characters** | High |
| Sitemaps (`sitemap-0.xml` = 8 URLs, `blogs/sitemap.xml` = 85 URLs) | n/a | **0 API URLs in either** — crawlers aren't told the API section exists | High |
| `/pricing` | Brokerage & charges | Full text (3,163 chars) — **but no API pricing line exists** on it | High |
| `/` (homepage) | Full site | Full text (3,984 chars), title + meta description + schema markup | — (good) |
| `/products/api/docs/*` (documentation) | Docs | Full text (RateLimits page = 7,563 chars; index = 4,401) | — (good) |

### What's already good

- robots.txt allows every AI bot (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot — none blocked)
- The documentation (built as a static site) is fully crawlable — it's why AI answers about Nubra's API are accurate and deep
- Homepage and /pricing are server-rendered with proper titles and meta descriptions
- Rate limits are published in the docs

### Diagnosis, in two lines

- **Retrieval works**: ask an AI *about Nubra* and it builds an excellent picture — from docs + homepage + pricing (verified with a live ChatGPT run; every fact in its answer traced to those crawlable pages, none to the 70-char pages).
- **Discovery fails**: ask "best trading API in India" and Nubra isn't in the candidate set — that set is assembled from third-party pages (listicles, forums), where Nubra is near-absent. Section 5 fixes retrieval-completeness; sections 1–3 win discovery.

### Structural issues (also flagged independently by the ChatGPT crawl run)

| Issue | Why it matters |
|---|---|
| Operational facts (rate limits, retry/reconciliation rules, TOTP guidance) live in FAQ pages, not the endpoint reference | AI/RAG systems chunk pages; facts outside the reference get missed or cited with lower authority |
| V3 and older doc paths coexist without clear separation | Naive crawlers merge obsolete and current API behavior |
| No machine-readable OpenAPI spec | The single strongest artifact for agentic/AI consumers of an API; competitors don't have one either — open win |

---

## 5. Website fixes and good practices, ranked

| # | Fix | How |
|---|---|---|
| 1 | **Server-render the API section** (landing, blog listing, every post, insti page) | • Next.js SSG for `/products/api/*` (content is static — no server needed at runtime) • Acceptance test: `curl -A "GPTBot" <url>` must return the full article text • Until then these pages depend on Google/Bing's delayed JS-rendering and are blank to Claude/Perplexity/direct ChatGPT fetches |
| 2 | **Put the API section in sitemaps** | • Add all `/products/api/**` URLs (landing, blogs, docs) to a sitemap listed in robots.txt • Keep `<lastmod>` honest |
| 3 | **Publish the numbers page** (API pricing + rate limits + session rules + UAT) | • One static crawlable page • This is what listicle writers and AI answers quote; Nubra's column in every comparison is currently blank |
| 4 | **Register with the indexes AI engines read** | • Bing Webmaster Tools (ChatGPT ≈ Bing results) + IndexNow pings on publish • Google Search Console • Check server logs that AI-bot requests aren't WAF-blocked |
| 5 | **Question-shaped headings in crawlable pages** | • H2/H3 = the literal questions traders type (from our corpus): "How do I test my algo without real money?", "What does the Nubra API cost?" • First paragraph under each = the direct answer with numbers |
| 6 | **OpenAPI spec + consolidate ops facts into the reference** | • Publish `openapi.json` for REST V3 • Duplicate rate limits/retry rules onto the reference pages (keep FAQs too) |
| 7 | **Structured data (JSON-LD)** on API pages | • `Organization` (disambiguates Nubra-the-broker from Nubra Valley and the apparel brand) • `SoftwareApplication` for the SDK • `FAQPage` for docs FAQs |
| 8 | **Small hygiene** | • Add project URLs to the `nubra-sdk` PyPI package (5 min) • llms.txt + markdown doc mirrors (1-hr plugin; useful for developers pasting docs into AI tools — no proven ranking effect, per [Ahrefs' 137k-domain study](https://ahrefs.com/blog/llmstxt-study/)) |

Standing rule: **any page meant to be quoted must pass the curl test** — fetch it with a bot user-agent, no JavaScript; if the fact isn't in the response, AI systems can't reliably quote it.

---

---

## 6. The frozen experiment panel (for the re-run)

Protocol: each query on Google (incognito, India), ChatGPT, Claude, Gemini; record Nubra presence, top cited domains, competitor names. Panel unchanged from v1 — the diff against 2026-08-30 baseline is the measurement.

| # | Google form | AI form |
|---|---|---|
| 1 | how to start algo trading in india | "I trade manually on charts. How do I start algo trading in India?" |
| 2 | best trading api india | "Which broker has the best trading API in India?" |
| 3 | free trading api india | "Which Indian brokers give free trading APIs? What does data cost?" |
| 4 | paper trading api india | "How can I test my trading strategy with an API without risking real money, in India?" |
| 5 | best broker for algo trading india | "I'm a Python developer in India. Which broker should I open an account with for algo trading?" |
| 6 | kite connect alternative | "Alternatives to Zerodha Kite Connect for algo trading?" |
| 7 | nse api free | "Cheapest way to get NSE market data through an API?" |
| 8 | historical options data nse api | "Where can I get historical NSE options data with Greeks for backtesting?" |
| 9 | algo trading kaise kare | (Gemini + ChatGPT) "India me algo trading kaise shuru kare?" |
| 10 | dhan api vs zerodha api | "Compare Dhan API and Zerodha Kite Connect — which is better for a beginner?" |
