# jatin/beacon-updates — first-build notes (2026-07-18)

Teammate's `feature/deploy-extra-sources` merged onto current main (clean, no
conflicts) with the agreed adjustments. Verified on local; NOT merged to main.

## What was verified working

- All 17 unit tests pass (first committed tests in the repo).
- All four collectors fetch REAL data with the supplied keys: Nubra App Store
  reviews ("stability needs to come" / "advanced charts are free here"),
  competitor GitHub issues (Kotak Neo API users asking for historical data),
  TradingQnA forum threads, YouTube comments on Nubra videos.
- Social engine ran end-to-end: 3 recommendations stored, 3 dropped by its own
  cross-segment validation; same-day guard confirmed (hourly reruns are cached,
  no repeat Sonnet spend).
- Source health page rebuilt to the agreed bar: "Run live checks" probes every
  source API on demand (twitterapi auth, reddit preflight, YouTube key, GitHub
  rate limit, forum + App Store reachability) alongside stored run state.
- Nav per decision: Social recommendations under What to make below Content
  briefs; Source health in its own Health section after Learn.

## Fixes made during the merge

- Migration runner now self-heals pre-existing DBs (adds the `dirty` column,
  relaxes the legacy NOT NULL `sha256`) — it previously only worked on fresh
  DBs, which is why prod was fine and local crashed.
- pytest added as a dev dependency.

## Issues to address after first-build review (ordered)

1. **Dual grounding — CONFIRMED drifting already.** The social engine reads
   its own `data/nubra_context/social_features.yaml`: 58 features, **19 marked
   live vs 15 live in context-v1** (the product-doc-derived catalog the
   Grounding page owns). Four capabilities are being called live in social
   copy that the product doc does not map as live. Decision made 2026-07-18:
   run as-is for the first build; rewire to `nubra_features` (or generate the
   YAML from it) before this branch reaches prod.
2. **Repetition guard does not cover social recs.** Briefs and social recs
   consume the same signals and overlapping formats; the repeat-judge only
   sees briefs. Deferred by user decision (may instead retire briefs).
3. **Social recs bypass the Grounding-page approval flow** — copy claims are
   validated against the YAML, not the human-editable catalog (same root as 1).
4. GitHub/YouTube keys were pasted in chat for testing — rotate before prod.
5. `requirements-extra-sources.txt` is a second dependency file — fold into
   the main requirements + Dockerfile layer story when this stabilizes.
6. Their `source_health_check.py` / smoke scripts overlap `./cm doctor` —
   converge later (doctor could absorb the per-collector probes).
