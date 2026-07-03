# Social Pulse — Community Discussion Ingestion & Daily "Rising Topics" Brief

_Architecture doc · 2026-06-14 · author: pipeline design pass_

## 1. Goal

Capture the live pulse of the Indian stock-market community — **F&O traders, API/algo
traders, and developers trying to trade via AI** — across the platforms where they
actually talk, filter out the noise, surface **emergent rising topics**, and produce a
**daily brief** so Nubra's social channels can be *first* to start the relevant
conversation.

Constraints (from product):
- **Free + ToS-compliant** wherever possible. Flag anything grey.
- Output = a **daily ranked "rising topics" brief** (not live alerting, not just a store).
- Audience focus, in priority order: F&O / options, API-algo traders, AI-trading devs,
  then serious discretionary traders.

## 2. Source strategy (decided)

| Tier | Source | Access | Cost | ToS posture | Signal for our audience |
|------|--------|--------|------|-------------|--------------------------|
| **1** | **Telegram** | Telethon (MTProto, user session via `my.telegram.org`) | Free | **Grey** — read **public** channels only, dedicated number, rate-limited | Highest. F&O tips, options selling, algo/API channels, "AI trading" groups |
| **1** | **Reddit** | Official API + PRAW (OAuth) | Free (100 QPM/client) | **Clean** | High. Serious + retail; comments carry the strategy/API talk |
| **2** | **Broker dev forums** | Discourse JSON API (`<url>.json`) | Free | **Clean** (public read) | Highest for *API/algo devs* — exactly what they struggle with |
| **2** | **GitHub** | REST/GraphQL API (token) | Free (5k req/hr) | **Clean** | High for *AI/algo devs* — issues = real pain points |
| **3** | **Discord** | Read-only bot in servers we join | Free | **Conditional** — bot must be invited; no self-bot scraping | Medium-high. Quant/algo communities |

**Explicitly out of scope: Twitter/X.** No usable free tier post-2023; full coverage is a
money pit. Revisit later as a *curated-list* feed only, never a firehose.

> **Update 2026-06-29 — reversed.** See `social-pulse-twitter-x-ingestion-2026-06-29.md`.
> X is now worth ingesting via a **paid managed API** (`twitterapi.io`, ~$0.15/1k tweets,
> historical search, no own-account ban risk). All **free** scraping paths are confirmed
> structurally doomed in 2026 (login-gated, token/`doc_id` rotation every 2–4 weeks,
> account+IP bans). Drops in as a source-agnostic `RawItem` adapter — no pipeline changes.

> ToS flags are restated in §8. Treat them as gating, not footnotes.

## 3. Where this lives

This is a **new ingestion layer that feeds the existing `intelligence_store`** (see
`migrations/007_intelligence_store.sql`). It is *another enrichment source* alongside the
market-data memory the reports/notifications already read — not a separate system.

```
nubraai-comms/
  social/                     # NEW module
    __init__.py
    sources/                  # one adapter per platform, common output contract
      base.py                 # SourceAdapter ABC -> yields RawItem
      reddit_source.py        # PRAW
      telegram_source.py      # Telethon
      discourse_source.py     # broker dev forums (Zerodha/Upstox/Dhan/AngelOne/Fyers)
      github_source.py        # issues/discussions on broker API wrappers
      discord_source.py       # discord.py read-only bot
    pipeline/
      normalize.py            # RawItem -> canonical schema + hash
      dedupe.py               # cross-source near-dup collapse
      prefilter.py            # cheap keyword/lang gate (kills ~70% before LLM)
      classify.py             # Haiku batch: audience/topic/sentiment/is_noise
      cluster.py              # embeddings + HDBSCAN / BERTopic -> emergent topics
      trend.py                # velocity + cross-source spread scoring
      brief.py                # render daily "rising topics" brief
    config/
      sources.yaml            # channel/subreddit/repo/forum lists + weights
    runner.py                 # cron entrypoint (mirrors comms runner.py)
```

Config lives in YAML like the rest of `nubraai-comms/config/`. LLM calls reuse
`intelligence/llm/` (Anthropic client, pricing, langfuse recorder). DB + S3 reuse `lib/`.

## 4. Canonical schema

Every adapter normalizes to one `RawItem` before anything else touches it:

```python
RawItem = {
  "source":      str,    # 'reddit' | 'telegram' | 'discourse:zerodha' | 'github:zerodha/pykiteconnect' | 'discord'
  "source_type": str,    # 'post' | 'comment' | 'message' | 'topic' | 'issue'
  "external_id": str,    # platform-native id (for idempotent upsert)
  "author":      str,    # hashed/pseudonymous where required
  "text":        str,
  "url":         str | None,
  "created_at":  datetime (UTC),
  "engagement":  {"score": int, "replies": int, "reactions": int},  # best-effort
  "raw":         dict,   # platform payload, for debugging
  "content_hash": str,   # sha256 of normalized text — dedupe key
}
```

### Storage in `intelligence_store`
Reuse the existing per-day JSONB table. Proposed keys:

| category | sub_key | data |
|----------|---------|------|
| `social.raw` | `<source>` | rolled-up list/count of items ingested that day (audit) |
| `social.topics` | `''` | clustered topics with members, velocity, sentiment |
| `social.brief` | `''` | the rendered daily "rising topics" brief (final artifact) |

`source_trigger` = `'social_ingest'`. UPSERT on PK keeps re-runs idempotent (same pattern
as the market triggers). Raw item bodies that we don't need long-term get a short
`expires_at`; the topic/brief rows are retained.

> If raw volume is high, raw items go in a dedicated `social_items` table (migration 029)
> instead of stuffing JSONB; the *derived* topic/brief rows stay in `intelligence_store`
> so downstream renderers read from one place. Decide at build time based on volume.

