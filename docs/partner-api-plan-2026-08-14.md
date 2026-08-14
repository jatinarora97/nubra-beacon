# Partner read API + SSO — implementation plan (2026-08-14, plan only)

Team ask: 7 read-only JSON/REST endpoints (items, search, authors,
broker-issues, feature-requests, trends, runs) + bearer/API-key auth,
opaque cursors, ISO8601 UTC. Our stance (user decision): we expose what OUR
system already computes and trusts — same tables the dashboard reads — and
the consumer adapts. No parallel logic, no invented numbers, no impact on
pipeline speed or dashboard accuracy.

## 0 · Shape of the solution

One new FastAPI router `community/api/partner_api.py` mounted into the
EXISTING read-api process under `/api/partner/v1/*`. Same container, same
DB, zero new infra. Isolation is logical, not physical:

- API-key auth middleware applies ONLY to this namespace (internal
  dashboard routes untouched).
- Every partner query runs with `SET LOCAL statement_timeout` (2s) and a
  hard `limit` cap (200) — a slow or hostile query cancels itself before it
  can contend with the pipeline.
- In-app rate limit per key (60 req/min default, registry knob). They poll;
  this is generous.
- Read-only by construction (SELECTs only; optionally `SET TRANSACTION READ
  ONLY` as belt).
- Every call logged to `compliance_audit` (key id, route, params, rows) —
  consistent with the audit posture.

Why not a separate service: one prod-grade codebase (locked decision), the
read-api is already the single query layer, and partner load is polling-
scale. If usage ever grows real, the escape hatch is a PG read replica —
not a rewrite.

## 1 · Endpoint mapping (their ask → our source of truth)

