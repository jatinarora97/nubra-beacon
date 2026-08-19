# SSO rollout runbook (Google login for the dashboard)

What you get: opening nubra-beacon.zanskar.xyz requires a work Google login;
only emails in the allowlist get in; everyone else sees a sign-in page telling
them to request access in the Beacon Slack group; approval = one line + one
restart. The beacon API (:8101) is untouched — machines keep using keys.

## One-time setup, in order (~15 min total)

1. **Google OAuth client (5 min, console.cloud.google.com)**
   APIs & Services → Credentials → Create credentials → OAuth client ID →
   type "Web application" → name "Nubra Beacon SSO" → Authorized redirect URI:
   `https://nubra-beacon.zanskar.xyz/oauth2/callback` → Create.
   Copy the client ID + secret. (If the consent screen asks: internal user
   type, app name Nubra Beacon — no scopes beyond default email/profile.)

2. **Prod `.env` — add four lines** (cookie secret generated on the spot):
   ```
   OAUTH2_PROXY_CLIENT_ID=<from step 1>.apps.googleusercontent.com
   OAUTH2_PROXY_CLIENT_SECRET=GOCSPX-<from step 1>
   OAUTH2_PROXY_COOKIE_SECRET=<run: python3 -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'>
   BEACON_SSO_REDIRECT_URL=https://nubra-beacon.zanskar.xyz/oauth2/callback
   ```

3. **Prod allowlist file** — create `deploy/beacon-allowlist.txt` next to your
   docker-compose.yml (VM copy is yours to manage, like the Makefile):
   ```
   jatinarora@zanskar.xyz
   anuragsrivastava@zanskar.xyz
   vandana@zanskar.xyz
   dhanush@zanskar.xyz
   deepender@zanskarsec.com
   subothsundar@zanskar.xyz
   ```

4. **Prod docker-compose.yml — add the oauth2-proxy service** (your compose is
   hand-managed; paste the whole `oauth2-proxy:` block from the repo's
   docker-compose.yml, added there 2026-08-19). Only prod-specific check: pick
   the host port. The repo block publishes `4180:4180`.

5. **Start it**: `docker compose --profile app up -d oauth2-proxy`
   (or your `make up S=oauth2-proxy`).

6. **Repoint the front** — whoever manages the reverse proxy serving
   nubra-beacon.zanskar.xyz changes its upstream from the webapp's host port
   to `:4180` on the same VM. This is THE cutover moment: before it, the site
   is open as today; after it, Google login required. (Optionally afterwards:
   remove the webapp's host port from compose so the only way in is through
   the proxy.)

7. **Verify**: incognito browser → nubra-beacon.zanskar.xyz → Google sign-in →
   an allowlisted account lands on the dashboard; a non-allowlisted account
   gets the sign-in page with the "request access in Slack" footer.

## Daily operation

- **Approve someone**: they post their email in the Slack group → you add one
  line to `deploy/beacon-allowlist.txt` on the VM → `docker compose restart
  oauth2-proxy` (seconds). Remove access = delete the line + same restart.
- **Free win, automatic**: the proxy forwards `X-Auth-Request-Email`, and the
  read-API already records it — Sources adds and similar actions become
  attributed to real people the moment SSO is live.
- The repo's `deploy/beacon-allowlist.txt` is the seed/reference; the VM copy
  is authoritative (manual-config rule).

## Known limits (deliberate, v1)

- The api container still publishes its host port (:8101 on prod) carrying
  BOTH the key-authed /api/beacon/* AND the internal /api/v1/* — same
  LAN-trust posture as today. Closing /api/v1 to LAN callers is a follow-up
  (bind api internal-only + route everything through the proxy) — do it only
  after confirming nothing else on the network calls /api/v1 directly.
- Login page is oauth2-proxy's stock page with our banner/footer text.
- The "logins dashboard tab" (who logged in when) is the next build on top of
  this — it needs SSO live first to have identities to count.
