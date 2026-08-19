# Beacon API — consumer guide (v1)

Working call in 30 seconds:

```bash
export KEY="<your-api-key>"        # provided by the Beacon owner; only secret in this doc
export B="http://mcp-server:8101/api/beacon/v1"

curl -s -H "X-API-Key: $KEY" "$B/taxonomy"
```

Host: `mcp-server:8101` on the office network/VPN (not internet-exposed).
If `mcp-server` doesn't resolve for you, use the VM's IP — same port.

## Rules that apply to EVERY endpoint

1. Auth: `X-API-Key: $KEY` header on every request (`Authorization: Bearer`
   also accepted). Missing/revoked key → 401.
2. Rate limit: 60 requests/min per key → 429 with a `Retry-After` header.
   Poll politely; don't parallel-hammer.
3. Time: ISO8601 UTC everywhere. Default window = last 24h. Override:
   `?since=2026-08-11&until=2026-08-18` (date-only = midnight UTC).
4. Lists return `{"results": [...], "next_cursor": "..."|null}` — pass
   `next_cursor` back verbatim for the next page. `limit` default 25, max 200.
5. Sources: `twitter reddit youtube github community_forum app_review
   instagram`. Input aliases: `x→twitter forum→community_forum
   review→app_review`. Multi: `sources=twitter,instagram`.
6. Never guess enum values — `GET /taxonomy` lists the real topics, intents,
   audiences, issue_types, brokers.
7. Errors are JSON `{"detail": "..."}`: 401 auth · 404 not found · 422 bad
   params · 429 rate limit · 503 API switched off.

## Raw content — what people posted

**GET /items** — posts + comments, filtered. Full text, full enrichment, raw
platform payload.
```bash
curl -s -H "X-API-Key: $KEY" "$B/items?sources=reddit&since=2026-08-11&limit=10"
curl -s -H "X-API-Key: $KEY" "$B/items?broker=zerodha&intent=complaint"
curl -s -H "X-API-Key: $KEY" "$B/items?topic=trading_scams&sentiment_max=-0.5"
```
Each row: `item_id source source_type external_id thread_id parent_id text
lang url created_at ingested_at engagement{score,native{likes,comments,...}}
author topic_key intent audience sentiment
entities{broker,issue_type,feature_phrase,summary} is_noise raw`.
Notes: `entities.summary` = Beacon's one-line read. Instagram `text` includes
`TRANSCRIPT:` (reel speech, English) / `ON-SCREEN:` (carousel slides) blocks.
Noise is pre-filtered; add `include_noise=true` to see it. Other filters:
`q` (substring), `min_engagement`, `sentiment_min`.

**GET /items/search** — full-text with `OR`, quoted phrases, `-exclusions`.
```bash
curl -s -H "X-API-Key: $KEY" "$B/items/search?q=%22margin%20penalty%22%20OR%20%22peak%20margin%22&since=2026-08-11"
```
Same rows as /items + `match_snippet` (matched words wrapped in `<b>`).

**GET /items/{source}/{external_id}** — one item in full + its thread.
```bash
curl -s -H "X-API-Key: $KEY" "$B/items/instagram/DJJFNA-BV7f"
```
Returns `{"item": {...}, "thread_siblings": [...]}`. `external_id` = the
platform's own id, copied from any /items row (tweet id, reddit `t3_...`,
instagram shortCode).

## People — who posts

**GET /authors** — deduped people with aggregates.
```bash
curl -s -H "X-API-Key: $KEY" "$B/authors?min_items=3&since=2026-08-01"
```
Rows: `source handle followers verified first_seen_at last_seen_at
item_count avg_engagement top_topics[]`.

**GET /authors/{source}/{handle}** — one person + their 20 latest items.
```bash
curl -s -H "X-API-Key: $KEY" "$B/authors/instagram/stockburner_official"
```

## Intelligence — what Beacon concluded (same math as its dashboard)

```bash
curl -s -H "X-API-Key: $KEY" "$B/trends?since=2026-08-12"            # moving topics: count, momentum, per-window deltas
curl -s -H "X-API-Key: $KEY" "$B/broker-issues?broker=zerodha"       # broker x issue_type: counts, severity, sentiment
curl -s -H "X-API-Key: $KEY" "$B/feature-requests?since=2026-08-01"  # merged asks with exactly-once mention counts
curl -s -H "X-API-Key: $KEY" "$B/nubra-mentions"                     # brand mentions + KPIs
curl -s -H "X-API-Key: $KEY" "$B/topic-suggestions"                  # machine-discovered themes awaiting human accept
```

## Action layer — what Beacon recommends

```bash
curl -s -H "X-API-Key: $KEY" "$B/opportunities?min_priority=60"      # scored actionables: priority, insight, status, replies
curl -s -H "X-API-Key: $KEY" "$B/drafts"                             # only opportunities carrying a ready compliant draft
curl -s -H "X-API-Key: $KEY" "$B/briefs"                             # content briefs (day=YYYY-MM-DD; default latest)
curl -s -H "X-API-Key: $KEY" "$B/social-recommendations?platform=linkedin"
curl -s -H "X-API-Key: $KEY" "$B/roundups?period=weekly"             # daily|weekly composed roundup payloads
```
Opportunity rows: `id source thread_id day priority insight brand_reply
rep_reply recommended_timing status url title velocity last_seen`.

## Ops + meta — freshness, config, spend

```bash
curl -s -H "X-API-Key: $KEY" "$B/runs"                    # per stage x source: watermark, last success/error, items_last_run
curl -s -H "X-API-Key: $KEY" "$B/source-health?live=true" # + real reachability probes per collector
curl -s -H "X-API-Key: $KEY" "$B/watch-sources"           # everything Beacon listens to (subs, handles, queries, accounts)
curl -s -H "X-API-Key: $KEY" "$B/taxonomy"                # all valid enum values for filters
curl -s -H "X-API-Key: $KEY" "$B/grounding"               # Nubra's verified capabilities (31 features, versioned)
curl -s -H "X-API-Key: $KEY" "$B/usage?days=7"            # Beacon's own LLM spend rollup
```
Note `/grounding`: ground any Nubra product claim on these rows — it's the
same catalog Beacon's own compliant drafts cite.

## Pagination example (works on every list)

```bash
P1=$(curl -s -H "X-API-Key: $KEY" "$B/items?limit=50")
CUR=$(echo "$P1" | python3 -c "import json,sys; print(json.load(sys.stdin)['next_cursor'])")
curl -s -H "X-API-Key: $KEY" "$B/items?limit=50&cursor=$CUR"
```
`next_cursor: null` = last page. Ordering is pinned to ingest time — pages
stay stable even while new data arrives.

## Building an agent on this?

One endpoint = one tool. Suggested loop: `/taxonomy` once (learn the enums) →
answer "what's happening" from trends/broker-issues/feature-requests/
opportunities → fetch receipts from /items only when quoting. `/runs` tells
you how fresh the data is before you trust it.

## Verify your setup end to end

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: $KEY" "$B/taxonomy"   # want 200
curl -s -o /dev/null -w "%{http_code}\n" "$B/taxonomy"                        # want 401 (auth works)
```

Data caveats, honest: Reddit has a gap 2026-08-10 → 2026-08-19 (upstream
block, since fixed). No `relevance_score`/`severity` fields exist — use
`engagement.score`, `sentiment`, `mention_count`. Fields Beacon doesn't
compute are absent, not faked.
