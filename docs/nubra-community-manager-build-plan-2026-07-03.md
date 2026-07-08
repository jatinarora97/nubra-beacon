# Nubra Community Manager — Build Plan (v1)

> **STALE AS OF 2026-07-08 — kept for design rationale only.** The build
> deviated in load-bearing ways (React UI, restructured packages, vendored
> scraper transport, calibrations, Docker deploy). Current truth:
> `nubra-community-manager-status-2026-07-05.md` (what is built) +
> `nubra-beacon-tech-backlog-2026-07-08.md` (what remains). Where this file
> disagrees with those, those win.

_2026-07-03 · the how-to-build companion to the architecture / decision / data-flow docs._
_Frontend decision: **hardened Streamlit** over a thin **FastAPI read-API** (internal, read-only)._

**Reference docs:** `nubra-community-manager-architecture-2026-06-29.md` (system/HLD),
`…-posting-and-roundups-2026-06-29.md` (recommendations/compliance),
`…-data-flow-2026-07-03.md` (per-stage table flow),
`…-lld-01-data-layer…` / `…-lld-02-ingest-enrich-aggregate…` /
`…-lld-03-recommend-delivery-api…` (build-depth specs),
`…-cost-plan-2026-07-03.md` (cost measures).

**What v1 delivers:** X + Reddit → enriched, deduped, rolled-up → 6 outputs + Nubra-watch
→ daily + weekly roundup on Slack + email → a read-only dashboard. Grounded on
`nubra_features`, compliant, human-in-the-loop (no posting). Runs on a schedule, its own
`nubra_community` Postgres DB, deployed next to `nubra-ai-personalization`.

---

## 0. Guiding principles

- **Backend does everything; frontend only reads tables + writes `feedback`.** (Swappable frontend.)
- **Pluggable sources, invariant pipeline.** Adding a source never touches downstream.
- **Idempotent + incremental.** Every stage UPSERTs, driven by a watermark; reruns are safe.
- **Grounded + compliant by construction.** Replies assert only `nubra_features` facts; every draft audited.
- **Reuse Nubra's stack** (Postgres, Claude, Langfuse, dynaconf, S3) — build only what's new.
- **Ship thin, then deepen.** v1 uses taxonomy assignment / rule-based timing / MinHash; fancier methods are P2.

---

## 1. Tech stack (concrete)

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| DB | PostgreSQL (existing server) · **new DB `nubra_community`** · `pgvector` ext |
| DB access | SQLAlchemy 2.0 Core (or psycopg3) + a thin repository layer; reuse Nubra pool pattern |
| Migrations | plain numbered SQL `migrations/0001_init.sql …` + tiny runner (Nubra convention, from 0001) |
| Ingestion | X = twitterapi.io (reuse POC adapter); Reddit = Playwright (reuse POC scraper) |
| Dedup | exact `content_hash` + **MinHash-LSH** (`datasketch`) |
| Embeddings | local `sentence-transformers`, **multilingual** (`multilingual-e5-small`; `bge-m3` if quality demands) on CPU → pgvector — the chatter is heavily **Hinglish**, an English-only model degrades near-dup + feature clustering; Voyage as drop-in option |
| LLM | Anthropic Claude — **Haiku** (enrich) · **Sonnet** (talking points, content, roundup, compliance) |
| Tracing/cost | Langfuse + `llm_usage` (reuse) |
| Scheduling | v1 = CLI stages (`runner.py stage <name>`) + cron/systemd timers; optional wire to EventBridge webhook later |
| Delivery | Slack incoming webhook (read-only digest) · Email via **Gmail SMTP (app password)** — ~a dozen mails/day, well inside Gmail limits; SES is a drop-in swap later |
| Read-API | FastAPI (read-only endpoints; writes only `feedback`) |
| Dashboard | Streamlit + `config.toml` theme + injected `design_system.css` (blue-dark) · SSO via `st.login` OIDC or reverse-proxy |
| Config/secrets | dynaconf + gitignored `config/.env` |
| Deploy | systemd (or docker-compose) behind nginx + TLS, on internal network/VPN |

---

## 2. Service & repo layout

New sibling service: `~/nubra/1.Communication/nubra-community-manager/` (separate from the
POC at `6.MarketPulse`, separate from `nubra-ai-personalization`).

