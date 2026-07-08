# Nubra Community Manager — Cost Plan (v1)

> **STALE AS OF 2026-07-08 — kept for design rationale only.** The build
> deviated in load-bearing ways (React UI, restructured packages, vendored
> scraper transport, calibrations, Docker deploy). Current truth:
> `nubra-community-manager-status-2026-07-05.md` (what is built) +
> `nubra-beacon-tech-backlog-2026-07-08.md` (what remains). Where this file
> disagrees with those, those win.

_2026-07-03 · what the pipeline costs, and every saving we can take **without quality
loss**. Companions: architecture §9 (baseline cost table) · build plan §8 (cost
observability) · LLD-02 (enrich mechanics) · LLD-03 (draft/compliance mechanics)._

---

## 1. Where the money actually goes

| Line | ~Cost/day | Share | Notes |
|---|---|---|---|
| **X data (twitterapi.io)** | up to **$5.00** (config `budget.max_usd_per_day` — start at $5, tune after shadow run) | **~75%** | billed per result fetched — the dominant, cappable line |
| LLM — enrichment (Haiku, ~100 batched calls) | ~$0.30–0.60 | ~30% of LLM | Haiku 4.5: $1 in / $5 out per MTok |
| LLM — drafts + proposals + roundup (Sonnet, ~15 calls) | ~$0.50 | | Sonnet: $3 in / $15 out per MTok |
| LLM — compliance L2 (Sonnet, ~25 calls) | ~$0.10 | | |
| Embeddings | ~$0 | | local CPU model — already free |
| Slack / email / infra | ~$0 | | shared box, webhook, Gmail SMTP |

**Conclusion up front:** optimize the X line first (it's 3–4× the LLM line), then halve
the LLM line with the Batch API. Everything here is a one-time implementation choice that
scales if volume 10×s.

---

## 2. Measures adopted for v1 (no quality loss)

Ranked by savings. "Adopted" = the build implements this from day one.

### 2.1 Anthropic Batch API for all LLM stages · **≈ –50% of the whole LLM line**

The Batches API (`/v1/messages/batches`) runs identical requests at **50% of standard
price**; most batches complete well within an hour (24h worst case). Nothing in this
pipeline is latency-critical enough to justify paying double:

| Stage | Cadence | Batch fit | Deadline guard |
|---|---|---|---|
| Enrichment (Haiku) | every 30–60 min | submit each enrich pass as one batch | poll; if not `ended` in 25 min → run that pass sync, next pass resumes batching. **Exception:** the 06:00 morning-build pass runs sync (≈$0.02/day) so the chain closes |
| ⑤b drafts + proposal candidates (Sonnet) | daily | the **independent** generation calls, one batch at **06:45 IST** (tail of the morning build, arch §8) | sync fallback at 07:15; roundup at 07:30 |
| L2 compliance · regenerations · roundup synthesis | daily | **stay sync** — they consume the batch's outputs (a batch can't chain dependent calls) | ~$0.15/day; not worth the deadline risk |

Rules: results arrive **unordered — key by `custom_id`**, never by position; on
`errored/expired` items fall back to a sync call for just those items. Zero quality
impact — same model, same prompt, half the price. **Savings ≈ $0.50–0.65/day.**

### 2.2 X-query discipline · the real money lever

twitterapi.io bills per result, so waste = paying for tweets we drop:

- **No dead-hour queries** — X polls run 4×/day inside the waking window
  (06:00/11:00/15:00/20:00 IST, LLD-02 §1.3 — the 06:00 poll feeds the morning build);
  the 01–06 IST window returns near-zero relevant items but would bill the same query
  overhead.
