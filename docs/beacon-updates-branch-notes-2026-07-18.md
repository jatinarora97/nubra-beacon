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

**Resolved 2026-07-18 (second pass):**
- Dual grounding RESOLVED: the social engine now reads the versioned
  `nubra_features` catalog (context-v2) — same source as drafts/briefs and the
  Grounding page; the private YAML is deleted. Reconciliation outcome: 3
  genuinely-live features added to the catalog (digital account opening/KYC,
  transparent charges, advanced charts — the last backed by our own collected
  app-store review); NOT added because the product doc forbids the claims:
  OMS V3 + News API (internal/unverified), flexible brokerage as live (doc:
  upcoming), retail basket orders (doc lists it as a competitor strength).
  Verified with a forced real run: context_version=context-v2, 31 features,
  stored recommendations' mapped features resolve to live catalog rows.
- Sources page manages all four new families (youtube_query / github_query /
  forum / app; migration 0012), collectors read DB-first, 66 targets seeded.
- YouTube per-query/per-video error isolation + daily query rotation.
- Dependency files merged into requirements.txt; Dockerfile layer folded.
- Teammate's standalone health script absorbed into ./cm doctor (four live
  collector probes added; Source-health page shares the same probe code).
  scripts/test_collectors_fetch_only.py kept (pre-deploy fetch smoke).

## Remaining issues — exactly two (+ one reminder)

1. **Briefs vs Social recommendations** (product decision): same signals,
   overlapping formats, two pages. Options: extend the repeat-judge across
   both, or retire Content briefs for direct ready-to-ship copy.
2. **Repetition guard is blind to social recs** — fix together with #1 (user
   decision 2026-07-18: these two are one workstream).

Reminder: rotate the YouTube API key + GitHub token before prod (pasted in
chat during testing).
