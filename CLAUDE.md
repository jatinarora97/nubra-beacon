# Nubra Community Manager — project state

This repo holds the **POC** (Streamlit + Reddit live + vetted X CSV) and the **finalized
production design docs**. The production service is a NEW sibling repo — do not build it
here.

## State (as of 2026-07-03)

- Design is **complete and verified** (multiple adversarial review passes; all findings
  fixed). Build has **not started**. Next step = **M0** of the build plan.
- Build target: `~/nubra/1.Communication/nubra-community-manager/` (new repo; layout in
  build plan §2). Own Postgres DB `nubra_community` on Nubra's existing server.

## The docs (in `docs/`) — reading order for building

1. `nubra-community-manager-build-plan-2026-07-03.md` — **the master doc**: milestones
   M0–M6 with tasks + acceptance criteria. Start here.
2. LLDs (build-depth, per milestone):
   `…-lld-01-data-layer…` (M0 + schema: 18 tables, full DDL, partitioning, retention,
   roles) · `…-lld-02-ingest-enrich-aggregate…` (M1+M2: adapters, dedup, enrich prompt,
   aggregation algorithms) · `…-lld-03-recommend-delivery-api…` (M3–M5: scoring,
   compliance gate, heads-up/roundup, API, dashboard).
3. Context/rationale: `…-architecture-2026-06-29.md` (HLD) ·
   `…-posting-and-roundups-2026-06-29.md` · `…-data-flow-2026-07-03.md` ·
   `…-cost-plan-2026-07-03.md`.

The docs are internally consistent — if code and a doc disagree during build, the LLDs
are the source of truth for mechanics, the build plan for sequence.

## Locked decisions — do NOT re-open these

- Retention: **180d for ALL data including `compliance_audit`** (team decision
  2026-07-03). Reference/ops tables kept.
- Email via **Gmail SMTP app password** (in `config/.env`), not SES.
- Grounding: build on engineering's **`assumed-v0`** `nubra_features` catalog (assumed
  USPs/upcoming + starter F&O-trader SEO keywords). Marketing's excel imports later as a
  new version (`seed_features.py --from-xlsx`).
- Hourly **heads-up** Slack+email 08:00–20:00 IST: weight-sorted **actions** (per-thread
  novelty + **recurrence boost** for topics still rising in new threads) + a **last-hour
  ops summary**; empty actions → compact ops-only digest (config). Pipeline paused
  01:00–06:00 IST; **morning build** 06:00→07:30 (arch §8).
- Weekly roundup = **Sat→Sat** window, Sat ~10:00 IST, with last-week persistence
  weighting (`weeks_running`). All outbound messages render from **Jinja2 templates**
  (`delivery/templates/`, LLD-03 §6.4) — copy edits are template edits.
- De-noising reuses the **vendored comms guardrails** (crypto / tip-pump / artifact
  denylists from `nubra-ai-personalization/nubraai-comms/intelligence/`) — LLD-02 §6.6;
  same denylists feed the L1 gate (`l1.shared`).
- Reddit stays **Playwright** (ToS trade-off accepted for now); subreddit list is live
  config in LLD-02 §1.3.
- SSO deferrable (VPN-only until then). `delivery.nubra_watch_mention` empty in v1
  (plain channel post, no @).
- X budget: config `budget.max_usd_per_day`, start $5.
- `dismissed_reason` enum ships in v1. LLM calls via Anthropic **Batch API** per cost
  plan §2.

## Pending human inputs (don't block M0)

Slack channels + Gmail app password + API keys into config (user) · marketing's keyword
excel + vetted feature catalog (later version swap) · scoring weights finalized after
~2 weeks of shadow run.
