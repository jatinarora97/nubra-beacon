# Social recommendations

## Purpose

This module turns Beacon's collected evidence into ready-to-publish social
content grounded in Nubra's product context. It is separate from the existing
Content briefs feature:

- **Content briefs** provide creator production plans.
- **Social recommendations** put exact copy first and keep the evidence,
  feature mapping, timing and visual direction behind expandable details.

The public copy is always the finished marketing message. Internal instructions
such as "create a post", "marketing team should", "content angle", or labelled
Hook/Body/CTA templates are rejected before storage. Internal rationale and
production direction live only in the collapsed supporting details.

Nothing is published automatically. A user must review and approve the copy.

## Isolation contract

The module is an additive subsystem:

- It owns only the `social_recommendation_*` tables introduced by migration
  `0011_social_recommendations.sql`.
- Its API lives under `/api/v1/social-recommendations`.
- Its product context is read from
  `data/nubra_context/social_features.yaml`.
- It reuses the shared Claude client and `ANTHROPIC_API_KEY` but does not change
  the existing enrichment, opportunity, draft or roundup logic.
- A missing key produces a stored `skipped` run.
- Invalid Claude output, failed grounding, failed compliance, missing context,
  or database errors are caught inside the module.
- The morning scheduler wraps the entire optional stage in a second defensive
  boundary and continues to compose/dispatch even if importing the module fails.
- The frontend fetch helper soft-fails to an empty state, so this page cannot
  break another dashboard route.

## Data flow

1. `community.social_recommend.evidence` reads recent, non-noise,
   non-duplicate rows from `social_items` and `item_enrichment`.
2. Evidence is deduplicated, ranked with engagement/recency/intent signals,
   capped per source, and split into `retail` and `api`.
3. Relevant features are selected from the versioned Nubra context.
4. One bounded evidence pack is sent through the existing Claude client.
5. Pydantic validates the structured response.
6. Grounding validates every feature ID, evidence item ID and segment.
7. Existing deterministic and Claude compliance gates review the exact copy.
8. Passed recommendations are stored. Page refreshes read stored results and
   never call Claude.

## Product context

`data/nubra_context/social_features.yaml` contains:

- audience personas;
- live and upcoming status;
- retail/API/shared classification;
- detailed feature descriptions;
- surfaces and applicable personas;
- matching terms;
- claim guardrails;
- flexible brokerage details.

Update the context version whenever product claims change. Live features may be
described as available. Upcoming features must always be presented as upcoming,
planned or under development.

## API

- `GET /api/v1/social-recommendations/status`
- `GET /api/v1/social-recommendations/preview?days=30`
- `GET /api/v1/social-recommendations`
- `POST /api/v1/social-recommendations/generate` with `{"days": 30}`
- `POST /api/v1/social-recommendations/{id}/edit`
- `POST /api/v1/social-recommendations/{id}/status`

The preview endpoint does not call Claude or write data. It is useful for
checking evidence and context readiness before deployment.

## Operations

After deployment:

```bash
./cm migrate
./cm stage social
```

The morning build runs the module after existing drafts and before the roundup.
The hourly pipeline also sees the stage, but scheduled calls are cached after
the first run of the IST calendar day and do not call Claude again. The
dashboard's **Generate latest** action explicitly forces a new stored set.
Status is recorded under pipeline stage `social_recommend` and source
`ready_copy`.

## Verification

Run:

```bash
pytest -q tests/test_social_recommendations.py
python -m compileall community/social_recommend community/api/social_recommend_api.py
cd webapp && npm run lint && npm run build
```

Real generation additionally requires collected evidence, migrated Postgres and
`ANTHROPIC_API_KEY`. Unit and frontend tests do not require the key.
