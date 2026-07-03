# Social Pulse — Twitter / X Ingestion Options & Decision

_Research + design doc · 2026-06-29 · revisits the "X out of scope" call in
`social-pulse-architecture-2026-06-14.md` §2._

## 0. TL;DR

- The original architecture doc parked **Twitter/X as out of scope** ("no usable free
  tier post-2023; a money pit"). This doc revisits that with the **verified mid-2026
  landscape** and **reverses it**: X is now worth ingesting — but **only via a paid
  managed API**, never via free scraping.
- **All free options are structurally doomed** in 2026 (login-gated, token/`doc_id`
  rotation every 2–4 weeks, account+IP bans, residential-proxy requirement). "Free"
  costs more in proxies + burner accounts + maintenance than the paid API costs in
  dollars — and returns *less reliable* data.
- **Recommended path: `twitterapi.io`** — ~$0.15 / 1,000 tweets, no auth on our side
  (zero ban risk), full search-operator grammar incl. **historical** search, REST.
- **Official X API (pay-per-use)** is the ToS-clean fallback but ~**33× pricier** and,
  for new developers, effectively limited to **7-day recent search**.
- The pipeline is **source-agnostic** (everything runs on the `RawItem` contract), so X
  is a drop-in `social_pulse/sources/twitter.py` adapter + one `ingest()` line + a
  sidebar checkbox + query config. **Zero downstream changes.**

> ⚠️ **Volatile facts.** X access terms and scraper viability change on a weeks-to-months
> cadence. Every dated/priced claim below was web-verified on **2026-06-29**. Re-verify
> before acting if it's materially later. Sources are listed in §9.

---

## 1. Why X at all (signal for our audience)

Indian "FinTwit" is where a large slice of F&O / options / algo-dev conversation happens
in real time — cashtags (`$NIFTY`, `$BANKNIFTY`), expiry-day chatter, broker outage
complaints, algo/API tips, and the finfluencer layer we care about for **Rising Voices**.
It is higher-velocity and more public-figure-driven than Reddit, which makes it strong
for both **Trends** (what's spiking now) and **Rising Voices** (who's driving it).

The cost-benefit changed in our favor for two reasons:
1. Managed scraping APIs matured and are now **cheap** ($0.05–0.25 / 1k tweets).
2. Our pipeline already abstracts the source, so integration is small and low-risk.

---

## 2. The 2026 access landscape (verified)

### 2A. PAID — the paths that actually hold up

| Option | Cost (2026) | Auth burden on us | Search scope | Reliability | ToS posture |
|--------|-------------|-------------------|--------------|-------------|-------------|
| **twitterapi.io** *(recommended)* | **~$0.15 / 1k reads** ($0.00015/tweet), no floor, no cap | **None** — they run accounts/proxies | Full operator grammar, **incl. historical**; `Latest` or `Top` | ~0.5s median, claims 99.99% uptime | Grey (third-party scraping behind their infra; risk is theirs, not ours) |
| **Official X API (pay-per-use)** | **$0.005/post read**, $0.010/author read, $0.001 "owned" reads; cap 2M reads/mo | Dev account + credits | **Recent only (7 days)** on pay-per-use; full archive = Pro/Enterprise | First-party, stable | **Clean** |
| GetXAPI | ~$0.05 / 1k | None | Search operators | Managed | Grey |
| Apify "kaito" tweet scraper | ~$0.25 / 1k | None | Search/handle | Managed actor | Grey |
| Sorsa API | **$49/mo flat** REST | None | Search/timeline | Managed | Grey |
| Bright Data / Data365 | Enterprise quote | None | Broad | Managed, SLA | Grey/managed |

**Official X API — the fine print that matters:**
- Since **2026-02-06**, **pay-per-use is the default** for new developers; the old flat
  tiers (Basic $200/mo, Pro $5,000/mo) are **closed to new signups**.
- Free tier is **useless for us**: ~1 read request / 15 min, ~100 reads/mo, **no search**
  — it's for bots that *post*, not apps that *collect*.
- Search endpoints: `/2/tweets/search/recent` (**last 7 days**) is reachable on
  pay-per-use; `/2/tweets/search/all` (**full archive**) needs **Pro ($5k) or Enterprise
  (~$42k)** — both closed/expensive. So a new dev effectively gets **7-day** search.
- Pricing moved again on **2026-04-20** (owned reads → $0.001; writes → $0.015; posts
  with a URL → $0.20). Expect continued drift.

**twitterapi.io — capability + the one caveat:**
- Advanced Search accepts the full Twitter operator grammar: cashtags, hashtags, `from:`,
  `to:`, `since:`/`until:`, `lang:`, `min_faves:`, etc. → **we can query anything**,
  including back in time, which the official pay-per-use tier can't.
- Returns `{ tweets, has_next_page, next_cursor }`; loop on the cursor to walk a window.
- **Caveat (design around it):** X's cursor pagination is flaky upstream in 2026 — deep
  pulls (10+ pages) can **duplicate or stop early**. → We page in **bounded windows**
  (date-sliced, capped page count) and lean on our **content-hash dedup** to absorb the
  duplicates rather than trusting infinite scroll.

### 2B. FREE — structurally doomed (not merely inconvenient)

**Alive but fragile:** `twikit`, `twscrape`, `Tweety`, `Scweet`.
**Dead:** `snscrape`, `Twint`, `Nitter`.

Why "free" fails as a *standing* source in 2026 — these are platform-level locks, not bugs
you can out-engineer cheaply:

1. **Login-gated.** Since late 2025, search results and most timelines require an
   **authenticated session**. No anonymous/guest path reaches them → you must feed a real
   (burner) account, which is exactly what gets banned.
2. **Guest tokens expire** (hours) and acquisition shifts every few weeks.
3. **GraphQL `doc_id`s rotate every 2–4 weeks** — you track 8–12 at once; each rotation
   breaks the scraper. Reported maintenance tax: **10–15 hrs/month**.
4. **Account + IP bans at any real volume** → you need **residential proxies**, rotating
   fingerprints, and disposable accounts to survive.

**The "free" cost is not zero:**

```
free scraper true cost  =  residential proxy bill
                         +  burner accounts (that keep dying)
                         +  10–15 hrs/month of break-fix engineering
                         +  data gaps every time it breaks mid-window
```

…to obtain **less reliable** data than a **$3 API call** returns cleanly. For a radar
that runs **repeatedly on a schedule**, this is a non-starter. Free is defensible **only**
for a one-off, tiny, manual pull where breakage and a possible ban don't matter.

**Verdict:** do not build the standing X source on a free scraper. If a zero-budget
proof-of-concept is ever needed, `twikit` with a throwaway account is the least-bad
choice — explicitly time-boxed and disposable.

---

## 3. Decision

> **Build one query-driven X adapter against `twitterapi.io`.** Keep the **official X API
> (pay-per-use)** as a documented swap-in if ToS-cleanliness becomes a hard requirement.
> Do **not** ship any free-scraper path as a standing source.

Rationale: cheapest, no own-account ban risk, full + historical search, REST → cleanest
`RawItem` mapping. The official API's only advantage (first-party/compliant) is
outweighed by 33× cost and a 7-day search horizon for new developers.

---

## 4. Scope — don't limit query *types*, limit *spend*

A search API removes any reason to restrict *what kind* of query we run. The real
governor is a **budget cap**, not the query shape. One adapter, one config, all of:

| Query type | Example | Why |
|------------|---------|-----|
| Cashtags / hashtags | `$NIFTY $BANKNIFTY #FnO #optionsselling #algotrading` | Broad community pulse |
| Free-text keywords | `"kite api"`, `"banknifty expiry"`, `openalgo` | Dev/algo chatter w/o tags |
| Handle timelines | broker / finfluencer / algo-dev accounts | Authority + Rising Voices |
| Replies / quotes | replies under the above | Richer engagement graph for Rising Voices (costs more reads) |

All flow through the **same** `advanced_search` + user-tweets endpoints; the budget guard
(not the query menu) is what bounds cost.

---

## 5. Adapter design (fits the existing architecture)

The pipeline is source-agnostic: `RawItem` → store (id + content-hash dedup) → dedupe →
prefilter → Haiku classify → trend → Actions → Rising Voices. Adding X touches **three
files** and **zero pipeline stages**.

### 5.1 New file — `social_pulse/sources/twitter.py`

Mirror `sources/reddit.py`. Public entry `fetch_twitter(cfg) -> list[RawItem]`.

- Read `TWITTERAPI_IO_KEY` from env (loaded from `.env`, same as the Anthropic key).
- Build queries from `cfg["twitter"]` (cashtags, hashtags, keywords, handles, lang, days).
- Call `GET https://api.twitterapi.io/twitter/tweet/advanced_search`
  with `query`, `queryType=Latest`, and cursor pagination.
- Use handle endpoints for timelines; optionally fetch replies for flagged tweets.
- **Bounded pagination:** cap pages per query *and* slice by date window (`since:`/
  `until:`) to dodge the upstream cursor-dup bug; rely on store dedup for residual dups.
- **Budget guard:** stop once `max_tweets` (or an estimated `$` cap) is hit; `log()` what
  was skipped so truncation is never silent.

### 5.2 `RawItem` field mapping

| `RawItem` field | X source value |
|-----------------|----------------|
| `source` | `"twitter"` |
| `source_type` | `"tweet"` \| `"reply"` |
| `external_id` | tweet id |
| `text` | tweet full text |
| `author` | `@handle` |
| `url` | `https://x.com/<handle>/status/<id>` |
| `created_at` | tweet timestamp (UTC) |
| `engagement` | `{score: likes, replies: reply_count, retweets, quotes, views}` |
| `raw` | `{handle, hashtags, cashtags, lang, query, is_reply, conversation_id, ...}` |

> **Rising-Voices note:** `influencers.py` reads `raw["subreddit"]` for the "communities /
> breadth" signal. For X, populate an analogous key (e.g. `raw["channel"] = "x"` or the
> query/cashtag bucket) so breadth scoring stays meaningful across sources. The
> audience/relevance logic is keyword-based and works on tweet text unchanged.