| Their endpoint | Backed by | Fit | Deviations we ship (they adapt) |
|---|---|---|---|
| `GET /items` | `social_items` + `item_enrichment` + `authors` (same SQL family as internal `/items`) | Direct | `platform` accepts their aliases (`x`→twitter, `forum`→community_forum, `review`→app_review) but we EMIT our canonical names, and we additionally offer `instagram`. No `relevance_score` (we don't compute one): we ship `engagement_score` (unified log score), `sentiment`, `is_noise` (noise excluded by default) — honest fields instead of an invented 0-100. `topics[]` = enrichment topic_key (+ entities). `raw` passthrough included minus internal bookkeeping keys (s3_*, transcript_state, tiers_done). |
| `GET /items/search` | Postgres full-text (`websearch_to_tsquery`) over `social_items.text` | Direct after 1 migration | `q` natively supports OR and quoted phrases (PG websearch syntax). `match_snippet` via `ts_headline`. Needs a generated tsvector column + GIN index (migration 0014) — one-time build, then fast; ILIKE fallback until then. |
| `GET /authors` | `authors` + aggregates over their items | Direct | first_seen from earliest item; `topics[]` = top-N enrichment topics; `avg_relevance` → `avg_engagement` (same honesty rule). |
| `GET /broker-issues` | issue rollups (broker × issue_type segments the Issues heatmap already renders) + item links | Direct | No `severity` field exists — we ship `mention_count` + `engagement_sum` and let them derive severity. `summary` = representative quotes/entity summaries we already store. |
| `GET /feature-requests` | `feature_rollup` + `feature_item_map` (exactly-once ledger) | Direct | Category = our taxonomy; mention_count is replay-proof by construction. |
| `GET /trends` | topic rollups behind the Trends page (hourly/daily windows) | Direct | `delta_vs_prev` computed vs the previous same-length window — same math the dashboard shows, nothing new. |
| `GET /runs` | `pipeline_state` (what source-health reads) | Direct | `run_id` is synthetic (stage+source+timestamp) — we track per-source state, not run objects; fields otherwise as asked. |

Cross-cutting, as asked: ISO8601 UTC everywhere (our timestamps are tz-aware
already) · opaque `next_cursor` = base64 keyset `(ingested_at, item_id)` —
stable ordering AND faster than our internal offset pagination (no OFFSET
scans) · auth = `X-API-Key` header (also accepted as `Authorization:
Bearer`).

## 2 · Auth for machines: API keys (this run)

- New table `api_keys` (migration 0014): key_id, sha256(secret), label,
  scopes (v1: `read`), created_by, created_at, last_used_at, revoked_at.
- Minting: `scripts/mint_api_key.py` — prints the secret ONCE, stores the
  hash; revocation = one UPDATE. No UI needed in v1.
- Keys are per-consumer (one per team/tool), so usage and rate limits are
  attributable in `compliance_audit`.
- Exposure: :8400 stays LAN/VPN-only (current posture). Nothing becomes
  internet-facing in this run.

## 3 · SSO for humans: OIDC proxy (next run, as planned in the backlog)

Design (matches the backlog's "auth = OIDC proxy; LAN-only meanwhile"):

- **oauth2-proxy sidecar** in compose (profile `app`), Google Workspace as
  the OIDC provider, restricted to the company domain(s) + optional email
  allowlist.
- Topology change: today webapp (:3000) and api (:8400) are exposed
  directly. After SSO, ONLY the proxy port is exposed; webapp and api go
  compose-internal. The proxy path-routes: `/` → webapp, `/api/v1/*` → api.
  Browser API calls move behind the same origin (removes the hardcoded
  :8400 assumption — one webapp env change at release).
- **Partner API and SSO compose cleanly**: proxy `skip_auth_routes` for
  `/api/partner/v1/*` (API-key auth governs it) and `/health`. Humans →
  Google login; machines → keys. One front door, two locks.
- The proxy forwards `X-Auth-Request-Email`; the read-api ALREADY consumes
  this header for attribution (Sources page `added_by`) — dashboard actions
  become attributed to real people the day SSO lands, no code change.
- User-owed setup: create the Google OAuth client (redirect URL
  `http://<box>/oauth2/callback`), pick allowed domain(s), drop
  client-id/secret + cookie secret into prod `.env` (manual, as always).

## 4 · Build phases + touchpoints

**Phase 1 — partner API core** (items, search, authors, runs + auth/keys/
cursors/rate-limit/audit):
- `community/api/partner_api.py` (new router; all endpoint logic)
- `community/api/read_api.py` (one line: mount router)
- `migrations/0014_partner_api.sql` (api_keys + tsvector GIN index)
- `scripts/mint_api_key.py`
- `community/config/registry.yaml` → `partner_api:` block (rate limit, caps,
  enabled flag — kill switch is one registry line)
- `docs/partner-api-2026-08-14.md` (the contract doc handed to the team)

**Phase 2 — rollup endpoints** (broker-issues, feature-requests, trends):
- same router file + possibly 1-2 SQL views for stable shapes
- dashboard API-doc page gains the partner section (webapp, one page)

**Phase 3 — SSO (next run)**:
- `docker-compose.yml` (oauth2-proxy service; webapp/api port unexposing)
- webapp env: API base behind the proxy origin
- prod `.env` additions (Google client id/secret, cookie secret) — user
- prod rollout: git pull + .env + `make up S=...` per the manual-config rule

Testing protocol (house rule — real data): every endpoint exercised locally
against the restored prod dump; cursor stability verified across pages;
statement-timeout and rate-limit verified by forcing violations; one
end-to-end consumer script in `scripts/` doubling as living documentation.

## 5 · Performance/accuracy guarantees (the "no compromise" clause)

- Same tables + same rollup math the dashboard uses → zero drift by design.
- Keyset pagination + GIN-indexed search + 2s statement timeout + limit cap
  + per-key rate limit → bounded worst-case load; the pipeline's writes are
  hourly and small, uncontended by polling reads.
- Fields we don't compute (relevance 0-100, severity) are NOT faked — we
  expose the real signals and document the mapping.
- Kill switch: `partner_api.enabled: false` in the registry disables the
  namespace without a release.

## 6 · Open items needing the user (not blockers to start Phase 1)

1. Confirm consumers are internal/LAN (assumed yes — no internet exposure).
2. Who gets keys (one per consumer team/tool).
3. For SSO: Google OAuth client creation + allowed domain list.
