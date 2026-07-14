# New Source Collectors Architecture

## Purpose

This document explains the optional source collectors added to Beacon:

- YouTube
- GitHub
- Broker communities
- App/Play Store reviews

These sources are added as independent modules so they do not disturb the existing Reddit/X pipeline.

---

## Design Principle

Existing sources remain unchanged.

New sources are:

- disabled by default
- config-gated
- failure-isolated
- emitted through the same `SocialItem` contract
- stored in the same `social_items` table once enabled

This lets Beacon collect richer market/product intelligence without making the current scraper fragile.

---

## Flow

```text
registry.yaml
    ↓
extra_sources.run()
    ↓
source-specific fetcher
    ↓
SocialItem
    ↓
insert_item_if_absent()
    ↓
existing clean → enrich → aggregate → recommend pipeline
```

---

## Source Modules

| Source | File | Data collected |
|---|---|---|
| YouTube | `community/scrape/youtube.py` | Video title, description, stats, comments |
| GitHub | `community/scrape/github_public.py` | Public issues/discussions-like issue results for API/algo demand |
| Broker communities | `community/scrape/broker_communities.py` | Public forum posts/comments from broker communities |
| App reviews | `community/scrape/app_reviews.py` | Apple RSS reviews when app IDs exist; Google Play listing snapshots |
| Orchestrator | `community/scrape/extra_sources.py` | Runs optional collectors and stores rows |

---

## Config Location

All new source settings live in:

```text
community/config/registry.yaml
```

Each source has:

```yaml
enabled: false
```

Set it to `true` only after fetch-only tests pass.

---

## Credentials

| Source | Credential | Required |
|---|---|---|
| YouTube | `YOUTUBE_API_KEY` | Yes, when YouTube is enabled |
| GitHub | `GITHUB_TOKEN` | Optional |
| Broker communities | None | No |
| App/Play Store | None for current mode | No |

Credentials should be stored in `.env`, not in Git.

---

## Source Quality Notes

### GitHub

GitHub search is useful for API/algo/developer signals but can be noisy.

The collector includes a relevance gate:

- allow terms: trading API, websocket, order placement, broker APIs, NSE/BSE, broker names
- deny terms: spam/adult/casino/noise terms
- minimum relevance score from config

Tune this in:

```yaml
sources:
  github:
    relevance:
      min_score: 2
      allow_terms: [...]
      deny_terms: [...]
```

### YouTube

YouTube collects text only:

- video title
- description
- view/like/comment counts
- comment text

It does not fetch thumbnails or media.

The collector stores partition labels such as:

- retail
- api_algo
- competitors

### Broker communities

Broker communities currently support:

- Discourse-style forums
- NodeBB-style forums
- sitemap fallback

Some communities may block requests or change endpoints. Failures are isolated and should not break the scrape stage.

### App reviews

Apple public reviews work when numeric Apple app IDs are configured.

Google Play currently emits listing snapshots. A stronger Google Play review collector can be added later if required.

---

## Fetch-Only Testing

Use:

```powershell
python scripts\test_collectors_fetch_only.py
```

Single source:

```powershell
python scripts\test_collectors_fetch_only.py --source github
python scripts\test_collectors_fetch_only.py --source youtube
python scripts\test_collectors_fetch_only.py --source broker_communities
python scripts\test_collectors_fetch_only.py --source app_reviews
```

Health summary:

```powershell
python scripts\source_health_check.py
```

---

## Dashboard Expectations

Once DB ingest is enabled, new source rows should become available through existing Beacon views:

- Explore
- Trends
- Features
- Broker issues
- Nubra mentions
- Opportunities

Future dedicated pages can add:

- Source health
- YouTube insights
- Developer/API demand
- Competitor community issues
- Social posting recommendations
- Design review intelligence

