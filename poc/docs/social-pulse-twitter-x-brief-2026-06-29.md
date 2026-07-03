# Social Pulse — Twitter / X Ingestion (condensed)

_Brief · 2026-06-29 · sections 1–4 only. Full detail (cost model, adapter design,
risks, sources) lives in `social-pulse-twitter-x-ingestion-2026-06-29.md`._

## 1. Why X at all (signal for our audience)

Indian "FinTwit" is where a large slice of F&O / options / algo-dev conversation happens
in real time — cashtags (`$NIFTY`, `$BANKNIFTY`), expiry-day chatter, broker outage
complaints, algo/API tips, and the finfluencer layer we care about for **Rising Voices**.
It is higher-velocity and more public-figure-driven than Reddit, which makes it strong
for both **Trends** (what's spiking now) and **Rising Voices** (who's driving it).

The cost-benefit changed in our favor for two reasons:
1. Managed scraping APIs matured and are now **cheap** ($0.05–0.25 / 1k tweets).
2. Our pipeline already abstracts the source, so integration is small and low-risk.

## 2. The 2026 access landscape (verified)

### 2A. PAID — the paths that actually hold up

| Option | Cost (2026) | Auth burden on us | Search scope | Reliability | ToS posture |
|--------|-------------|-------------------|--------------|-------------|-------------|
| **twitterapi.io** *(recommended)* | **~$0.15 / 1k reads** ($0.00015/tweet), no floor, no cap | **None** — they run accounts/proxies | Full operator grammar, **incl. historical**; `Latest` or `Top` | ~0.5s median, claims 99.99% uptime | Grey (scraping behind their infra; risk is theirs) |
| **Official X API (pay-per-use)** | **$0.005/post read**, $0.010/author read, $0.001 "owned"; cap 2M/mo | Dev account + credits | **Recent only (7 days)** on pay-per-use; full archive = Pro/Enterprise | First-party, stable | **Clean** |
| GetXAPI | ~$0.05 / 1k | None | Search operators | Managed | Grey |
| Apify "kaito" scraper | ~$0.25 / 1k | None | Search/handle | Managed actor | Grey |
| Sorsa API | **$49/mo flat** | None | Search/timeline | Managed | Grey |

- Official API: pay-per-use is the **default since 2026-02-06**; Basic/Pro **closed to new
  signups**; free tier is useless for collection (~100 reads/mo, no search). New devs
  effectively get **7-day** search only (full archive needs Pro $5k / Enterprise ~$42k).
- twitterapi.io: full Twitter operator grammar incl. **historical** search → we can query
  anything. One caveat: X's cursor pagination is flaky upstream — deep pulls can dup/stop
  early, so page in **bounded windows** and lean on content-hash dedup.

### 2B. FREE — structurally doomed (not merely inconvenient)

**Alive but fragile:** `twikit`, `twscrape`, `Tweety`, `Scweet`. **Dead:** `snscrape`,
`Twint`, `Nitter`.

Platform-level locks, not bugs you can out-engineer cheaply:
1. **Login-gated** — search + most timelines need an authenticated session (a real
   account → exactly what gets banned).
2. **Guest tokens expire** (hours); acquisition shifts every few weeks.
3. **GraphQL `doc_id`s rotate every 2–4 weeks** → scraper breaks; ~**10–15 hrs/month** of
   break-fix.
4. **Account + IP bans at volume** → need residential proxies + rotating fingerprints +
   disposable accounts.

True "free" cost = proxy bill + dying burner accounts + permanent maintenance, for **less
reliable** data than a **$3 API call**. A non-starter for a standing radar; defensible
only for a one-off, tiny, manual pull.

## 3. Decision

> **Build one query-driven X adapter against `twitterapi.io`.** Keep the **official X API
> (pay-per-use)** as a documented swap-in if ToS-cleanliness becomes a hard requirement.
> Do **not** ship any free-scraper path as a standing source.

Rationale: cheapest, no own-account ban risk, full + historical search, REST → cleanest
`RawItem` mapping. The official API's only advantage (first-party/compliant) is outweighed
by 33× cost and a 7-day search horizon for new developers.

## 4. Scope — don't limit query *types*, limit *spend*

A search API removes any reason to restrict *what kind* of query we run. The real governor
is a **budget cap**, not the query shape. One adapter, one config, all of:

| Query type | Example | Why |
|------------|---------|-----|
| Cashtags / hashtags | `$NIFTY $BANKNIFTY #FnO #optionselling #algotrading` | Broad community pulse |
| Free-text keywords | `"kite api"`, `"banknifty expiry"`, `openalgo` | Dev/algo chatter w/o tags |
| Handle timelines | broker / finfluencer / algo-dev accounts | Authority + Rising Voices |
| Replies / quotes | replies under the above | Richer engagement graph (costs more reads) |

All flow through the **same** search endpoint; the budget guard (not the query menu)
bounds cost.
