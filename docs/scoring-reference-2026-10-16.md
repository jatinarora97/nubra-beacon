# Scoring reference: every score, formula and threshold

State of the code on 2026-10-16. Line numbers drift; search for the function names. Items marked **(registry)** are
tunable in `community/config/registry.yaml`; everything else is fixed in code. `CLAUDE.md` locks two of them as
measured calibrations: **action bar 60** and **centroid τ 0.86** (re-tune only with production feedback data).

Values that come from a model, not a formula: intent, topic, `is_noise`, sentiment (-1..1), audience, entities, the
compliance verdicts, and the `priority_score` (0..100) the model writes on content briefs and queue items.

## Contents
1. [Engagement score](#1-engagement-score)
2. [Opportunity priority](#2-opportunity-priority-the-main-score)
3. [Timing advice](#3-timing-advice)
4. [Aggregation](#4-aggregation-conversations-topics-issues-features-voices)
5. [Duplicates](#5-duplicates)
6. [What gets delivered](#6-what-gets-delivered-heads-up-roundups-pages)
7. [Content briefs](#7-content-briefs)
8. [Social recommendations and the content queue](#8-social-recommendations-and-the-content-queue)
9. [API-trader lens](#9-api-trader-lens)
10. [Collection gates and de-noising](#10-collection-gates-and-de-noising)
11. [Tunables](#11-tunables)
12. [Quirks worth knowing](#12-quirks-worth-knowing)

---

## 1. Engagement score

`unified_score = ln(1 + max(0,likes) + 2*max(0,shares) + 3*max(0,replies))`. [scrape/base.py](../community/scrape/base.py)

Stored on every item as `engagement.score`; every collector calls it. What goes into each slot:

| Source | likes | shares | replies |
|---|---|---|---|
| X | likes | retweets + quotes | replies |
| Reddit post | upvotes | 0 | number of comments |
| Reddit comment | upvotes | 0 | 0 |
| YouTube video, Instagram | likes | 0 | comments |
| GitHub issue | thumbs-up reactions | heart reactions | comments |
| LinkedIn | likes | shares | comments |
| Forums | likes | 0 | replies |
| App reviews | **the star rating** | 0 | 0 |

Related: a conversation's `peak_engagement = int(max item score * 100)`.

## 2. Opportunity priority (the main score)

[recommend/score.py](../community/recommend/score.py), hourly, `score.run()`. It scores every conversation whose
`last_seen` is in the last 48 hours, from any source, using only enriched non-noise items. Conversations flagged
`is_nubra_watch` are skipped, and opportunities already `acted` or `dismissed` are not re-scored.

```
priority = 100 * ( 0.30*relevance + 0.25*freshness + 0.15*reach + 0.15*type + 0.15*author_quality )   (registry: recommend.weights)
```

| Part | Formula |
|---|---|
| **relevance** | `min(base + seo_boost, 1)` |
| base, by matched kind | broker_issue (complaint naming another broker) **1.0**, feature_request **0.9**, question / how_to **0.7**, comparison **0.7**, topic **0.4** |
| seo_boost | `min(0.1 * number of scoring keywords found, 0.2)`. Keywords = `nubra_features.seo_keywords` (Grounding page). Matched as plain **substrings** in the first 8,000 characters of the thread. |
| **freshness** | `0.5*min(velocity/4, 1) + 0.5*e^(-age_hours/12)`. velocity = the conversation velocity (section 4). age = hours since the conversation's `last_seen`. |
| **reach** | `0.6*min(log10(1+audience)/6, 1) + 0.4*min(ln(1+interactions)/ln(201), 1)`. audience = max over the thread of followers and views. interactions = the best single item's likes + upvotes + replies + comments + retweets + quotes (views and followers excluded). |
| **type** | broker_issue **1.0**, feature_request **0.9**, question / how_to **0.8**, comparison **0.7**, topic **0.5** (**0.3** when the thread is only news_opinion) |
| **author_quality** | `min(best voice score among the thread's authors / 100, 1)`. Multiplied by 0.3 if any author is flagged. 0.5 when no author has a voice score. |

Then, in this order:

1. **Recurrence boost.** For a *new* thread whose dominant topic already appeared in N heads-ups today:
   `priority *= 1 + min(0.05*N, 0.15)` (registry: `recurrence_boost_per_hit`, `recurrence_boost_cap`).
2. **Engagement gate.** If interactions < 10 (registry: `action_min_interactions`) and priority >= 60, priority is set to 59.
3. `priority = int(min(priority, 100))`. Below **40** (registry: `thresholds.secondary`) it is not stored. At **60** or more
   (`thresholds.headsup`) it can be a heads-up.

Used by: the Opportunities page and Overview ordering, the draft stage (best 10 at 40 or more, `max_drafted`), heads-ups,
the daily roundup, and the order in which Reddit threads are refreshed.

## 3. Timing advice

[recommend/draft.py](../community/recommend/draft.py), `_timing()`. Stored with each drafted opportunity as
`recommended_timing`. accel = conversation velocity, z = today's `velocity_z` of its dominant topic.

| Rule (first match wins) | Result |
|---|---|
| (accel >= 2 or z >= 1.5) and age < 12 h | now, "live" |
| topic is evergreen | schedule, pre-open |
| age < 24 h | today, the next window |
| otherwise | schedule, pre-open |

Windows (IST): pre-open 08:30-09:15, open 09:15-10:00, post-close 15:30-17:00, evening 20:00-22:30.

## 4. Aggregation: conversations, topics, issues, features, voices

[aggregate/rollups.py](../community/aggregate/rollups.py), runs after enrichment.

**Conversation** (one row per source + thread)
- `velocity = items in the last 3 h / max(items in the 3 h before that, 1)`
- `participants` = distinct authors, `peak_engagement` as in section 1, `is_nubra_watch` = any item names `nubra` as the broker.

**Topic per day** (`topic_daily`)
- `count` = canonical non-noise items that day, `spread` = number of distinct sources, `engagement_sum` = sum of scores plus the scores of duplicates credited to them, `audience_mix` = share by audience.
- `velocity_z = (count - mean of the previous 7 days) / (std + 1)`. Only computed when the previous 7 days all have a row. A topic with `velocity_z >= 1.5` is **rising**.

**Issue severity** (`issue_rollup`, complaints that name a broker, per broker + issue type + day)
- `severity = ln(1 + sum over items of max(followers, views)) * (share of items with sentiment < -0.3)`.
- The dashboard recomputes the same formula for custom windows. Sample items = the 5 highest-scoring.

**Feature requests** (`feature_rollup`)
- Each `feature_phrase` is embedded (multilingual-e5-small) and compared with the active centroids. Cosine similarity
  `>= tau` (registry: `aggregate.feature_sim_threshold`, **0.86**; code default 0.80) joins that group and the centre becomes
  the renormalised running mean. Otherwise a new `feat_NNNNN` group is created. Near misses in `[tau-0.03, tau)` are logged.

**Voice score** (`author_stats`, recomputed for authors who have new enriched items, over the trailing 30 days)

```
voice = 100 * ( 0.4*relevance + 0.3*consistency + 0.3*breadth )
relevance   = relevant items / enriched items      (relevant = not noise and the topic is in the live taxonomy)
consistency = distinct days with any item / 30
breadth     = min(distinct relevant topics, 8) / 8
```

- **Authenticity flag** = (followers > 10,000 and average item score < 1.0) or (account younger than 90 days).
- Shown on Voices (top 12 by score) and in the daily roundup (top 5). Also feeds **author_quality** in section 2.

## 5. Duplicates

[clean/dedup.py](../community/clean/dedup.py). Duplicates are linked (`duplicate_of`), never deleted.
- **Exact:** same content hash within the trailing 14 days.
- **Near:** MinHash (128 permutations) over 3-word shingles, candidate search at similarity 0.7, accepted when Jaccard >= **0.8**.
  Texts under 3 words are exact-match only. The earliest copy is the canonical one.

## 6. What gets delivered: heads-up, roundups, pages

| Output | Rule |
|---|---|
| **Heads-up actions** ([compose/render.py](../community/compose/render.py)) | status suggested, not yet pinged, priority >= 60, best 8 |
| **Heads-up rising topics** | `velocity_z >= 1.5`, not yet surfaced, best 5. With no 7-day history yet: top 3 by count with count >= 3 |
| **Heads-up Nubra watch** | `is_nubra_watch` conversations from the last 24 h, not yet shown today, newest 10 |
| **Daily roundup** ([compose/roundup.py](../community/compose/roundup.py)) | trending topics: sum of count >= 3 (`roundup.trending_min_items`), excluding `trending_exclude_topics`, ordered by `velocity_z` then count, 8. Broker issues: **no minimum**, by count, 8. Features: >= 2 mentions (`features_min_mentions`), by count, 8. Opportunities: the day's best 10 by priority. Voices: top 5. |
| **Weekly roundup** | `rank = metric * (1 + 0.25*min(weeks_running - 1, 3))`, where `weeks_running` is 2 if the key was in last week's report, else 1. "Consistent features" = seen on 4 or more days. |
| **Trends page** | no window: by max `velocity_z`, then count. With a window: by count, then engagement; z shown when the window is 2 days or more |
| **Explore** | by engagement score, or newest |
| **Overview "Top actions"** | the 5 best open opportunities by priority |

## 7. Content briefs

[recommend/draft.py](../community/recommend/draft.py), `_content_proposals()`, daily. The model proposes 8 candidates with five
sub-scores; the code ranks them:

```
score = 0.30*impact + 0.25*reach_fit + 0.20*timeliness + 0.15*effort_inv + 0.10*on_brand
```

Then: taxonomy check, at most **2 per format family**, an LLM repeat-judge against the last 7 days
(`content.repetition_lookback_days`), compliance, and the best **5** are kept (`MAX_PROPOSALS`).

## 8. Social recommendations and the content queue

**General recommendations** ([social_recommend/evidence.py](../community/social_recommend/evidence.py)): evidence from the last 30 days,
non-noise, not duplicate, text of 24 or more characters, near-identical texts collapsed (first 400 normalised characters).

```
item score = engagement + max(0, 20 - age_days) + 12 if intent is feature_request, question or comparison
engagement = direct score + likes*1 + upvotes*1 + score*1 + comments*2 + replies*2 + shares*3 + views*0.01 + stars*2 + downloads*0.1
```

Caps: 35 items per (segment, source) and 120 per segment. **Segment** = api if more API terms than retail terms appear
(GitHub gets +2), otherwise retail.
**Feature matching:** +6 if the feature name appears, +2 per keyword found, + up to 6 for distinctive-word overlap; the best 24 are sent.

**Content queue** ([social_recommend/api_lens.py](../community/social_recommend/api_lens.py)):
- Per-platform daily minimum of **2** briefs (github, forum, stackoverflow **1**; linkedin **4**). Only the shortfall is generated.
- Evidence order: reply targets first, then engagement score, 40 items. Fresh X reply targets (at most 3 days old, up to 8) are added on top.
- `priority_score` (0..100) is written by the model. The queue lists by created time, then priority.

## 9. API-trader lens

[enrich/api_trader.py](../community/enrich/api_trader.py): a regex gate on broker/API words picks candidates (max 200 per run), then a model labels
relevance, stage (exploring, first_api, building, scaling, churning), layer, kind (friction, guidance_seeking, showcase, comparison) and gist.
Themes are the **first matching regex** of ten friction buckets (cost_pricing, reliability, order_primitives, backtest_trust, data_access,
deployment_infra, onboarding_auth, risk_controls, regulation, data_quality) or six working buckets. "Build candidate" cards count
items per theme in the window and compare with the previous window (`api_trading.candidates`).

## 10. Collection gates and de-noising

| Where | Rule |
|---|---|
| **Prefilter** ([clean/prefilter.py](../community/clean/prefilter.py)) | noise if: no words after removing links; a spam handle (list currently empty); crypto talk without a market term; tip/pump language (2 or more hits, or 1 hit in 12 words or fewer); scraper artefacts |
| **Keyword fallback** (LLM failure) | complaint words, then feature-request words, then "?" means question, else news_opinion; topic `other:unclassified` |
| **Reddit search hits** | outside watched subreddits a post needs a market term (stock, trading, option, broker, ...) and an India signal (`keyword_india_only`). Any Reddit post older than `max_post_age_days` (30) is dropped. |
| **Reddit brand pass** | the text names "nubra" and is not a Ladakh travel post (travel words with no finance words) |
| **GitHub** | `2*(allowed words) - 4*(denied words)`, +3 for known broker repos; needs >= `relevance.min_score` (2) |
| **Instagram audio/video tiers** | likes >= `max(tier_min_likes (25), tier_multiplier (1.5) * the account's median likes)` |
| **YouTube comments** | at least `min_chars` (8) characters and no deny terms |

## 11. Tunables

| Setting (registry) | Default | Effect |
|---|---|---|
| `recommend.thresholds.headsup` / `secondary` | 60 / 40 | heads-up bar / lowest stored priority |
| `recommend.weights.*` | 0.25 / 0.30 / 0.15 / 0.15 / 0.15 | freshness_velocity / relevance / reach / opportunity_type / author_quality |
| `recommend.action_min_interactions` | 10 | engagement gate |
| `recommend.recurrence_boost_per_hit` / `_cap` | 0.05 / 0.15 | recurrence boost |
| `recommend.max_drafted` | 10 | drafts per run |
| `aggregate.feature_sim_threshold` | 0.86 | feature grouping |
| `roundup.trending_min_items`, `features_min_mentions`, `trending_exclude_topics`, `daily_window_days` | 3, 2, two topics, see quirks | roundup selection |
| GitHub `relevance.*`, Instagram `tier_*`, YouTube `comment_quality.*` | see section 10 | collection gates |
| Scoring keywords | Grounding page | the `seo_boost` |

Fixed in code (change `score.py`, `rollups.py` or `dedup.py`): the 12-hour freshness decay, the velocity cap of 4, the reach scaling,
the relevance and type tables, the SEO boost size, the voice weights, the `velocity_z` threshold 1.5, the dedupe thresholds, the severity formula.

## 12. Quirks worth knowing

1. **Scoring keywords match inside words.** `oi`, `iv`, `amo`, `uat` and `etf` are plain substrings, so ordinary words can add up to +0.2 relevance (about +6 priority) with no finance content. A whole-word match is not built.
2. **App reviews** feed the star rating into the "likes" slot of the engagement score.
3. **Weekly `weeks_running` is only 1 or 2**, so the multiplier is 1.0 or 1.25; the cap of 3 is never reached.
4. **`velocity_z` needs a row on each of the previous 7 days.** A sporadic or new topic never gets one, so it cannot be "rising".
5. **Voices:** scores are recomputed only when an author has new enriched items and never expire; followers and reach do not count; the account-age flag can never fire because no collector fills `account_created_at`; and the page text "relevant posts across N communities" is really *all items in 30 days* and *distinct relevant topics*.
6. **Freshness uses the last activity**, not when the thread started, so an old thread with a new reply looks fresh.
7. **`roundup.daily_window_days` is 7 in the registry file** although its comment says production should be 1. Check what production actually has.
8. **A thread the model skips, or whose drafts fail every attempt, is remembered** (migration 0025) and not drafted again on every run; see [reply-drafting-context-2026-10-14.md](reply-drafting-context-2026-10-14.md).