### 5.3 Wiring

- `app.py` + `run.py` `ingest()`: add `elif s == "twitter": items += fetch_twitter(cfg)`.
- Sidebar: add `"twitter"` to the **Live sources** multiselect; show a small query-config
  panel (cashtags/hashtags/keywords/handles, days, `max_tweets`) like the Reddit panel.
- `requirements`: just `requests`/`httpx` (no SDK needed — plain REST).

### 5.4 `config.yaml` shape (proposed)

```yaml
twitter:
  enabled: false                 # opt-in; off by default so no accidental spend
  cashtags:   ["$NIFTY", "$BANKNIFTY", "$FINNIFTY", "$SENSEX"]
  hashtags:   ["#FnO", "#optionsselling", "#algotrading", "#banknifty"]
  keywords:   ["kite api", "banknifty expiry", "openalgo", "dhan api"]
  handles:    []                 # broker / finfluencer / algo-dev accounts to track
  lang:       "en"
  days:       7                  # scrape + working-set window (same semantics as Reddit)
  query_type: "Latest"           # Latest = chronological sweep; Top = engagement-ranked
  max_tweets: 2000               # HARD budget guard (≈ $0.30 at $0.15/1k)
  include_replies: false         # true = richer Rising-Voices signal, more reads
```

---

## 6. Cost model