```
 nubra-community-manager/
   migrations/            0001_init.sql · 0002_*.sql · run_migrations.py
   community/
     sources/             base.py(SocialItem+contract) · twitter.py · reddit.py   (+github… later)
     pipeline/            normalize.py · dedup.py · enrich.py · aggregate.py
                          recommend.py · compliance.py · roundup.py
     store/               db.py(pool) · schema.py · repositories.py
     llm/                 client.py · embeddings.py · prompts/*.txt
     lib/                 comms_guardrails/ (vendored from nubraai-comms — LLD-02 §6.6)
     reference/           features.py(nubra_features) · taxonomy.py
     delivery/            slack.py · email.py · templates/*.j2 (LLD-03 §6.4)
     api/                 read_api.py (FastAPI)
     scheduler/           runner.py (CLI stages) · timers
     config/              settings.py · .env · design_system.css
   dashboard/             app.py (Streamlit) · pages/ · theme/config.toml
   tests/                 unit/ · integration/ · fixtures/
   scripts/               seed_features.py · sync_guardrails.py · backfill.py · healthcheck.py
   pyproject.toml · README.md
```

**Reused from the POC** (ported, not rewritten): twitterapi.io adapter + vetting, Reddit
Playwright scraper, keyword-classifier (as LLM fallback), trend/actions/voices heuristics
(as seeds + fallbacks), prompt patterns. **Discarded:** SQLite schema, the run-pipeline
Streamlit UI, the CSV interim.

---

## 3. Build sequence (critical path)

```
 M0 Foundations ─▶ M1 Ingestion ─▶ M2 Enrich+Aggregate ─▶ M3 Reference+Recommend ─▶ M4 Roundup+Deliver
      (DB, store,      (SocialItem,      (Haiku enrich,          (nubra_features,           (digest,
       config, CI)      X+Reddit,         embeddings,             opportunities,            Slack+email)
                        dedup)            rollups)                compliance)                   │
                                                                                               ▼
                                                              M6 Orchestrate+Deploy ◀── M5 Read-API + Dashboard
                                                              (scheduler, systemd,        (FastAPI, Streamlit,
                                                               nginx, health, rollout)     SSO, palette, feedback)

 PARALLEL, start at M0:  ▸ Reference data: engineering seeds `assumed-v0` (nubra_features + SEO keywords);
                           marketing/product/SEO refine later via a versioned publish
                         ▸ Slack channels (team creates) · Gmail app password into config ·
                           SSO app (deferrable — see M5)
```

Infra provisioning is the only cross-team dependency left (Slack channels + Gmail app
password now; SSO before full rollout). Reference data starts as our own `assumed-v0` —
no longer a blocker (§5).

---

## 4. Milestones — tasks, acceptance, sizing

_Sizing is rough guidance (person-weeks), sequenced by dependency, not calendar-dated._

### M0 · Foundations  ·  ~1 wk
- [ ] Repo scaffold, `pyproject`, lint/format, CI (tests + lint).
- [ ] Create DB `nubra_community`; enable `pgvector`; rw + ro DB roles.
- [ ] `0001_init.sql` — the **18 tables** (per LLD-01) + indexes + monthly partitioning on `social_items`/`item_enrichment`/`item_embeddings` + a 180d retention job stub. Migration runner.
- [ ] `store/` pool + repository skeletons; dynaconf config + `.env`; Langfuse wired.
- **Accept:** `run_migrations.py` builds the schema clean; a smoke test inserts + reads a `social_items` row.

### M1 · Ingestion  ·  ~1.5 wk
- [ ] `SocialItem` contract + `sources/base.py` (fetch signature + capabilities).
- [ ] Port **X adapter** (twitterapi.io, budget-capped) and **Reddit adapter** (Playwright) to emit `SocialItem`, incl. `thread_id`/`parent_id`/`author_meta`; X-query discipline per cost plan §2.2 (waking-window polls, minimal query overlap, candidate-only thread backfill + engagement refresh).
- [ ] `normalize.py` + `dedup.py` — exact hash + MinHash-LSH over a trailing ~14d window; **link, don't drop** (`duplicate_of` → canonical; `minhash_sig` persisted); `authors` upsert.
- [ ] `pipeline_state` watermarks (**on `ingested_at`**, not `created_at` — late-arriving items) / cursors per source; per-source health fields; engagement re-fetch for roots of *candidate* conversations active < 24h (suggested opportunity or Nubra-watch — LLD-02 §4).
- **Accept:** a scheduled ingest run lands X + Reddit items in `social_items`/`authors` with dupes **linked** (never dropped); rerun adds only new rows and picks up late arrivals; `pipeline_state` updates.

