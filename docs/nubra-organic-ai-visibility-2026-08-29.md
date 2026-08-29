# Organic AI visibility — crawl audit, fixes, playbook, experiment kit (2026-08-29)

Four connected pieces: what an AI crawler actually sees on nubra.io today (probed live, 2026-08-29, as GPTBot/ClaudeBot/PerplexityBot user-agents, no JavaScript — none of these bots execute JS), the site fixes, the organic mention playbook, and the search experiment you'll run.

---

## 1. What I face when crawling/searching Nubra (live probe results)

| # | Finding | Evidence (measured today) | Severity |
|---|---|---|---|
| 1 | **The API landing page is invisible.** `/products/api/` serves the title and nothing else | **70 characters** of visible text (3.7KB HTML shell) vs homepage's 3,984 chars | Critical |
| 2 | **Every API blog post is invisible.** The TradingView-webhook guide, Tradetron guide — the exact GEO content Nubra already wrote — serve the same empty shell | `/products/api/blogs/tradingview-to-nubra-webhook-guide` → **70 chars** | Critical |
| 3 | **No sitemap lists a single API URL.** Main sitemap-0 = 8 URLs (contact/support/pricing/faq...), blogs sitemap = 85 URLs, **API URLs in either: 0**. Crawlers can only find the API section by following nav links into pages that then render empty | fetched sitemap.xml, sitemap-0.xml, blogs/sitemap.xml | High |
| 4 | The institutional API page is invisible too | `/insti/trading-apis.html` → **34 chars** | High |
| 5 | **API pricing doesn't exist anywhere crawlable** — `/pricing` (which IS server-rendered, 3.2k chars) has no API line; docs don't state it; third parties flag "pricing undisclosed" | pricing page fetch + earlier audit | High |
| 6 | Searching "Nubra" is polluted by Nubra Valley (Ladakh) and NuBra (apparel) — the broker only wins queries containing api/trading/broker | earlier audit | Medium (name reality — mitigate with schema + consistent "Nubra API" phrasing) |
| 7 | Zero third-party surface: 1 GitHub star, 0 TradingQnA posts, ~0 discoverable Reddit threads, absent from every ranking listicle except one | earlier audit (08-27) | High (this is §3's job) |
| 8 | No llms.txt (404), no JSON-LD on API/docs/pricing pages (homepage has some) | fetched | Low |

**What's already good:** robots.txt allows all AI bots (GPTBot, OAI-SearchBot, ClaudeBot, PerplexityBot not blocked) · the MkDocs documentation is fully crawlable (RateLimits page = 7,563 chars of clean text; index = 4,401) · homepage and /pricing are server-rendered with titles + meta descriptions · rate limits are published.

**The one-sentence diagnosis:** Nubra writes the right content, then ships it inside a client-rendered Next.js shell that no AI crawler can read, and doesn't tell crawlers it exists (no sitemap entries). The docs — built with MkDocs, static — prove the fix works: they're the only API pages a bot can read.

---

## 2. Website best practices — the fix list, ranked

| # | Fix | How | Effort |
|---|---|---|---|
| 1 | **Server-render the API section** — landing page, blog listing, every blog post, insti page | Next.js SSG/SSR for `/products/api/*` (the content is mostly static — SSG is enough). Acceptance test: `curl -A GPTBot <url>` returns the full article text | days — the highest-ROI item on this list |
| 2 | **Sitemaps that include the API section** | Add all `/products/api/**` URLs (landing, blogs, every docs page) to a sitemap referenced in robots.txt; keep `<lastmod>` honest | hours |
| 3 | **Publish API pricing on a crawlable page** | One static page: pricing + rate limits + token/session rules + UAT access — the "numbers page". This is what listicle writers and LLMs quote; every Nubra comparison column is currently blank | days (needs the pricing decision) |
| 4 | **Bing Webmaster Tools + IndexNow + GSC** | ChatGPT citations ≈ Bing top-10 (87% overlap); verify site, submit sitemaps, fire IndexNow pings on publish. Check server logs/CDN that AI-bot requests aren't being challenged (robots.txt is clean but a WAF can still block) | hours |
| 5 | **Keyword-rich, question-shaped headings in crawlable HTML** | Docs + blog pages should carry the literal questions traders type (from our corpus): "How do I test my algo without real money?", "Nubra API pricing and rate limits", "Automate daily TOTP login". H2/H3 = questions, first paragraph = the direct answer with numbers. LLMs lift Q→A blocks | ongoing editorial rule |
| 6 | **JSON-LD** on API pages: `Organization` (disambiguates Nubra-the-broker from the valley and the bra), `SoftwareApplication` (the SDK), `FAQPage` (docs FAQs) | template task | hours |
| 7 | **PyPI project URLs** — `nubra-sdk` has no links back to docs/GitHub | 5-minute setup.py/pyproject fix | 5 min |
| 8 | llms.txt + .md mirrors of docs | MkDocs plugin, ~1 hour. Honest expectation: no proven citation lift (Ahrefs: 97% of llms.txt files get zero bot requests) — do it for Cursor/Claude-Code users pasting docs, not for rankings | 1 hour |

Rule of thumb going forward: **any page meant to be quoted must pass the curl test** — fetch it with a bot UA, no JS; if the fact you want quoted isn't in the response, it doesn't exist.

---

## 3. Organically boosting AI mentions (no ads) — how engines pick names, and the plays

Mechanics (all verified in the 08-29 research): ChatGPT search ≈ **Bing top-10** (87% citation overlap) · Gemini + AI Overviews ≈ **Google top-12 organic** (Google: normal indexing is the only requirement) · Claude ≈ **Brave index** · Perplexity = own crawler, most **Reddit**-weighted. Content traits that win citations: **statistics (+33%), quotable claims (+41%), cited sources (+28% — and +115% for lower-ranked challenger sites)** (Princeton GEO paper); commercial questions pull **40.9% of citations from listicles, 81% of those third-party**; **Reddit is the most-cited single domain across engines** (4B-citation study), feeding ChatGPT and Google via licensing deals; cited Reddit posts average ~1 year old.

So the organic machine, in causal order:

| Play | Why it moves AI answers | Concrete first step |
|---|---|---|
| **A. Be quotable** (after §2 fixes) | LLMs assemble answers from numbers and claims they can lift. A page stating "₹X/mo, 10 orders/sec, full UAT, TOTP auth, historical Greeks since YYYY" becomes the canonical Nubra source | Ship the numbers page; add dated latency methodology when available |
| **B. Own comparison pages** | "X vs Y" pages with tables + outbound links to competitors' official docs hit the +115% challenger citation boost | "Nubra vs Kite Connect", "Nubra vs Dhan API" (exchange-approval-safe wording: facts, no discrediting) |
| **C. Get into third-party listicles** — the pages engines already cite | 81% of commercial citations are third-party lists; we have the named targets that rank today | Outreach queue: multibagg (fix the existing article + Dhan-alternatives table), moneycontain, univest, algocrab, indikator, letsthinkwise, qubera, startupog, investormoney, cernoquant; create techjockey/G2/alternativeto listings |
| **D. Reddit, disclosed and authentic** | Most-cited domain; slow-burn (~1yr-old posts get cited) — start now for 2027 answers | Official flaired account in r/IndiaAlgoTrading; answer the threads that already name Nubra (TOTP thread, Greeks thread); never astroturf |
| **E. Developer UGC** | Medium/LinkedIn/YouTube/GitHub are top-5 cited domains; X feeds Grok | Public latency-benchmark repo, engineering posts, Stack Overflow answers on `nubra-sdk` |
| **F. Measure weekly** | You can't steer what you don't see | The §4 experiment (manual, now) → then a 15-prompt weekly panel as a Beacon cron (Gemini + Perplexity expose citations via API) |

Sequencing matters: A and the §2 fixes come first — outreach (C) and Reddit answers (D) both *point at* the numbers page; without it there's nothing for a listicle writer or an LLM to copy. Timeline: retrieval engines pick up changes at index speed (first citations ~4–8 weeks); "Nubra by default next to Zerodha and Dhan" is a 2–4 quarter outcome that requires C + D, not just our own site.

---

## 4. The experiment — starter persona, 4 engines, you run it, we pattern-match

**Persona**: someone who trades manually, curious about API/algo trading, no code shipped yet (our Explorer→First-timer boundary — the corpus says this is where broker choice happens).

**Protocol**: run each query on Google (incognito, India), ChatGPT, Claude, Gemini. Per query per engine record: (1) does Nubra appear at all, (2) top 3–5 domains cited/ranked, (3) which competitor names appear. Paste results here in any raw form — I'll do the pattern extraction.

**Query panel** (phrasings from our corpus language + verified autocomplete; Google gets keyword form, AIs get the conversational form):

| # | Google form | ChatGPT/Claude/Gemini form | What it tests |
|---|---|---|---|
| 1 | how to start algo trading in india | "I trade manually on charts. How do I start algo trading in India?" | The entry answer — who owns the beginner path |
| 2 | best trading api india | "Which broker has the best trading API in India?" | The money query |
| 3 | free trading api india | "Which Indian brokers give free trading APIs? What does data cost?" | Pricing-anchored pick (top autocomplete modifier) |
| 4 | paper trading api india | "How can I test my trading strategy with an API without risking real money, in India?" | Our strongest hook (256 corpus items) — does anyone claim it? |
| 5 | best broker for algo trading india | "I'm a Python developer in India. Which broker should I open an account with for algo trading?" | Broker-choice with dev framing |
| 6 | kite connect alternative | "Alternatives to Zerodha Kite Connect for algo trading?" | Conquest visibility |
| 7 | nse api free | "Cheapest way to get NSE market data through an API?" | Data-access intent |
| 8 | historical options data nse api | "Where can I get historical NSE options data with Greeks for backtesting?" | Our differentiator — who gets named today |
| 9 | algo trading kaise kare | (Hindi/Hinglish on Gemini + ChatGPT only) "India me algo trading kaise shuru kare?" | Hindi answer space |
| 10 | dhan api vs zerodha api | "Compare Dhan API and Zerodha Kite Connect — which is better for a beginner?" | The comparison slot the multibagg article occupies |

**What we'll extract from your results** (the pattern hypothesis to confirm or break): citations should cluster into four source types — third-party listicles (moneycontain/univest tier), TradingQnA/Reddit threads, brokers' own crawlable pages, and the multibagg pair. For every source that actually appears, the counter-move is mechanical: listicle → outreach queue (play C); forum/Reddit thread → answer it, disclosed (play D); broker's own page → we need the equivalent crawlable page (plays A/B); multibagg → fix that article first. Anything that appears and *isn't* in that taxonomy is the interesting finding.

**Baseline expectation to measure against**: today Nubra should appear ~0 times except possibly query 10 via multibagg. Re-run the same panel ~6 weeks after the §2 fixes ship — that diff is the experiment's result.
