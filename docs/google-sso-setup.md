# Google SSO setup — console walkthrough (do when SSO build resumes)

Prereq context and decisions: `sso-decisions-2026-08-19.md`. Time: ~15 min.
Everything happens at console.cloud.google.com (any project you own; create
"nubra-beacon" if unsure).

## 1 · Branding (2 min)

APIs & Services → OAuth consent screen (new console: "Google Auth Platform"
→ Branding):
- App name: `Nubra Beacon`
- User support email: your email
- App logo: skip
- Authorized domain: `zanskar.xyz`
- Developer contact: your email

## 2 · Audience (1 min — the decision is already made)

Choose **External**, and leave the app in **Testing** (do NOT click
"Publish app"). Why external: deepender@zanskarsec.com is outside the
zanskar.xyz Workspace org; Internal would lock him out. Testing mode skips
Google's verification review entirely.

## 3 · Test users (2 min)

Audience → Test users → Add users — paste all six:
```
jatinarora@zanskar.xyz
anuragsrivastava@zanskar.xyz
vandana@zanskar.xyz
dhanush@zanskar.xyz
subothsundar@zanskar.xyz
deepender@zanskarsec.com
```
Anyone approved LATER via the Slack flow must ALSO be added here (Testing
mode only lets listed users authenticate; cap 100). This is the one
recurring Google-side chore — two clicks per new person.

## 4 · Scopes (0 min)

Touch nothing. The defaults (openid/email/profile) are all oauth2-proxy
needs.

## 5 · The client (3 min)

Clients (or Credentials → Create credentials → OAuth client ID):
- Type: **Web application** · Name: `nubra-beacon-sso`
- Authorized redirect URI (exact): `https://nubra-beacon.zanskar.xyz/oauth2/callback`
- Create → copy the **Client ID** and **Client secret**.

## 6 · Into prod .env (2 min)

```
OAUTH2_PROXY_CLIENT_ID=<client id>.apps.googleusercontent.com
OAUTH2_PROXY_CLIENT_SECRET=GOCSPX-<client secret>
OAUTH2_PROXY_COOKIE_SECRET=<generate: python3 -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'>
BEACON_SSO_REDIRECT_URL=https://nubra-beacon.zanskar.xyz/oauth2/callback
```

## Known quirks (accepted in the decisions doc)

- Testing-mode consent screens may show an "unverified app" note to test
  users — expected, ignorable.
- Testing-mode refresh tokens expire after 7 days — we don't use refresh
  tokens (cookie sessions, 168h), so the only effect is a weekly re-login.
