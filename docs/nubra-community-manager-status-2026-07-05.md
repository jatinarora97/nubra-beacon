# Nubra Community Manager — Project Status (2026-07-05)

_The living state document. Newer than every design doc in this folder — where they
conflict, THIS wins. For a fresh session: read this + CLAUDE.md, then the code._

---

## 1 · What we are building

An always-on **community radar + marketing copilot** for Nubra (Indian discount broker,
NSE/BSE + F&O). It listens where Indian traders talk (X + Reddit today; more sources
later), understands what's trending / breaking / being asked for, and tells the
marketing team **what to say, where, and when** — grounded in what Nubra actually
offers and safe for a SEBI-regulated broker.

The pipeline (code layout maps 1:1, one package per stage):

```
scrape/ → clean/ → enrich/ → aggregate/ → recommend/ → compose/ → dispatch/
 pull      dedup     LLM tags    trends      score +      build       Slack/email
 raw       de-noise  topic/      issues      draft +      messages    + archive +
 data                intent/     features    comply       (analytics  dashboard
                     entities    voices                   + actions)
```

Outputs: **hourly heads-up** (weight-sorted actions + last-hour ops summary, 08–20 IST),
**daily roundup** (07:30, all 6 outputs), **weekly Sat→Sat roundup** (Sat 10:00,
persistence-weighted), a **Nubra-watch** segment (our own mentions → support, never
engagement drafts), and a **React dashboard** — branded **Nubra Beacon** — for
browsing/acting on everything.
Recommends only — humans post. Grounded on the versioned `nubra_features` table;
every draft passes a 3-layer compliance gate (regex rules → LLM review → human).

## 2 · Built and verified (everything below ran on real data)

