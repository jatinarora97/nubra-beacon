# Beacon API — consumer contract (v1, 2026-08-18)

Read-only JSON over REST. Base: `http://<beacon-host>:8400/api/beacon/v1`
(LAN/VPN only). Built for MCP agents: one endpoint = one tool.

## Auth

Header `X-API-Key: nbk_...` on every request (`Authorization: Bearer nbk_...`
also accepted). One key per consumer team/tool — ask the Beacon owner (minted
on the dashboard's API-access page; the secret is shown once). 401 = missing/
revoked key. 60 requests/min per key; 429 carries `Retry-After`. 503 = the
API is switched off.

## Conventions (identical on every endpoint)

- Timestamps: ISO8601 UTC in and out.
- Default window: rolling last 24h. Override with `since`/`until` (ISO8601;
  date-only means midnight UTC).
- List responses: `{ "results": [...], "next_cursor": "..."|null }` (+
  `"window"` echo where a range applies). Pass `next_cursor` back verbatim to
  page; ordering is stable (pinned to our ingest time). Page size `limit`
  default 25, max 200.
- Sources: `twitter, reddit, youtube, github, community_forum, app_review,
  instagram`. Aliases accepted on input: `x→twitter, forum→community_forum,
  review→app_review`. `sources=` takes a comma list.
- Full data by default: complete text (incl. Instagram TRANSCRIPT/ON-SCREEN
  blocks), all enrichment, `raw` platform passthrough (internal pipeline
  bookkeeping removed).
- Valid enum values: never guess — `GET /taxonomy` lists live topics,
  intents, audiences, issue_types, brokers, sources.
- Fields we deliberately do NOT provide: no `relevance_score` (use
  `engagement->score`, `sentiment`, noise pre-filtered), no `severity` on
  issues (use `mention_count` + engagement).

## Endpoints

### Corpus
| | |
|---|---|
| `GET /items` | filters: `sources, since, until, topic, intent, audience, broker, q (substring), min_engagement, sentiment_min/max, include_noise (default false), limit, cursor`. Row: item_id, source, source_type, external_id, thread_id, parent_id, text, lang, url, created_at, ingested_at, engagement{score,native}, author, topic_key, intent, audience, sentiment, entities{broker,issue_type,feature_phrase,summary}, is_noise, raw |
| `GET /items/search` | `q` REQUIRED, websearch syntax: `"option chain" OR scam -telegram`. Adds `match_snippet` (matched terms in `<b>`). Same other params as /items |
| `GET /items/{source}/{external_id}` | full single item + `thread_siblings`. `external_id` = the platform's own id, copied from any /items row (tweet id, reddit t3_..., yt_video_..., instagram shortCode) |

### People
| | |
|---|---|
| `GET /authors` | `sources, since, until, q (handle), min_items, limit, cursor` → handle, followers, verified, first/last_seen_at, item_count, avg_engagement, top_topics[] |
| `GET /authors/{source}/{handle}` | profile + 20 most recent items |

### Intelligence
| | |
|---|---|
| `GET /trends` | topics moving in the window: counts + deltas (same math as the dashboard Trends page) |
| `GET /broker-issues` | `broker?` — broker x issue_type segments with counts + quotes |
| `GET /feature-requests` | `min_days?` — merged asks with exactly-once mention counts |
| `GET /nubra-mentions` | brand mentions + KPIs (negatives counted, listed under broker-issues) |
| `GET /topic-suggestions` | machine-discovered themes awaiting human accept/reject |

### Action layer
| | |
|---|---|
| `GET /opportunities` | `status?, min_priority?` — scored actionables (bar 60) with reasons, replies, status |
| `GET /drafts` | opportunities that carry a ready compliant draft (brand_reply / rep_reply) |
| `GET /briefs` | `day?` (default latest built day) — content briefs: hook, beats, caption, hashtags, platform, why |
| `GET /social-recommendations` | `segment?, status?, platform?` — social engine posts, grounding-version stamped |
| `GET /roundups` | `period=daily|weekly, day?` — the composed roundup payloads |

### Ops + meta
| | |
|---|---|
| `GET /runs` | pipeline freshness per stage x source: watermark, last success/error, items_last_run |
| `GET /source-health` | `live=true` adds real reachability/auth probes per collector |
| `GET /watch-sources` | everything Beacon listens to (subreddits, handles, queries, instagram accounts) |
| `GET /taxonomy` | all valid filter enum values |
| `GET /grounding` | Nubra's real capabilities (versioned; ground product claims here) |
| `GET /usage` | `days?` — Beacon's own LLM spend rollup |

## Errors

`401` bad/missing key · `404` unknown item/author · `422` bad params
(invalid source, cursor, ISO date, since>=until) · `429` rate limit ·
`503` API disabled. Bodies: `{"detail": "..."}`.

## Quickstart

```
curl -s -H "X-API-Key: $KEY" \
  "http://<host>:8400/api/beacon/v1/items/search?q=%22margin%20penalty%22%20OR%20%22peak%20margin%22&since=2026-08-11" | jq .
```
