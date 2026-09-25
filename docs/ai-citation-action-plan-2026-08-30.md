# AI-citation action plan — patterns and sequenced steps (2026-08-30)

Built from the 10-query x 4-engine experiment (extraction: `ai-search-experiment-results-2026-08-30.md`). Companion docs: `nubra-organic-ai-visibility-2026-08-29.md` (crawl audit, site fixes, sourced plays, the frozen panel).

**Baseline (measured):** Nubra = 0 of 40 AI-answer slots, 0 of 155 citations. Candidate set today: Zerodha (32/40), Dhan (28), Fyers (25), Upstox (20), Angel One (20) — and Pocketful, a younger broker, already in 5 of Claude's 10 answers. Entry is provably possible.

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
