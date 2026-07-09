# Nubra Beacon — Tech Backlog (2026-07-08, prod-eve)

_The single list of everything deliberately not done at go-live. Ordered by
when it bites. Supersedes the backlog sections of the status doc and the
2026-07-07 work plan (both now point here)._

## P0 — first weeks of prod

1. **Auth (dashboard + API).** No authentication exists; the README mandates
   LAN-only ports. Plan: OIDC/SSO proxy in front of :3000/:8400; the API
   already reads `X-Auth-Request-Email` on every write — enforcement is a
   one-line reject-when-absent. All write attribution (`local-dev` today)
   becomes real. Do before anyone outside the team gets network access.
2. **Scoring-weight re-tune from prod feedback.** We went live without a
   shadow run (user decision 2026-07-08). The acted/dismissed(+reason) data
   the team generates IS the calibration set — after 1–2 weeks, re-tune the
   priority weights (30/25/15/15/15) and bars (action 60, trending 3) against
   it, in registry, with the change documented like the τ=0.86 calibration.
3. **Health alerting.** The dashboard shows freshness, but nobody watches a
   dashboard at 3am. Per-source staleness + cron-failure detection → Slack
   alerts channel (webhook already config-gated). Includes alert on
   `keyword_search`/`refresh` stats degrading (parse-fragility canary).

## P1 — before October

4. **Rolling partition job + 180d retention purge.** Monthly partitions for
   social_items/item_enrichment/item_embeddings are pre-created only through
   2026-10; inserts FAIL in November without new partitions. One maintenance
   job (cron, monthly): create month+2 partitions, drop data older than 180d
   (incl. compliance_audit — retention decision is FINAL). Parked by user
   2026-07-08 but date-bound: schedule for September.
5. **Langfuse ingestion.** Keys live in .env and the code path is verified,
   but the org's free-tier quota is exhausted ("Ingestion suspended"). Upgrade
   the plan or accept llm_usage-only metering. Verify one trace in the
   Langfuse UI when unblocked.
6. **X credits → verification sweep.** When twitterapi.io credits return:
   verify live X collection at volume, keyword fan-out queries, trend
   discovery round-trip, then raise/remove the 10-item live cap (registry).

## P2 — quality and depth

7. **feature-key hygiene.** `feat_00006` centroid has drifted center-ward
   (running-mean artifact); `feat_00019`/`feat_00020` are one genuine merge
   pair. `scripts/report_feature_clusters.py` is the evidence; do
   human-reviewed merges + consider re-anchoring drifted centroids from
   `feature_item_map` phrases.
8. **Reddit keyword search depth.** v1 is first-page, posts-only, market-term
   gated. Add pagination + optional comment fetch for high-signal keywords if
   brand-watch volume justifies it. DOM-selector fragility degrades to
   `found: 0` — pair with backlog item 3's alerting.
9. **Enrichment prompt tightening.** The 2026-07-08 E2E (1,299 items) showed
   batch chunks inventing intent labels (`pnl_sharing`, `opinion`, `other`) —
   validation caught all and sync-retried (resilience worked), but each retry
   costs. Tighten the prompt's intent instruction if prod shows the same rate.
10. **Enrichment per-run cap.** `LOCAL_MAX_ITEMS = 600` in enrich/tagger.py
    protected local spend but also throttles backlog drains (the E2E left
    ~595 items for later runs). Make it registry-configurable; hourly prod
    volume (~50–100) never hits it, only outage recovery does.
11. **stage trace_log.** llm_usage persists; stage-level run traces are still
   stdout/cron.log only. Add a run-scoped trace_log table (mirror the
   personalization pattern) when debugging prod runs gets annoying.
12. **`seed_features --from-xlsx` loader** — build when marketing's keyword
    excel + vetted catalog arrive; publish as a new grounding version.
13. **Weekly roundup history navigation** — the page shows the latest week
    only; add a week picker once 3+ weeks exist.

## P3 — product phases (unchanged design intent)

14. Posting-with-approval workflow (Slack approve/edit/skip + post_executor +
    post_log) → 15. learned posting windows (needs 14's outcome data) →
    16. self-learning from `feedback` + dismissed reasons.
17. More sources: YouTube / Telegram / app-store reviews (adapter contract
    ready), issue-type discovery via clustering at ~100+ complaints.
18. Emergent-topic discovery is live; revisit HDBSCAN params (min cluster 4)
    once `other:*` volume grows past ~500 items.

## Accepted P2s from the pre-prod review (2026-07-08, four-segment bug hunt)

Fixed in the same pass: run lock + watermark regression, morning-build import
crash, dead broker_issue scoring, hourly brief regeneration destroying edits,
per-stage isolation, batch-submit sync fallback, evening novelty consumption,
backup pipefail, registry bind-mount, refresh priority order, CSV one-time
backfill, per-query X isolation, author scoring on active topics, transactional
recomputes/publishes, revise 500→400 + instruction cap, two-clocks
standardization, Opportunities all-open default, Load-more race. Deliberately
NOT fixed (tracked here):

- Keyword-found Reddit posts keep snippet text forever if later reachable via
  subreddit collection (insert-if-absent skips the fuller copy) — revisit with
  keyword-search depth (item 8).
- Derived Reddit comment-id collisions (same author, near-identical short
  replies) silently drop a comment; edited comments re-fetch as new rows.
- Explore offset pagination can duplicate a row across pages while the table
  moves under it (live inserts / engagement refresh reordering).
- Single-endpoint failures render as truthful-looking empty states (get()
  fallback); only full API/DB-down shows the red banner. Now at least logged
  client-side; a per-page "could not load" state is the real fix.
- serve.py dev supervisor has no crash-loop backoff (prod uses compose).
- Windowed /features builds unbounded item_id arrays before sampling (fine at
  current scale).
- Brief revisions have no row lock — simultaneous revisions last-write-win.
- est_llm_usd stage stat hardcodes Haiku rates (llm_usage is the real meter);
  score stats key still says new_ge70 though the bar is 60.
- `make pull-prod` mid-cron-run kills that run; watermarks recover next hour
  (in-flight Anthropic batch is paid-but-discarded). Operational note.

## Docs state

- `nubra-community-manager-status-2026-07-05.md` — "what is built" authority.
- `nubra-beacon-workplan-2026-07-07.md` — executed 2026-07-07/08; historical.
- Design docs / LLDs (2026-06-29 → 2026-07-03) — carry a stale-banner as of
  2026-07-08; kept for rationale, not current mechanics. This file + the
  status doc win every conflict.
