# Organic AI visibility — crawl audit, fixes, playbook, experiment (2026-08-30)

Four parts: what Claude finds when crawling nubra.io (probed live with AI-bot user-agents), the site fixes, the organic-mention playbook (sourced), and the search experiment.

**One term used throughout — "JS-only page":** a page whose HTML arrives essentially empty; a browser then runs JavaScript to draw the content. Humans see the full page. AI bots that fetch pages directly (OpenAI's GPTBot/ChatGPT-User, Anthropic's ClaudeBot, PerplexityBot) do not run JavaScript — they receive the empty shell. Google and Bing do run JavaScript, but in a delayed rendering queue, so such pages reach ChatGPT-search/AI-Overviews late and indirectly, and never reach Brave (the index Claude's web search uses).

---

## 1. What Claude faces when crawling/searching Nubra

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
- **Discovery fails**: ask "best trading API in India" and Nubra isn't in the candidate set — that set is assembled from third-party pages (listicles, forums), where Nubra is near-absent. Section 2 fixes retrieval-completeness; section 3 is what wins discovery.

### Structural issues (also flagged independently by the ChatGPT crawl run)

| Issue | Why it matters |
|---|---|
| Operational facts (rate limits, retry/reconciliation rules, TOTP guidance) live in FAQ pages, not the endpoint reference | AI/RAG systems chunk pages; facts outside the reference get missed or cited with lower authority |
| V3 and older doc paths coexist without clear separation | Naive crawlers merge obsolete and current API behavior |
| No machine-readable OpenAPI spec | The single strongest artifact for agentic/AI consumers of an API; competitors don't have one either — open win |

---

## 2. Website fixes, ranked

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

## 3. Organically boosting AI mentions — the plays, with sources

How the engines pick names (each verified against the primary source):

| Engine | Where its answers come from | Source |
|---|---|---|
| ChatGPT (search) | Bing's index — 87% of citations match Bing top results | [Seer Interactive study](https://www.seerinteractive.com/insights/87-percent-of-searchgpt-citations-match-bings-top-results) |
| Gemini / Google AI Overviews | Google's normal index; ~75% of links from top-12 organic; no special markup needed | [Google's official doc](https://developers.google.com/search/docs/appearance/ai-features) · [Botify via SEL](https://searchengineland.com/google-search-rankings-llm-mentions-450348) |
| Claude | Brave Search's index | [Anthropic subprocessor evidence](https://simonwillison.net/2025/Mar/21/anthropic-use-brave/) |
| Perplexity | Own crawler; most Reddit-weighted engine | [Perplexity bot docs](https://docs.perplexity.ai/guides/bots) · [Profound citation study](https://www.tryprofound.com/blog/the-data-on-reddit-and-ai-search) |

The plays, in causal order:

| Play | First step | Evidence it works | Source |
|---|---|---|---|
| **A. Be quotable** — publish exact numbers (pricing, rate limits, dated latency) | Ship the numbers page (fix 3) | Adding statistics: +33% AI-answer visibility; quotable claims: +41% | [Princeton GEO paper, KDD 2024](https://arxiv.org/abs/2311.09735) |
| **B. Own comparison pages** — "Nubra vs Kite Connect", "vs Dhan API", with tables + links to competitors' official docs | Draft 2 pages, route through exchange approval | Citing sources: +28% overall, **+115% for lower-ranked challenger sites** — the boost is biggest for exactly our position | same paper, [full text](https://arxiv.org/html/2311.09735v3) |
| **C. Get into third-party listicles** — the pages engines cite for commercial questions | Outreach queue (all currently rank, all checked live): multibagg, moneycontain, univest, algocrab, indikator, letsthinkwise, qubera, startupog, investormoney, cernoquant + techjockey/G2/alternativeto listings | Commercial queries: 40.9% of AI citations are listicles; 81% of those third-party (self-authored lists earn only 19%) | [Wix AI Search study, 1M+ citations](https://searchengineland.com/ai-citations-favor-listicles-articles-product-pages-study-472364) |
| **D. Reddit, disclosed + authentic** — official account answering r/IndiaAlgoTrading threads (two already name Nubra) | Answer the [TOTP thread](https://reddit.com/r/IndiaAlgoTrading/comments/1vh3obr/) and [Greeks thread](https://reddit.com/r/IndiaAlgoTrading/comments/1vbk8sg/) with disclosure | Reddit = most-cited single domain across AI engines (3.11% of 4B citations); feeds ChatGPT and Google via licensing deals; cited posts average ~1 year old — start now for 2027 answers | [Profound, 4B citations](https://www.tryprofound.com/blog/the-data-on-reddit-and-ai-search) · [OpenAI–Reddit deal](https://openai.com/index/openai-and-reddit-partnership/) |
| **E. Developer UGC** — public latency-benchmark repo, engineering posts, Stack Overflow, X threads | One engineering post + one public benchmark repo | Medium/LinkedIn/YouTube are top-5 cited domains; X posts feed Grok | [Semrush, 100M+ citations](https://www.semrush.com/blog/most-cited-domains-ai/) · [Peec AI, 30M sources](https://searchengineland.com/ai-search-engines-cite-reddit-youtube-and-linkedin-most-study-473138) |
| **F. Measure weekly** — the §4 panel now, then a 15-prompt weekly cron | Run §4 | Median time-to-first-citation ≈ 47 days after indexing; consistent publishers hit it 3.2x faster | [Xale.ai, 127 brands](https://www.xale.ai/studies/geo-time-before-results) |

Sequencing: A before C and D — outreach and Reddit answers need the numbers page to point at, or there's nothing for anyone to copy. Expectation: retrieval engines move at index speed (weeks); "Nubra named by default next to Zerodha and Dhan" is a 2–4 quarter outcome driven by C + D.

---

## 4. The experiment — you run it, we pattern-match

**Why these queries and not "trade with APIs":** the panel uses the words real starters type, not our internal vocabulary. Evidence: in India the category's entry language is **"algo trading"** (Google autocomplete has a full tree for it; the subreddit is r/IndiaAlgoTrading; the tools are "AlgoTest"/"algo platforms"), while **"trading api"** appears once someone is past the idea stage and choosing infrastructure (that's when our corpus shows the phrase). "Trade with APIs" as a phrase has neither an autocomplete tree nor corpus presence. So the panel covers the journey: entry queries in algo-language (1, 5, 9), infrastructure queries in api-language (2, 3, 4, 7, 8), and conquest/comparison queries (6, 10).

**Go ahead — the panel is final, no changes coming.** Keeping it frozen is the point: we re-run the identical panel ~6 weeks after the fixes ship, and the diff is the result.

**Protocol:** each query on Google (incognito, India), ChatGPT, Claude, Gemini. Record per query per engine: (1) does Nubra appear, (2) top 3–5 domains cited/ranked, (3) competitor names mentioned. Paste raw results here — pattern extraction is my job.

| # | Google form | ChatGPT/Claude/Gemini form | What it tests |
|---|---|---|---|
| 1 | how to start algo trading in india | "I trade manually on charts. How do I start algo trading in India?" | Who owns the beginner path |
| 2 | best trading api india | "Which broker has the best trading API in India?" | The money query |
| 3 | free trading api india | "Which Indian brokers give free trading APIs? What does data cost?" | Pricing-anchored choice |
| 4 | paper trading api india | "How can I test my trading strategy with an API without risking real money, in India?" | Our strongest hook — does anyone claim it? |
| 5 | best broker for algo trading india | "I'm a Python developer in India. Which broker should I open an account with for algo trading?" | Broker choice, dev framing |
| 6 | kite connect alternative | "Alternatives to Zerodha Kite Connect for algo trading?" | Conquest visibility |
| 7 | nse api free | "Cheapest way to get NSE market data through an API?" | Data-access intent |
| 8 | historical options data nse api | "Where can I get historical NSE options data with Greeks for backtesting?" | Our differentiator — who gets named |
| 9 | algo trading kaise kare | (Gemini + ChatGPT) "India me algo trading kaise shuru kare?" | Hindi answer space |
| 10 | dhan api vs zerodha api | "Compare Dhan API and Zerodha Kite Connect — which is better for a beginner?" | The comparison slot |

**Pattern hypothesis to confirm or break:** citations cluster into four source types, each with a mechanical counter-move — third-party listicles → play C · forum/Reddit threads → play D · brokers' own crawlable pages → plays A/B · the multibagg pair → fix that article first. Anything outside this taxonomy is the interesting finding.

**Baseline expectation:** Nubra appears ~0 times, except possibly query 10 (via multibagg). The re-run after fixes measures the movement.