### M2 · Enrichment + Aggregation  ·  ~2 wk
- [ ] `topic_taxonomy` seed (~40 trading topics).
- [ ] `enrich.py` — **one batched Haiku call** → `audience·intent·topic_key·sentiment·entities`; keyword-classifier fallback; schema-validated output; prompt explicitly handles **Hinglish/code-switched** text; submitted via the **Anthropic Batch API** (−50%, 25-min SLA → sync fallback) behind a **deterministic noise pre-filter** (cost plan §2.1/§2.3).
- [ ] **Vendor the comms guardrails** (`community/lib/comms_guardrails/` + `scripts/sync_guardrails.py` with CI drift check) and wire them into de-noise — crypto-only, tip/pump language, scraper artifacts (LLD-02 §6.6) — and into the L1 gate vocabulary (LLD-03 §3.1 `l1.shared`).
- [ ] `embeddings.py` — local **multilingual** model → `item_embeddings` (non-noise only); HNSW index.
- [ ] `aggregate.py` — `conversations` (thread grouping), `topic_daily` (velocity_z, spread), `issue_rollup` + `feature_rollup` (broker gazetteer link + **incremental centroid assignment** for `feature_key`: nearest existing centroid ≥ τ else mint new key — no per-run re-clustering), `author_stats` (voice score + authenticity flag).
- **Accept:** on a real batch, every non-noise item has enrichment + embedding; rollups populate; velocity_z computes (raw-count fallback in cold-start); entity linking spot-checks ≥ target precision; planted crypto-only and tip-pump items are rule-marked noise with no LLM call, while a complaint merely *quoting* tip language survives to enrichment.

### M3 · Reference data + Recommend  ·  ~2.5 wk
- [ ] `nubra_features` table live + `scripts/seed_features.py` loading the catalog (v1 = engineering's **`assumed-v0`** cut + `seo_keywords[]`, versioned; `is_current`; marketing's vetted cut publishes as a later version — §5).
- [ ] SEO-keyword use: query expansion at ingest + rank boost at recommend (never filter).
- [ ] `recommend.py` — **split cadence**: hourly scoring pass over `conversations` (no LLM) feeding an **hourly heads-up to Slack + email (08:00–20:00 IST)** — weight-sorted actions (per-thread novelty + **recurrence boost** for topics still rising in new threads) + the **last-hour ops summary**; ops-only digest when no actions (config; LLD-03 §1.3); daily draft pass. **Nubra-watch** diversion (broker==Nubra → segment, no drafts); grounded **brand + rep** drafts (context = `nubra_features`); **when-to-post** timing (thread urgency + Indian-market windows); **content proposals top-3** (rank→3).
- [ ] `compliance.py` — defense-in-depth gate (rule denylist → Sonnet review → `compliance_audit`), applied to **replies and content proposals**; ASCI disclosure baked into rep template.
- [ ] Cost measures (cost plan §2): ⑤b drafts + proposal candidates submitted as one **06:45 IST batch** at the tail of the morning build (sync fallback 07:15; L2 compliance/regenerations/roundup synthesis stay sync — dependent calls); `cache_control` on the shared `nubra_features` prefix; enrich cache marker verified via Langfuse `cache_read_input_tokens` (drop if zero).
- **Accept:** opportunities carry priority + both drafts + timing; a planted hot thread appears in the next hourly heads-up and is not repeated for the same thread; a *new* thread on an already-featured topic re-enters with a visible recurrence boost; an actions-empty pass sends a compact ops-only digest (or nothing, per config); content proposals capped at 3; every draft has a `compliance_audit` verdict; a planted non-compliant draft is blocked; a Nubra-mention never becomes an opportunity (it appears in the heads-up instead).

### M4 · Roundup + Delivery  ·  ~1.5 wk
- [ ] `roundup.py` — daily + weekly synthesis (Sonnet) → `roundups.payload`; weekly = **Sat→Sat highlights** with last-week persistence weighting (`weeks_running`, LLD-03 §6.3) + the weekly actions recap.
- [ ] `delivery/templates/` — **Jinja2 templates** for every outbound message (heads-up / daily / weekly × Slack / email), rendered against fixture payloads in CI; copy changes are template edits, not deploys (LLD-03 §6.4).
- [ ] `delivery/slack.py` (incoming webhook digest) + `delivery/email.py` (Gmail SMTP, app password) + the **hourly heads-up path** (Slack alerts channel + short email; ops-only digest when no actions, per config).
- **Accept:** a daily roundup with all 6 outputs + Nubra-watch lands in the Slack channel and inbox; the Saturday weekly shows `weeks_running` persistence weighting + the actions recap; editing a template changes the message without a code change; `roundups.delivery` records status.

