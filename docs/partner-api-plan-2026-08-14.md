# Partner read API + SSO — plan (2026-08-14)

Decision: new router `/api/partner/v1/*` inside the existing read-api.
Same container, same DB, same rollups the dashboard trusts. No new infra,
no parallel logic. Where their contract asks for numbers we don't compute,
we ship our real fields and they adapt (user decision).

Build starts when the user says go. Phase 1 is ~1 day of work, Phase 2 ~half
a day, SSO is its own run (~1 day incl. prod rollout).

## Their 7 endpoints → our sources (all direct fits)

| Endpoint | Backed by | What differs from their ask |
|---|---|---|
| `/items` | social_items + enrichment + authors | No `relevance_score` — we send `engagement_score`, `sentiment`, noise-filtered by default. Their platform names accepted as input; we EMIT ours (twitter, community_forum, app_review) + bonus `instagram`. `raw` included minus internal keys (s3_*, tier state). |
| `/items/search` | Postgres `websearch_to_tsquery` | Their OR/quoted-phrase syntax works natively. Needs one migration (tsvector + GIN index). `match_snippet` via ts_headline. |
| `/authors` | authors + per-author aggregates | `avg_relevance` → `avg_engagement`. |
| `/broker-issues` | issue rollups (Issues heatmap data) | No `severity` — we send mention_count + engagement_sum; they derive. |
| `/feature-requests` | feature_rollup + feature_item_map | Exact fit. Counts are replay-proof by construction. |
| `/trends` | topic rollups (Trends page data) | `delta_vs_prev` = same math the dashboard shows. |
| `/runs` | pipeline_state (source-health data) | `run_id` synthetic (we track per-source state, not runs). |

Cross-cutting, as they asked: ISO8601 UTC · opaque `next_cursor` (base64
keyset on ingested_at+item_id — stable AND faster than offset) · auth =
`X-API-Key` header (Bearer also accepted).

## Speed/accuracy guards (the no-compromise clause)

1. 2s statement timeout on every partner query — a bad query cancels itself.
2. Hard limit cap 200 rows + per-key rate limit 60/min (registry knobs).
3. Read-only SQL; every call logged to compliance_audit with key id.
4. Same tables + same rollup math as the dashboard → zero drift possible.
5. Kill switch: `partner_api.enabled: false` in registry — no release needed.

Exposure stays LAN/VPN-only. Nothing becomes internet-facing.

## API keys (this run)

1. Migration: `api_keys` table — key_id, sha256(secret), label, created_by,
   last_used_at, revoked_at.
2. Mint: `scripts/mint_api_key.py` — prints the secret once, stores the hash.
3. Revoke: one UPDATE. One key per consumer team → attributable usage.

## SSO (next run — humans via Google, machines via keys)

1. oauth2-proxy sidecar in compose, Google Workspace OIDC, company domain(s)
   only.
2. Only the proxy port stays exposed; webapp + api go compose-internal.
   Proxy routes `/` → webapp, `/api/v1/*` → api.
3. `/api/partner/v1/*` + `/health` in skip_auth_routes — API keys govern
   them. One front door, two locks.
4. Free win: the read-api already consumes the `X-Auth-Request-Email` header
   the proxy forwards — dashboard actions get attributed to real people
   with zero code change.
5. User-owed at that point: create the Google OAuth client (redirect
   `http://<box>/oauth2/callback`), pick allowed domains, put client
   id/secret + cookie secret in prod `.env` (manual, as always).

## Build order + touchpoints

Phase 1 (~1 day): `/items`, `/items/search`, `/authors`, `/runs` + keys,
cursors, rate limit, audit.
1. `community/api/partner_api.py` — new router, all logic lives here
2. `community/api/read_api.py` — one mount line
3. `migrations/0014_partner_api.sql` — api_keys + GIN index
4. `scripts/mint_api_key.py` + registry `partner_api:` block
5. `docs/partner-api-2026-08-14.md` — the contract doc handed to the team

Phase 2 (~half day): `/broker-issues`, `/feature-requests`, `/trends` +
partner section on the dashboard API-doc page.

Phase 3 = SSO run (files: docker-compose.yml, webapp env, prod .env — rolled
per the manual-config rule).

Test protocol (house rule — real data): every endpoint against the restored
prod dump; cursor stability across pages; forced timeout + rate-limit
violations; one consumer script in scripts/ that doubles as documentation.

## Open with the user (none block Phase 1)

1. Confirm consumers are internal/LAN-only (assumed yes).
2. Name who gets keys.
3. SSO run: Google OAuth client + allowed domain list.

Next action: user says "go" → Phase 1 starts on jatin/beacon-updates.