At twitterapi.io's **$0.15 / 1k reads**:

| Pull | Tweets | Cost |
|------|--------|------|
| Small daily sweep | 2,000 | ~$0.30 |
| Healthy daily radar | 6,000 | ~$0.90 |
| Big backfill | 20,000 | **~$3** |

Same 20,000 reads on the **official API** at $0.005 ≈ **$100** (and only within a 7-day
window). The `max_tweets` guard + per-run `log()` of skipped queries keeps spend
predictable and visible.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Cursor pagination dup/early-stop (upstream) | Date-sliced bounded windows + content-hash store dedup |
| Provider outage / shutdown (cf. socialdata.tools, which **shut down** in 2026) | Adapter is thin REST; keep official-API swap-in documented (§3); provider URL/key in config |
| Cost runaway | `max_tweets` hard cap + `$`-estimate guard + opt-in `enabled: false` default |
| ToS sensitivity | If compliance becomes mandatory, switch to official pay-per-use (accept 7-day horizon + 33× cost) |
| Provider terms drift | This doc is dated; re-verify §2 before relying on prices/limits |

---

## 8. Status & next step

- **Status:** researched + designed; **not yet implemented** (awaiting go-ahead + a
  `TWITTERAPI_IO_KEY`).
- **To build:** `sources/twitter.py`, `ingest()` wiring (app + CLI), sidebar source +
  query panel, `config.yaml` block, README note. Est. small — no pipeline changes.
- **Open inputs from product:** the **handle list** (which broker/finfluencer/algo-dev
  accounts to track) and the default **`max_tweets` budget** per run.

---

## 9. Sources (verified 2026-06-29)

- X API pricing 2026 — https://api.sorsa.io/blog/twitter-api-pricing-2026
- Twitter/X API pricing tiers $0–$42K — https://www.xpoz.ai/blog/guides/understanding-twitter-api-pricing-tiers-and-alternatives/
- X API official docs — https://docs.x.com/x-api/introduction
- Searching tweets via API 2026 — https://api.sorsa.io/blog/twitter-search-api
- Best Twitter scrapers — what works/breaks — https://api.sorsa.io/blog/twitter-scrapers
- How to scrape X with Python 2026 (Scrapfly) — https://scrapfly.io/blog/posts/how-to-scrape-twitter
- twitterapi.io Advanced Search docs — https://docs.twitterapi.io/api-reference/endpoint/tweet_advanced_search
- twitterapi.io pricing — https://twitterapi.io/pricing
- twitterapi.io vs Apify — https://twitterapi.io/compare/vs-apify
- Apify cheapest tweet scraper — https://apify.com/kaitoeasyapi/twitter-x-data-tweet-scraper-pay-per-result-cheapest
- twikit (GitHub) — https://github.com/d60/twikit