- **No overlapping queries** — base queries and SEO-expansion queries are constructed to
  minimize shared result sets (dedup happens *after* we've paid for both copies). Review
  overlap monthly via `raw._matched_seo` counts.
- **Cursor discipline** — never re-fetch a seen tweet (already in LLD-02 §2; keep it).
- **Thread backfill only for candidates** — `conversation_id` backfill runs only for
  conversations that scored priority ≥ 40, not for every thread.
- **Engagement refresh scoped** — re-fetch roots only for conversations that are current
  opportunity candidates (priority ≥ 40) rather than all active-24h threads; batch lookup
  endpoint (100 ids/call) keeps this to 1–2 calls/run.

Effect: the same $5/day cap buys meaningfully more *relevant* coverage — or the cap can
drop once shadow-run data shows the actual spend curve.

### 2.3 Deterministic pre-filter before enrichment · **≈ –5–15% of enrich volume**

Rule-mark unambiguous noise as `is_noise=true` **without an LLM call**: empty/emoji-only
text, pure-link posts with no words, authors on the known spam/tip handle list (LLD-02
§8.5). Only cases where no judgment is involved — anything debatable still goes to Haiku,
so recall is untouched.

### 2.4 Prompt caching where it actually bites

Caching reads cost 0.1× (writes 1.25×), **but a prefix only caches above a model-specific
minimum** — ~4k tokens on Haiku 4.5, ~1–2k on Sonnet-tier:

- **⑤b draft pass (adopt):** the system prompt + serialized `nubra_features` catalog is
  the shared prefix across ~10 Sonnet calls made minutes apart — mark it with
  `cache_control` and the 9 follow-up calls read it at 0.1×. One parameter, free money.
- **Enrichment (measure first, don't force):** the enrich prompt + 40-topic taxonomy is
  likely *below* Haiku's cacheable minimum, in which case `cache_control` silently does
  nothing. Add the marker, then check `usage.cache_read_input_tokens` in Langfuse — if
  zero, drop it. **Never pad a prompt just to reach the caching threshold.**
- Caching works inside batches too, but hits are best-effort (parallel processing) —
  treat batch-cache savings as a bonus, not a plan.

Honest sizing: cents per day at current volume; adopt because it's one line of code and
scales linearly with volume.

### 2.5 Overnight pause (01:00–06:00 IST) — what it does and doesn't save

Adopted for cadence reasons (see architecture §8); the cost framing, honestly:

- **Does NOT reduce LLM cost** — items posted overnight are still fetched and enriched at
  the 06:00 catch-up; the same tokens get processed, just later.
- **Does save X query spend** — scheduled searches in dead hours pay full query overhead
  for near-empty result sets (covered in §2.2).
- **Does shrink the ops surface** — 5 fewer hourly runs/day of enrich/aggregate/score to
  monitor, alert on, and debug.
- **Loses nothing** — both sources are pull-based; cursors and `ingested_at` watermarks
  mean overnight items are collected at 06:00, well before the 07:30 roundup and the
  first 08:00 heads-up.

### 2.6 Already in the design — preserve these

Duplicates are never enriched (canonical-only, LLD-02 §5) · embeddings are local CPU ·
Haiku for bulk, Sonnet only for ~35 high-value calls/day · hourly scoring pass uses **no
LLM** at all · 180d retention caps storage.

---

## 3. Explicitly rejected (would cost quality)

| Idea | Why rejected |
|---|---|
| Cheaper/smaller model for compliance L2 | the gate is the product's safety net; it costs $0.10/day — not the place to save |
| Keyword pre-filtering at ingest | violates the founding "expand, never filter — full blast radius" rule; silently blinds the radar |
| Cutting subreddit / X query coverage | coverage *is* the product; trim only with shadow-run evidence that a source yields nothing |
| Skipping L1+L2 for "low-risk" drafts | every public-facing draft is gated, no exceptions — regulatory posture |
| Enriching only high-engagement items | early complaints/requests start at zero engagement; sampling would miss exactly the rising signal we exist to catch |

---

## 4. Net effect

| Line | Before | After |
|---|---|---|
| LLM | ~$1.20–1.40/day | **~$0.55–0.70/day** (Batch API −50%, prefilter −5–15% of enrich, caching pennies) |
| X data | $5/day cap, partly wasted on dead hours + overlap | same cap, materially more relevant coverage; likely reducible after shadow run |
| Storage | bounded (180d) | unchanged |

Absolute numbers are small today; the point is that every measure above is structural —
at 10× volume the LLM line stays ~$6/day instead of ~$13, and the X budget conversation
becomes "what coverage do we want" instead of "where is it leaking".

**Implementation homes:** Batch API + caching + prefilter → LLD-02 §6 / LLD-03 §2 (M2/M3
work items) · X discipline → LLD-02 §2 (M1) · pause → scheduler (M6). Cost check lives in
build plan §8 (daily `llm_usage` + X budget vs this plan's targets).