### M5 · Read-API + Dashboard  ·  ~2 wk
- [ ] `api/read_api.py` — FastAPI read endpoints (trends, issues, features, voices, opportunities, content, roundups, item drill-down) with filters; `POST /feedback`; `POST /opportunities/{id}/status` (acted | dismissed + required `dismissed_reason` enum).
- [ ] Streamlit dashboard — filter → view → drill-down; **feedback widget** (categories + free text → `feedback`) + **opportunity status buttons** (acted / dismiss-with-reason picker); blue-dark palette via `config.toml` + injected `design_system.css`.
- [ ] Auth — `st.login` OIDC (or reverse-proxy SSO); read-only DB role for API. SSO may land **after** the first internal rollout — until then the dashboard is reachable only on the internal network/VPN (already required by the deploy posture).
- **Accept:** team member logs in via SSO, filters by date/source/topic/broker/intent, drills into source items, submits feedback that persists, marks an opportunity acted/dismissed; dashboard reads only through the API; palette matches comms.

> **Why Streamlit for v1 — and what "hardened" means.** The costly, durable work is the
> backend + the FastAPI **read-API**; a future React app reuses *all* of it and only swaps
> the thin view layer. So Streamlit is a cheap, validated first step — **not** a throwaway.
> The rule that makes this safe: **build the read-API boundary properly, keep the UI
> disposable.** "Hardened" = the production concerns a POC skips, bolted on:
> **SSO auth · read-only (via the read-API + a read-only DB role) · secure deploy (systemd +
> nginx/TLS on VPN/internal net) · Nubra blue-dark palette · caching (no live fetch) ·
> dynaconf secrets.** See the React migration path in §10.

