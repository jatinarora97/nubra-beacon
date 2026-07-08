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
9. **stage trace_log.** llm_usage persists; stage-level run traces are still
   stdout/cron.log only. Add a run-scoped trace_log table (mirror the
   personalization pattern) when debugging prod runs gets annoying.
10. **`seed_features --from-xlsx` loader** — build when marketing's keyword
    excel + vetted catalog arrive; publish as a new grounding version.
11. **Weekly roundup history navigation** — the page shows the latest week
    only; add a week picker once 3+ weeks exist.

## P3 — product phases (unchanged design intent)

12. Posting-with-approval workflow (Slack approve/edit/skip + post_executor +
    post_log) → 13. learned posting windows (needs 12's outcome data) →
    14. self-learning from `feedback` + dismissed reasons.
15. More sources: YouTube / Telegram / app-store reviews (adapter contract
    ready), issue-type discovery via clustering at ~100+ complaints.
16. Emergent-topic discovery is live; revisit HDBSCAN params (min cluster 4)
    once `other:*` volume grows past ~500 items.

## Docs state

- `nubra-community-manager-status-2026-07-05.md` — "what is built" authority.
- `nubra-beacon-workplan-2026-07-07.md` — executed 2026-07-07/08; historical.
- Design docs / LLDs (2026-06-29 → 2026-07-03) — carry a stale-banner as of
  2026-07-08; kept for rationale, not current mechanics. This file + the
  status doc win every conflict.
