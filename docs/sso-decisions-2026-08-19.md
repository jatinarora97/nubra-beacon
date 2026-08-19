# SSO — decisions (LOCKED 2026-08-20; BUILT 2026-08-20 — awaiting the 3 go-live steps below)

Setup steps live separately in `google-sso-setup.md`. This file is the WHAT
and WHY.

## Locked decisions

1. **Authentication = Google via oauth2-proxy** in front of the webapp
   (compose service exists, profile `sso`, cannot start via any release path).
   The beacon API (:8101) stays key-authed, outside SSO.
2. **Authorization = Beacon's own DB table** (`sso_allowlist`), NOT a static
   file: instant effect, no docker commands, full audit (who approved whom,
   when).
3. **Approval flow = Variant A, real Slack buttons** (locked 2026-08-20:
   nubra-beacon.zanskar.xyz IS publicly reachable, so Slack's servers can
   POST to us). Unknown-but-authenticated user → "access pending" page →
   instant message in #nubra-beacon with Approve/Reject buttons → click
   flips the DB row (Slack signature verified) → message edits itself to
   "Approved by <name>" → user's next page load is in.
4. **Approval authority = the channel**: anyone in #nubra-beacon can decide
   (user intent: "approve through slack group"). Tighten later if needed.
5. **Google audience = External, Testing mode** (locked 2026-08-20:
   deepender@zanskarsec.com is outside the zanskar.xyz Workspace org).
   Everyone is added as a test user (cap 100 — plenty). No Google
   verification review. Known quirk: Testing-mode refresh tokens expire in
   7 days — irrelevant to us, oauth2-proxy runs cookie sessions (168h);
   people just sign in again weekly.
6. **Launch allowlist** (seeded as approved in the table): jatinarora@,
   anuragsrivastava@, vandana@, dhanush@, subothsundar@ — zanskar.xyz —
   plus deepender@zanskarsec.com.
7. Rider feature after SSO ships: the logins/"Team activity" dashboard tab
   (needs identities, which SSO provides via X-Auth-Request-Email — the
   read-api already consumes that header for attribution).

## Go-live steps (ONLY these remain — everything below this section is BUILT)

1. USER: Slack app (5 min) — api.slack.com/apps -> Create (Blank app) ->
   Interactivity ON with request URL
   https://nubra-beacon.zanskar.xyz/api/v1/slack/interactions -> add an
   Incoming Webhook to #nubra-beacon under this app (replace the old
   standalone webhook's URL in prod .env) -> copy Signing Secret ->
   prod .env: SLACK_SIGNING_SECRET=...
2. USER: prod release cycle (code is on the branch) + start the proxy:
   docker compose --profile sso up -d oauth2-proxy
   (the 4 OAUTH2_PROXY_* .env lines are already parked in prod .env).
3. USER/IT: cutover — repoint the front for nubra-beacon.zanskar.xyz to
   :4180. Before this moment nothing changes for anyone; after it, Google
   login + the approval flow are live. Also remember: each newly approved
   person needs 2 clicks in Google console -> Audience -> Test users.

## Build list — DONE 2026-08-20 (for the record)

1. Migration: `sso_allowlist` (email, status pending/approved/rejected,
   requested_at, decided_by, decided_at) + seed the 6 launch emails.
2. read-api: authz check endpoint · access-request creation (dedup one Slack
   ping per email per 24h) · `/slack/interactions` endpoint with signing-
   secret verification (proxy skip_auth path).
3. webapp: `middleware.ts` gate on X-Auth-Request-Email (60s cache) +
   "access pending" page.
4. compose: drop the emails-file mount from oauth2-proxy (table replaces it).
5. Slack: upgrade from bare webhook to a Slack APP with Interactivity
   enabled, request URL `https://nubra-beacon.zanskar.xyz/api/v1/slack/interactions`
   (user creates at api.slack.com; needs the app's signing secret in .env).
6. Cutover: the reverse proxy serving nubra-beacon.zanskar.xyz repoints its
   upstream from the webapp port to :4180.

## User-owed inputs at build time

Google client ID/secret (per google-sso-setup.md) · Slack app signing secret
+ bot token (guided at build) · the reverse-proxy repoint (IT/whoever manages
the front).