### M6 · Orchestration + Deploy + Rollout  ·  ~1.5 wk
- [ ] `scheduler/` — CLI stage commands + cron/systemd timers at the documented cadence (incl. **hourly score 06–01 IST**, **heads-up 08–20 IST**, the **06:00–07:30 morning-build sequence** (arch §8), and the **01:00–06:00 IST overnight pause** — cursors catch up at 06:00, nothing lost); partition + 180d-retention job (**all data 180d, compliance_audit included**; runs as the table-owner role, LLD-01 §8).
- [ ] Deploy — systemd/docker, nginx+TLS, internal-network/VPN; secrets via dynaconf; backups.
- [ ] Observability — per-source health alerts, stage `trace_log` rows, Langfuse dashboards, cost check.
- [ ] **Rollout:** shadow run (roundup to a private channel, team doesn't act) → pilot (2–3 users) → full team.
- **Accept:** the full chain runs unattended on schedule; a killed source degrades gracefully + alerts; retention/partition jobs run; go-live checklist signed off.

**Indicative total: ~12 person-weeks** for v1 (compressible with parallelism across the workstreams above).

---

## 5. Reference-data workstream (start at M0, needed by M3)

`nubra_features` is the grounding + keyword backbone. **v1 ships on our own assumed
catalog** — engineering drafts the live-USP/upcoming rows + obvious SEO keywords from
public product knowledge, published as version **`assumed-v0`**:
- `scripts/seed_features.py` loads `assumed-v0` at M0; every publish is
  **version-labelled** and history is retained.
- `assumed-v0` SEO keywords = a starter **F&O-trader set** (expiry, option selling,
  margin, brokerage, order types, …). Marketing has a large keyword excel — it imports
  later via `seed_features.py --from-xlsx` as a new version, same swap mechanism.
- Marketing/product/SEO refine later: their vetted cut publishes as a new version and
  flips `is_current` — a data swap, not a code change.
- **No longer a build blocker** — but drafts ground on assumed facts until the vetted cut
  lands, so the roundup footer flags `grounding: assumed-v0` during shadow run.

---

## 6. Testing & QA

| Layer | What |
|---|---|
| Unit | adapter→SocialItem mapping · dedup (exact + near; link-not-drop) · velocity_z math · feature_key centroid assignment · opportunity scoring · compliance rule denylist · timing logic |
| Integration | fixture batch end-to-end (ingest→roundup) on canned data, no network |
| LLM output | schema-validate every enrich/recommend/compliance response; retry/fallback on malformed |
| Golden set | weekly 30-item spot-check (**incl. a Hinglish slice**): intent/entity precision, topic accuracy, compliance recall |
| Compliance | planted non-compliant drafts must be blocked (regression suite) |
| Dashboard | smoke: loads, filters, drill-down, feedback write |
| Templates | render every `.j2` against fixture payloads (CI) — a broken template fails the build |
| Vendored guardrails | drift check vs the comms repo; planted crypto/tip-pump items marked noise, quoted-tip complaint survives |

---

## 7. Deployment & ops

- **Processes:** ingest/enrich/aggregate/recommend/roundup as scheduled CLI runs; `read_api` + `dashboard` as long-running services (systemd/docker) behind nginx+TLS.
- **DB roles:** pipeline = read-write; API/dashboard = **read-only** (+ insert on `feedback`, update on the `opportunities` status/reason columns).
- **Secrets:** dynaconf `config/.env` (Anthropic, twitterapi.io, Slack webhook, Gmail SMTP app password, DB URL, SSO client). Never in git.
- **Jobs:** monthly partition creation; 180d retention prune for **all data** incl. rollups + roundups (raw jsonb ~60d; compliance_audit included); backups.
- **Isolation:** own DB + own service → cannot affect `nubra-ai-personalization`.

---

## 8. Observability & success metrics

- **Health:** per-source `last_success_at` + counts; alert on staleness (X 429, Reddit break).
- **Pipeline:** ingest/dedup/enrich rates, stage latency, error rate (`trace_log`).
- **Cost:** `llm_usage` + X budget; daily cost check (~$1–2/day LLM target; reduction measures in `nubra-community-manager-cost-plan-2026-07-03.md`).
- **Product success:** roundup usefulness (team tags via `feedback`), opportunity precision, coverage of known events.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| X rate-limit/cost (trial 429s) | budget cap + backoff (already in POC); paid tier for volume |
| Reddit scraper breakage | isolate adapter; health alert; graceful degrade to other sources |
| LLM cost drift / outage | Haiku for bulk + caching; keyword fallback keeps pipeline alive |
| Assumed catalog (`assumed-v0`) has a wrong fact | roundup footer flags the grounding version during shadow run; marketing's vetted publish swaps it in without a code change |
| Compliance miss | deterministic L1 rules + human backstop (no auto-post); regression suite |
| Embedding infra | local CPU model at 2k/day is cheap; Voyage fallback if needed |
| Adoption | shadow → pilot → full rollout; feedback widget from day one |

---

## 10. Out of scope for v1 (deferred)

Posting + human-approval workflow · when-to-post **automation** (we recommend timing, not act) ·
feedback-driven **self-learning** · GitHub/YouTube/Discord/Telegram/app-review adapters ·
emergent topic **clustering** · learned timing.

**React frontend migration (deferred, not rework).** Swap the Streamlit view layer for a
polished Next.js/React app against the **same FastAPI read-API** — **zero backend change**,
only the thin UI is replaced. Trigger it only when the "modern/polished" bar becomes hard
or the tool goes customer-facing. Because the read-API is the durable contract, this stays
a cheap, planned upgrade rather than a rebuild.

---

## 11. Definition of Done (v1)

- [ ] X + Reddit auto-ingested on schedule into `nubra_community`; dupes linked (never dropped); late arrivals picked up (`ingested_at` watermark).
- [ ] Every non-noise item enriched + embedded; rollups (topic/issue/feature/voice) populate with velocity + history.
- [ ] Recommend produces: opportunities (priority + grounded brand+rep drafts + when-to-post), top-3 content proposals, Nubra-watch segment — all compliance-gated + audited; hot threads + Nubra-mentions surfaced in the **hourly Slack+email heads-up (08–20 IST)** — weight-sorted actions (incl. recurrence boosts) + last-hour ops summary, all from editable templates.
- [ ] Daily (07:30) + weekly **Sat→Sat** roundup (Sat ~10:00, persistence-weighted) delivered to **Slack + email**.
- [ ] Read-only **Streamlit dashboard** live behind **SSO**, blue-dark palette, filters + drill-down + feedback + opportunity-status capture, served via the FastAPI read-API.
- [ ] Runs unattended on schedule with health alerts, retention/partition jobs, and Langfuse traces.
- [ ] Docs updated; go-live checklist signed off after shadow + pilot.