## 5. Pipeline (4 stages)

```
ingest (per-source cron) ─▶ normalize+dedupe ─▶ prefilter ─▶ classify(LLM) ─▶ cluster ─▶ trend ─▶ brief
```

1. **Ingest** — each adapter pulls on its own cadence (Telegram live-ish, Reddit
   new/hot/rising, forums/GitHub hourly). Adapters are stateless; they yield `RawItem`s.

2. **Normalize + dedupe** — canonicalize, hash, collapse near-dupes. The same tip is
   copy-pasted across 10 Telegram channels — dedupe by `content_hash` + fuzzy (MinHash/
   SimHash) so one viral message counts once but *cross-source spread is still recorded*.

3. **Prefilter (cheap, no LLM)** — regex/keyword gate (tickers, `expiry`, `straddle`,
   `kite api`, `algo`, `backtest`, `openalgo`, …) + language filter. Drops ~70% of junk
   before any token spend.

4. **Classify (LLM, batched)** — **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) — the
   cheap/fast tier, ideal for classification. Batch dozens of items per call. Output per
   item: `audience` (retail / serious / algo / dev), `topic_label`, `sentiment`,
   `is_question`, `is_noise`. Cost tracked via existing `migrations/013_llm_usage.sql`.

5. **Cluster** — embed surviving texts, cluster with **BERTopic** (or
   `sentence-transformers` + HDBSCAN) to discover themes we *didn't* pre-define.

6. **Trend** — rank clusters by **velocity** (mentions now vs 24h/7d baseline) ×
   **cross-source spread** (a topic on Reddit + Telegram + a dev forum at once = real
   pulse, not one loud account) × audience weight. This ranked list is the brief.

7. **Brief** — render top-N rising topics with: topic, why-now, representative quotes
   (linked), sentiment, suggested angle for our post. Deliver via the existing
   push/email rails (reuse `intelligence/email_sender.py` pattern).

## 6. Per-source build notes

- **Reddit (PRAW):** OAuth "script" app, free 100 QPM. Poll `new`/`hot`/`rising`/`top(day)`
  on target subs; pull comment trees on high-velocity threads. `rising` velocity is itself
  a pulse signal. Comment reading is allowed under the API. Target subs (validate at build):
  `r/IndianStreetBets`, `r/IndiaInvestments`, `r/DalalStreetTalks`, `r/IndianStockMarket`,
  `r/StockMarketIndia`, and `r/algotrading` + `r/options` for the dev/quant slice.
- **Telegram (Telethon):** `api_id`/`api_hash` from `my.telegram.org`; **user** session
  (bots can't read arbitrary channel history). Join **public** channels only, throttle
  hard (FloodWait-aware), dedicated number. Discover channels via in-app search + public
  directories; seed a list, expand from forwards/mentions.
- **Broker dev forums (Discourse):** Zerodha `TradingQnA` + Kite Connect forum, and the
  Upstox/Dhan/AngelOne/Fyers communities are Discourse — append `.json` to any URL for
  structured data (`/latest.json`, `/t/<slug>/<id>.json`). Public read, no key needed for
  reasonable rates. Richest source for *what API/algo traders are stuck on*.
- **GitHub:** authenticated REST/GraphQL (5k req/hr). Mine issues + Discussions on broker
  API wrappers: `pykiteconnect`, `upstox` SDKs, `dhanhq`, `fyers-api`, `openalgo`, etc.
  Open/recent issues = live developer pain → great "we hear you" post fodder.
- **Discord:** official bot, **invited** to servers (no self-bots / no scraping servers
  we're not in — that violates ToS and risks bans). Read-only intent on public algo/quant
  servers. Medium effort; do after Tier 1+2 prove out.

## 7. Cadence & delivery

- Ingest crons staggered per source (see `runner.py`). Classify/cluster/trend run once in
  an **early-morning batch**; brief renders ~07:00 IST so social team has it pre-market.
- Idempotent: re-running a day re-UPSERTs the same `intelligence_store` rows.

## 8. ToS & risk — read before building

- **Telegram:** scraping is a **grey area**. Mitigations: public channels only, dedicated
  number, aggressive rate-limiting, respect FloodWait, never scrape private groups we
  aren't legitimately in. Accept some ban risk on the scraping account.
- **Discord:** only via an **invited bot**. Self-botting / scraping un-joined servers
  violates ToS — do not.
- **Reddit / GitHub / Discourse:** clean public-API/JSON read paths. Respect rate limits
  and `robots`/API terms.
- **PII / compliance:** pseudonymize authors; store text for topic intel, not profiling of
  named individuals. We surface *topics*, not people.

## 9. Build plan (phased — doc → vertical slice → expand)

- **Phase 0 (this doc):** architecture agreed.
- **Phase 1 — highest-ROI vertical slice:** Telegram + Reddit → normalize/dedupe →
  prefilter → Haiku classify → simple velocity ranking → daily brief. Proves the whole
  chain end-to-end on the two best free sources. *(blend of "prototype" + "spike highest-ROI source")*
- **Phase 2:** add Discourse (broker forums) + GitHub adapters — the API/algo-dev signal.
- **Phase 3:** add BERTopic clustering (replace keyword topics) + cross-source spread
  scoring; add Discord bot.
- **Phase 4:** wire brief into push/email delivery rails; tune weights from feedback.

## 10. Open decisions for build time

1. Raw items in `intelligence_store` JSONB vs a dedicated `social_items` table (volume call).
2. Embedding model: local `sentence-transformers` (free) vs hosted — start local.
3. Brief delivery channel: email vs push vs internal Slack — confirm with social team.