| Area | State |
|---|---|
| **Infra** | Docker pgvector Postgres (`nubra-community-postgres`, :5544), 19-table schema via 3 migrations, git history in this repo. POC archived in `poc/`. |
| **Scrape** | X: CSV backfill (400 tweets) + live twitterapi.io search (capped; currently 402 — credits exhausted, degrades gracefully, flagged in every ops summary). Reddit: vendored zanshash/reddit_scraper (old.reddit + Playwright — the ONLY transport; works where JSON API is network-blocked), 18 categorized subs incl. live broker subs (r/Zerodha, r/groww, r/upstox, r/dhanhq), feeds new+hot+rising hourly / top daily, 10 posts/sub, top-15 comments + **1 level of nested replies**, rerun-skip via SKIP_IDS. ~2k items in DB (1.6k Reddit). |
| **Clean** | normalize → content_hash; MinHash-LSH near-dup (link-not-drop, `duplicate_of`, 14d window); guardrail de-noise **vendored from nubra-ai-personalization** (crypto-only, tip/pump, scraper artifacts — classifier-not-censor). |
| **Enrich** | Haiku batched enrichment via **Anthropic Batch API** (50% price, 25-min SLA → sync fallback; `sync=True` for morning build), Hinglish-first prompt, pydantic-validated, kw-fallback; **multilingual-e5-small embeddings** (1.1k+ vectors). |
| **Aggregate** | conversations (velocity, Nubra-watch flag), topic_daily (velocity_z vs 7d), issue_rollup (broker gazetteer, severity), feature_rollup with **embedding-centroid keys** (τ=0.86, measured — merges differently-worded asks), author_stats (voice score). |
| **Recommend** | Priority scoring (weights in registry; **engagement gate**: <10 interactions can't be a top action; **recurrence boost** for topics rising in new threads; action bar 60 — recalibrated on real data), Nubra-watch diversion, grounded brand+rep drafts (features_cited validated, ASCI disclosure verbatim), timing rules, compliance gate writing `compliance_audit` (429 rows so far). |
| **Compose** | Heads-up (actions + human ops summary: fetched/analyzed/identified per platform), daily roundup (trending bar ≥3 items, issue topics excluded from trending; features bar ≥2), weekly Sat→Sat with `weeks_running` weighting, **content briefs**: free-form creative treatment + registry-controlled `format_family`/`platform` taxonomy, creator-ready (beats/caption/hashtags/CTA/visual direction). Jinja templates, emoji-free. |
| **Dispatch** | Slack webhook + Gmail SMTP senders (config-gated via .env; template `community/config/env.example`), archive to `out/messages/` always, 08–20 IST channel window, once-per-row roundup sends, novelty stamping post-delivery. |
| **UI** | **React/Next.js** (`webapp/`, :3000) — dark multi-accent, 9 routes: context-first landing, trends (sorted bars + metric glossary), broker×issue heatmap with quotes, feature cards with quotes, opportunities (why-engage-led cards, tabbed drafts + copy, acted/dismiss-with-reason), creator-handoff content briefs, sorted voices (niche, why-rising, profile links), explore (verification layer, engagement-sorted), **Sources** (manage subreddits/hashtags/handles/queries from the UI — next run picks them up). Branded **Nubra Beacon** with the official Nubra logo (tab icon + sidebar); theme switcher (System/Dark/Light) behind a top-right settings menu; manual feature-request intake on the Features page (writes to the `feedback` table). Streamlit retired. |
| **API** | FastAPI read-API (:8400, /docs): overview KPIs, server-computed `why_engage`, quote samples, sources CRUD, feedback + status writes (one-way, dismissed-reason enum). `./cm ui` supervises API+webapp and respawns dead children. |
| **Scheduler** | `./cm schedule` prints/installs cron (hourly 07–00 IST, 06:00 morning build, Sat weekly, 01–05 pause); `./cm morning-build` orchestrated sequence with sync enrich + X trend discovery. NOT yet installed on any machine. |
| **Sources config** | `watch_sources` table = source of truth (UI-managed, registry is seed): 18 subreddits, 14 hashtags, 12 researched handles (official NSE/BSE/SEBI, verified SEBI-registered voices with provenance notes, educators), 1 X query. X trend discovery (India trends → LLM finance filter → inactive suggestions) implemented, unverified until X credits return. |

**Commands:** `./cm run-local` (E2E) · `./cm stage <scrape|clean|enrich|aggregate|score|draft|compose|dispatch>` · `./cm ui` · `./cm migrate` · `./cm schedule` · `./cm morning-build`. Scripts: `seed_features` / `seed_sources` / `sync_guardrails` / `sync_reddit_scraper` (vendor patches live here) / `backfill_embeddings` / `refresh_local_data` (test utility).

## 3 · Additions & changes vs the original design docs

Decisions made during the build (the LLD/build-plan docs predate these):

1. **Build lives in THIS repo** (not the planned sibling repo); code restructured into stage packages (docs describe the old `pipeline/` layout).
2. **No local/prod split** — one prod-grade codebase (Batch API, embeddings, real senders); only credentials/cron are environment-specific.
3. **Frontend is React/Next.js**, not the planned Streamlit-then-React (Streamlit built, reviewed, rejected, replaced same-day).
4. **Reddit transport** = vendored zanshash/reddit_scraper (user's repo) with sync-script patches (nested replies, SKIP_IDS) — not the LLD's own Playwright port; JSON fallback removed by directive.
5. **Heads-up redesign**: two-part (actions + ops summary), per-thread novelty + recurrence boost, ops-only digest on empty (config), hourly 08–20 IST.
6. **Weekly = Sat→Sat** (was Monday), persistence-weighted.
7. **Quality gates added**: engagement gate (≥10 interactions for top actions), trending bar ≥3, features bar ≥2, issue topics excluded from trending; priority displayed as rank, score demoted.
8. **Content generation freed**: LLM invents treatment + picks platform; control via registry `content.format_families/platforms` (migration 0002 dropped the format CHECK).
9. **Sources are UI-managed** (`watch_sources`, migration 0003) + X hashtags/handles as first-class query sources + daily trend discovery.
10. **Calibrations from real data**: centroid τ 0.80→0.86, action bar 70→60, roundup signal windows widened; documented in registry comments.
11. **Retention**: 180d for EVERYTHING incl. compliance_audit (user decision, final). Grounding = engineering's `assumed-v0` catalog until marketing's vetted cut + keyword excel swap in (versioned publish).
12. **Emoji-free** everywhere in system chrome (UI, messages, prompts); social drafts may still use them (they're platform-native content).
13. Email = **Gmail SMTP app password** (not SES).
14. Dashboard renamed **Nubra Beacon** (user-picked, 2026-07-05) with official nubra.io logo mark; light theme added (System/Dark/Light, persisted, no-flash boot script); Next dev indicator disabled. Team-logged feature requests land in the designed `feedback` table (`GET`/`POST /api/v1/feedback`, category `feature_request`) — kept separate from measured community rollups.

## 4 · What's left

**To go live (needs human/credentials):**
- [ ] Slack webhook + Gmail app password into `.env` (+ recipients in registry) — senders activate on next dispatch, zero code.
- [ ] X credits top-up (twitterapi.io is 402) → verifies live X at volume + trend discovery round-trip; then raise/remove the 10-item cap.
- [ ] Install the schedule (`./cm schedule --install`) on whichever box runs this (target: next to nubra-ai-personalization) — includes morning build + hourly cadence.
- [ ] Marketing inputs: vetted `nubra_features` catalog + SEO keyword excel (`seed_features.py --from-xlsx` path specced, not yet implemented — small task when the excel arrives).

**Engineering backlog (ordered by value):**
- [ ] Shadow run 1–2 weeks → re-tune scoring weights + thresholds (the designed calibration step), then pilot → team rollout.
- [ ] Auth for the dashboard/API (SSO/OIDC per LLD; `X-Auth-Request-Email` wiring is a one-liner server-side; currently `local-dev` writes) — before anyone beyond the team touches it.
- [ ] "Backend offline" banner in the webapp (soft-fail currently looks like blank data — bit us once).
- [ ] Reddit engagement refresh (`fetch_items` not implemented for the scraper transport — candidate threads' upvotes stay snapshot-at-fetch).
- [ ] `llm_usage`/`trace_log` persistence (spend + stage logs currently stdout only) + health alerting (per-source staleness → Slack alerts channel).
- [ ] Weekly roundup page in the webapp (payload + markdown exist; no route renders it).
- [ ] Doc-sync pass: LLDs/build plan still describe pre-restructure layout, Streamlit, τ=0.80, 70-bar, Mon weekly (this file is the authority meanwhile).
- [ ] Prod deploy hardening: systemd/nginx/TLS per build plan §7, backups, `docker compose` for the DB on the prod box.

**Deferred by design (P2 / future phases — unchanged from the docs):**
emergent topic discovery (HDBSCAN over `other:*`), learned posting windows, posting-with-approval workflow (Slack approve/edit/skip), self-learning from `feedback` + dismissed reasons, more sources (YouTube/Telegram/app reviews — adapter contract ready).

## 5 · Current data & spend snapshot

~2,050 items (1,608 Reddit / ~440 X) · 1,123 embeddings · 20 centroid feature keys ·
227 opportunities (37 drafted) · 429 compliance-audit rows · total LLM spend for the
entire build ≈ $5. DB up via `docker compose up -d`; UI via `./cm ui`
(http://localhost:3000 + http://127.0.0.1:8400/docs).
