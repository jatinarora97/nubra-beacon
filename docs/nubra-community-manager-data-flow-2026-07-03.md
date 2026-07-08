# Nubra Community Manager — End-to-End Data Flow

> **STALE AS OF 2026-07-08 — kept for design rationale only.** The build
> deviated in load-bearing ways (React UI, restructured packages, vendored
> scraper transport, calibrations, Docker deploy). Current truth:
> `nubra-community-manager-status-2026-07-05.md` (what is built) +
> `nubra-beacon-tech-backlog-2026-07-08.md` (what remains). Where this file
> disagrees with those, those win.

_2026-07-03 · what happens at each stage and which table it touches._
_DB: **`nubra_community`** (own database on Nubra's Postgres server · migrations `0001+`)._

```
LEGEND    ▸ W: writes   ▸ R: reads   ▸ ⟳: updates          ══ pipeline stage ══   [ table ]
```

```
 REFERENCE FEEDS (marketing/product/SEO + git = source of truth · all version-labelled)
   nubra_features  (USP/live + upcoming + seo_keywords[]) ──┐     topic_taxonomy.seed ──┐
                                                            ▼                            ▼
                                                   [ nubra_features ]            [ topic_taxonomy ]


 ┌───────────────────────────────── SOURCES ─────────────────────────────────┐
 │  IN SCOPE:  X / Twitter (paid)    Reddit                                    │
 │  LATER:     GitHub · YouTube · Discord · Telegram · App-store reviews       │
 └────────────────────────────────────┬────────────────────────────────────────┘
                                       ▼
                        ╔═══════════════════════════════╗   R: pipeline_state (cursor)
                        ║  ① INGEST  (per-source)       ║   R: nubra_features.seo_keywords (expansion)
                        ║    + refresh engagement on    ║   W: social_items · authors (sets ingested_at
                        ║      active-24h conv roots    ║      — the watermark clock, not created_at)
                        ╚═══════════════╤═══════════════╝   ⟳: pipeline_state (watermark·health)
                                        ▼
                        ╔═══════════════════════════════╗
                        ║  ② NORMALIZE + DEDUP          ║   R/W: social_items
                        ║     content_hash + MinHash-LSH║        (link dupes: duplicate_of → canonical —
                        ║     (LSH over trailing ~14d)  ║         never dropped; author/engagement kept)
                        ╚═══════════════╤═══════════════╝
                                        ▼
                        ╔═══════════════════════════════╗   R: social_items (new via watermark)
                        ║  ③ ENRICH  (1 batched LLM call)║   R: topic_taxonomy
                        ║     audience · intent ·        ║   W: item_enrichment      (1:1)
                        ║     topic_key · entities       ║   W: item_embeddings      (non-noise)
                        ║     + embeddings               ║   log: llm_usage · trace_log
                        ╚═══════════════╤═══════════════╝
                                        ▼
                        ╔═══════════════════════════════╗   R: item_enrichment · social_items
                        ║  ④ AGGREGATE                  ║   R: authors · item_embeddings
                        ║   velocity · rollups · voices ║   W: conversations   (group thread_id)
                        ║                               ║   W: topic_daily     (velocity_z · spread)
                        ║   Nubra-mention items →        ║   W: issue_rollup    (broker · issue_key)
                        ║   tagged for Nubra-watch       ║   W: feature_rollup  (centroid-match feature_key)
                        ║                               ║   W: author_stats    (voice_score)
                        ╚═══════════════╤═══════════════╝
                                        ▼
                        ╔═══════════════════════════════╗   R: conversations · topic_daily
                        ║  ⑤a SCORE  (hourly · no LLM)  ║   R: issue_rollup · feature_rollup
                        ║   • score opportunities       ║   R: author_stats
                        ║     (skip broker=Nubra →       ║   R: nubra_features (kw boost)
                        ║      Nubra-watch segment)     ║   W: opportunities (priority · status=suggested)
                        ║   • HEADS-UP hourly 08–20 IST ║
                        ║     → Slack + email: actions  ║
                        ║     (new + recurring momentum,║
                        ║     weight-sorted) + ops summ ║
                        ╚═══════════════╤═══════════════╝
                                        ▼
                        ╔═══════════════════════════════╗   R: opportunities (top) ·
                        ║  ⑤b RECOMMEND (daily build)   ║      nubra_features (grounding)
                        ║   • gen brand + rep           ║   ⟳: opportunities
                        ║   • compliance gate (incl.    ║       (drafts·recommended_timing)
                        ║     content proposals)        ║   W: content_proposals (top 3)
                        ║   • when-to-post timing       ║   W: compliance_audit (draft × layer)
                        ║                               ║   log: llm_usage · trace_log
                        ╚═══════════════╤═══════════════╝
                                        ▼
                        ╔═══════════════════════════════╗   R: topic_daily · issue_rollup
                        ║  ⑥ ROUNDUP  (daily · Sat wk)  ║   R: feature_rollup · author_stats
                        ║     synthesize digest (Sonnet)║   R: opportunities · content_proposals
                        ╚═══════════════╤═══════════════╝   W: roundups (payload)
                                        ▼
                        ╔═══════════════════════════════╗
                        ║  ⑦ DELIVER   Slack + Email    ║   ⟳: roundups.delivery
                        ╚═══════════════╤═══════════════╝
                                        ▼
                            HUMAN reads roundup → acts manually
                            (posting / approval = out of scope, future)


 FRONTEND (read-only DASHBOARD · Nubra blue-dark palette · NO live fetching)
   R: roundups · topic_daily · issue_rollup · feature_rollup · author_stats ·
      opportunities · content_proposals · social_items (drill-down)
   filters: date · source · topic · broker · intent · audience · min-engagement
   W: feedback   (category + free text → internal; trains future self-learning)
   ⟳: opportunities.status  (acted / dismissed — closes the loop; future training signal)
```

```
 TABLES BY LAYER                                            RETENTION
 ─────────────────────────────────────────────────────     ──────────────────────────────
 L1 RAW        social_items ................ ①②③④⑤ dash      partitioned monthly, 180d (raw jsonb ~60d)
               authors ..................... ①④⑤            reference — kept (small; FK target)
 L2 ENRICH     item_enrichment ............. ③④⑤            } item_embeddings kept 180d
               item_embeddings ............. ③④
 L3 AGGREGATE  conversations ............... ④⑤              180d (by last_seen)
               topic_daily ................. ④⑤⑥ dash        } tiny → kept 180d
               issue_rollup ................ ④⑤⑥ dash        } (all data capped at 6 months)
               feature_rollup .............. ④⑤⑥ dash
               author_stats ................ ④⑤⑥ dash        ops — kept (current-state)
 L4 OUTPUT     opportunities ............... ⑤⑥ dash          kept 180d
               content_proposals ........... ⑤⑥ dash          kept 180d
               roundups .................... ⑥⑦ dash          kept 180d
 L5 OPS/REF    pipeline_state .............. ①  (all stages) live
               compliance_audit ............ ⑤               kept 180d (team decision 2026-07-03)
               topic_taxonomy .............. ③               reference (git-seeded)
               feature_keys ................ ④               centroid registry (reference — kept)
               nubra_features .............. ①⑤              reference (versioned; USP + upcoming
                                                             + seo_keywords[] — marketing/product/SEO)
               feedback .................... dash             internal (future self-learning)
               llm_usage · trace_log ....... ③⑤⑥  (reused from Nubra libs)
```

```
 CADENCE                                       DATA WINDOWS
 ────────────────────────────────────────     ────────────────────────────────
 ① ingest        per source · paused 01–06 IST  velocity baseline ...... trailing 7d
 ③ enrich        every 30–60 min (06–01 IST)    "rising" ............... velocity_z ≥ 1.5
 ④ aggregate     hourly (06–01 IST)              issue/feature history .. from L3 rollups (180d)
 ⑤a score        hourly → heads-up 08–20 IST     hot conversation ....... age < ~12h & rising
 ⑤b recommend    drafts with daily build        retention .............. 180d everything
 ⑥ roundup       daily 07:30 IST · weekly Sat 10:00 (Sat→Sat)
```
