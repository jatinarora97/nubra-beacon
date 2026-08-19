# SSO — ON HOLD (user decision 2026-08-19); design locked, ships separately

Status: oauth2-proxy code sits inert behind its own compose profile (`sso`) —
no release, `make up`, or `--profile app up` can start it. Explore/API
releases ship unaffected. Resume when the pieces below are ready.

## The approval flow we are building (user spec, 2026-08-19)

Not-allowlisted person → attempts Google login → login succeeds with Google
but Beacon shows "access pending" → the nubra-beacon Slack channel INSTANTLY
gets a notification with approve/reject → approve adds them automatically —
zero docker commands, zero file edits.

### Architecture (replaces the static-file allowlist)

1. **oauth2-proxy does AUTHENTICATION only** (is this a real Google account:
   `email-domains=*`, no emails file). Forwards `X-Auth-Request-Email`.
2. **AUTHORIZATION moves into Beacon**: an `sso_allowlist` DB table (email,
   status pending/approved/rejected, requested_at, decided_by, decided_at).
   Next.js middleware checks the header against it (cached ~60s):
   approved → through; unknown → row created as pending + Slack notification
   fired (deduped: one ping per email per 24h) + "access pending" page.
   Instant effect on approval — nothing restarts, the next page load passes.
3. **Approve/reject — two variants, picked by ONE fact we must verify**
   (is `https://nubra-beacon.zanskar.xyz` reachable FROM THE INTERNET — i.e.
   can Slack's servers POST to it? Check with IT or from a phone off-VPN):
   - **Variant A (domain is public): true Slack buttons.** A small Slack app
     (not just the webhook) with Interactivity enabled; request URL
     `https://nubra-beacon.zanskar.xyz/api/v1/slack/interactions` (proxy
     skip_auth path). Button click → Slack POSTs (signature-verified via the
     app's signing secret) → we flip the row → Slack message updates to
     "Approved by <name>". Needs: create Slack app, enable interactivity,
     one new API endpoint + signature check.
   - **Variant B (domain is VPN-only): notification + one-click dashboard
     approval.** The Slack message (plain webhook, works today) carries
     Approve/Reject LINKS into a new Beacon "Access requests" card; clicking
     opens the dashboard (you are SSO'd) and one click decides. Slack never
     needs to reach us — only we reach Slack. Fewer moving parts; the
     notification is equally instant, approval is one extra click.
   Default to B unless public reachability is confirmed — A can be layered
   on later without rework (same table, same endpoint shape).

### Build list when SSO resumes (~1 day)

1. Migration: `sso_allowlist` table (+ seed the 6 launch emails as approved:
   jatinarora@, anuragsrivastava@, vandana@, dhanush@, subothsundar@ —
   zanskar.xyz; deepender@zanskarsec.com).
2. read-api: check endpoint + request/decide endpoints (+ Slack interactions
   endpoint if Variant A).
3. webapp: middleware.ts gate + "access pending" page + Access-requests
   admin card.
4. compose: drop `OAUTH2_PROXY_AUTHENTICATED_EMAILS_FILE` (table replaces it).
5. Slack: Variant A = new Slack app with interactivity; Variant B = existing
   webhook only.

## Google OAuth client — the new console flow, mapped (for when we resume)

The new Google Cloud console splits the old form into sections; only these
matter:

1. **Branding**: App name `Nubra Beacon`, user support email = yours, logo
   optional (skip). Authorized domain: `zanskar.xyz`.
2. **Audience**: choose **Internal** — CRITICAL choice: only your Google
   Workspace org can authenticate, no Google verification review, no test
   users needed, done in seconds. (External would demand a verification
   process we don't want. Note: Internal covers zanskar.xyz workspace
   accounts; deepender@zanskarsec.com can still be AUTHENTICATED only if
   zanskarsec.com is in the same Workspace org — if it is a separate org,
   Audience must be External(+test users) OR that one user gets access
   another way. Check which before creating.)
3. **Scopes**: defaults only (email/profile/openid) — add nothing.
4. **Clients**: Create client → type Web application → name
   `nubra-beacon-sso` → Authorized redirect URI:
   `https://nubra-beacon.zanskar.xyz/oauth2/callback` → copy client ID +
   secret into prod `.env` (`OAUTH2_PROXY_CLIENT_ID/SECRET`, plus
   `OAUTH2_PROXY_COOKIE_SECRET` — generate:
   `python3 -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'`).
5. Overview/Verification sections: nothing to do for Internal.

## Two facts to bring back before the resume (no other blockers)

1. Is nubra-beacon.zanskar.xyz reachable from the public internet? → picks
   Variant A or B.
2. Is deepender@zanskarsec.com in the same Google Workspace org as
   zanskar.xyz? → picks Internal vs External audience.
