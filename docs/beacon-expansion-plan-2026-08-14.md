# Beacon expansion plan (2026-08-14)

Supersedes `partner-api-plan-2026-08-14.md`. Five workstreams, ordered by
value-per-day. Total: ~6.5 build days spread across runs.

To start work the user provides, in this order:
1. `SLACK_WEBHOOK_URL` into prod `.env` (2 min — unblocks workstream 1)
2. "go" on the API phases (nothing else needed)
3. Later: Google OAuth client (SSO) + `GEMINI_API_KEY` (content gen)

| # | Workstream | Effort | Blocked on |
|---|---|---|---|
| 1 | Slack hourly digest | 0.5 day | Slack webhook (user, 2 min) |
| 2 | Partner read API | 1.5 days | nothing |
| 3 | SSO login | 1 day | Google OAuth client (user) |
| 4 | Logins dashboard tab | 0.5 day | SSO shipped |
| 5 | Content generation v2 | 2 days proto + 1 day integrate | GEMINI_API_KEY + user review gate |

---

# Workstream 1 — Slack hourly digest (0.5 day)

## What you get

Every hour, one Slack message with three blocks:

1. **The hour in numbers** — posts collected, analyzed, noise filtered,
   duplicates merged (the same numbers the Overview page tiles show).
2. **Trends right now** — topics moving this hour with their counts
   (e.g. "CAS rollback anger — 14 posts, up from 3").
3. **Top 5 actionables, each with a WHY and a link** — e.g. "User asking
   which app to use for trading, 2.9M-view reel — high engagement +
   question intent + no broker mentioned = open field. → beacon/opportunities"
   The link lands on the Beacon page where the compliant draft reply is
   already waiting.

## How (technical)

Beacon already composes an hourly Slack overview message — the code path
exists and self-skips because `SLACK_WEBHOOK_URL` was never provided. Work:

1. Extend the existing compose step: add trends block (topic rollups, same
   math as the Trends page) and top-5 block (opportunities with
   `score >= 60` action bar, reasons from the existing scoring components:
   engagement, recurrence, audience, intent).
2. Deep links: `delivery.dashboard_url` registry knob + route anchors
   (`/opportunities`, `/briefs?day=`). Already how the overview message
   links home.
3. Slack Block Kit layout (sections + buttons), emoji-free.
4. Test with real pipeline output on the restored prod dump; verify links.

User action: create an incoming webhook in the team Slack workspace, put it
in prod `.env` as `SLACK_WEBHOOK_URL`. Everything else is already wired.

---

# Workstream 2 — Partner read API (1.5 days)

## Plain English (for PMs — read only this half if you want)

**What it is.** Other internal teams want to pull Beacon's data into their
own tools instead of reading our dashboard. We give them 7 read-only URLs.
They call a URL, they get JSON back. They can't change anything — reading
only.

**What each URL answers, with a Beacon example:**

1. `/items` — "Give me everything people posted since Monday."
   Example: every tweet, reddit post, and Instagram reel mentioning margin
   penalties this week, with author, engagement, and Beacon's topic tag.
2. `/items/search` — "Find posts saying THIS phrase."
   Example: `"option chain" OR "strategy builder"` returns matching posts
   with the matching sentence highlighted.
3. `/authors` — "Who talks about this stuff?" People, not posts.
   Example: the finfluencers and power-users Beacon has seen, how many
   posts each, how loud their audience is.
4. `/broker-issues` + `/feature-requests` — "What are people angry about at
   each broker, and what do they wish existed?" Same data as our Issues
   heatmap and Features page.
5. `/trends` + `/runs` — "What's blowing up right now?" and "Is Beacon's
   data fresh?" (last successful collection per source).

**The house rules (in plain English):**

- **Keys, not passwords.** Each consuming team gets one secret key. Every
  request carries it. Lose it → we revoke that one key, nobody else
  affected, and we can see exactly who pulled what.
- **Rate limiting = a turnstile.** Each key gets 60 requests per minute.
  Enough to refresh a dashboard every second; not enough to accidentally
  hammer our database while the pipeline is working. Beacon's own hourly
  scrape/analyze runs are untouched — reader traffic physically cannot slow
  the pipeline because every partner query self-cancels after 2 seconds.
- **Data wrapping = every response comes in the same envelope.** You always
  get `{ "items": [...], "next_cursor": "..." }`. Got 200 results but there
  are 5,000? The `next_cursor` string is your bookmark — send it back, get
  the next page. Bookmarks don't break even if new posts arrive between
  pages (ordering is pinned to when WE ingested the item, which never
  changes).
- **We don't invent numbers.** They asked for a "relevance score 0-100" and
  a "severity" field. Beacon doesn't compute those, and a made-up number is
  worse than none. They get what we actually measure: engagement score,
  sentiment, mention counts. Documented, and they adapt (agreed stance).
- **Kill switch.** One config line turns the whole partner API off. No
  release, no restart drama.

## Technical (references the plain-English rules above)

1. New router `community/api/partner_api.py` mounted at `/api/partner/v1/*`
   in the existing read-api process. Same DB, same rollup SQL the dashboard
   uses — zero logic drift.
2. "Keys": migration `0014_partner_api.sql` → `api_keys` (key_id,
   sha256(secret), label, created_by, last_used_at, revoked_at) +
   `scripts/mint_api_key.py` (prints secret once). Header `X-API-Key`
   (Bearer also accepted). Calls logged to `compliance_audit`.
3. "Turnstile": in-app per-key limiter (60/min, registry knob) + `SET LOCAL
   statement_timeout = '2s'` + limit cap 200 + read-only SQL.
4. "Envelope": cursor = base64 keyset `(ingested_at, item_id)` — stable
   ordering, no OFFSET scans. Search = `websearch_to_tsquery` (native
   OR/quoted-phrase support) + `ts_headline` snippet; needs a tsvector
   GIN index in the same migration.
5. "Kill switch": `partner_api.enabled` in registry.yaml.

Field deviations they adapt to: our platform names emitted (twitter,
community_forum, app_review, + bonus instagram; their aliases accepted as
input) · `engagement_score`/`sentiment` instead of relevance_score ·
mention_count + engagement_sum instead of severity · `raw` passthrough minus
internal keys (s3_*, transcript/tier state).

Phase 1 (1 day): /items, /items/search, /authors, /runs + keys/limits/
cursors/audit. Phase 2 (0.5 day): /broker-issues, /feature-requests,
/trends + partner section on the dashboard API-doc page. Exposure stays
LAN/VPN-only.

---

# Workstream 3 — SSO login (1 day, moved here from the API plan)

## What you get

Opening Beacon requires a Google login with a company email. No more
open-on-LAN dashboard. Every action (adding a source, editing a brief) is
stamped with who did it.

## How (technical)

1. oauth2-proxy sidecar in docker-compose (profile `app`), Google Workspace
   OIDC, allowed domain(s) + optional email allowlist.
2. Only the proxy port stays exposed; webapp + api become compose-internal.
   Proxy routes `/` → webapp, `/api/v1/*` → api.
3. `/api/partner/v1/*` and `/health` in `skip_auth_routes` — machines keep
   using API keys (workstream 2). Humans → Google; machines → keys.
4. Free win already wired: the read-api consumes the proxy's
   `X-Auth-Request-Email` header today (Sources page `added_by`) —
   attribution starts working the moment SSO lands, zero code change.
5. Prod rollout per the manual-config rule: compose via git pull, secrets
   via .env, services rolled with `make up S=...`.

User actions: create the Google OAuth client (redirect
`http://<box>/oauth2/callback`), choose allowed domains, put client
id/secret + a cookie secret into prod `.env`.

---

# Workstream 4 — Logins dashboard tab (0.5 day, after SSO)

## What you get

A "Team activity" tab: who logged in, when last, how often, and what they
did — e.g. "3 unique users today · Priya: 14 visits this week, last seen
2:10 pm, added 2 sources, edited 1 brief."

## How (technical)

1. Migration: `user_activity` table (email, first_seen, last_seen,
   visit_count, day rollup). Written by a tiny read-api middleware that
   reads `X-Auth-Request-Email` on page-data requests (dedup to one visit
   per email per 30 min — count sessions, not clicks).
2. Actions column joins what we already attribute: `watch_sources.added_by`,
   brief edit history, feedback submissions.
3. New tab after Configure; same table components the rest of the dashboard
   uses; CSV export like other pages.

Depends entirely on SSO (without it there are no identities) — that's why
SSO moved into this plan as workstream 3.

---

# Workstream 5 — Content generation v2 (2 days prototype → user review → 1 day integrate)

## What you get

From a content brief, Beacon produces ready-to-review assets: an image
carousel (visuals generated, text crisp), a commentary script, and a
voiceover in natural Indian-accented English (Hindi second) — downloadable
from the content page. Humans still review and post.

## How (technical) — three pieces, each with a hard lesson already learned

1. **Visuals: Gemini image model ("Nano Banana", API, ~$0.04/image)**
   generates backgrounds/illustrations per slide. Text does NOT go through
   image-gen — round-2 verdict was "still looks AI generated" precisely
   because of image-gen text. Keep the proven hybrid: Nano Banana visual
   layer + our Playwright/HTML text layer (crisp typography, brand fonts)
   from `community/render/`. New credential: `GEMINI_API_KEY` (user-owed).
2. **Commentary: Haiku** (already proven in briefs/render prototype) writes
   the slide copy + reel script: commentary ABOUT the content, not reading
   the screen (locked format decision from round 1).
3. **Voice: bench 3 local models on OUR hardware, English first, Hindi
   second.** Candidates, all runnable on-system, ranked by expected
   naturalness for Indian voices:
   - Indic Parler-TTS (AI4Bharat, Apache 2.0) — built FOR Indian English +
     Hindi accents; top candidate for the "non-robotic Indian voice" ask.
   - Chatterbox multilingual (MIT) — most natural open model of 2025;
     GPU-hungry, so the bench must time it on CPU (content gen is async —
     minutes per clip is acceptable, hours is not).
   - Kokoro-82M (current, Apache) — fastest on CPU; round-2 verdict said
     pronunciations bad → stays only as fallback.
   Bench = same 30s script through all three, user picks by ear (round-3
   review). XTTS/F5 stay disqualified (non-commercial licenses).
4. Integration AFTER the user approves round-3 artifacts: `./cm stage
   render`, download buttons on the content page, chosen TTS + fonts into
   the api image (mind the qemu rule: download weights at build, never load).

Gate: prototype artifacts go to the user first. No integration day until
the verdict.

---

# Suggested order

1. Slack digest (0.5 d) — most visible daily win, unblocked by one webhook.
2. API Phase 1 → 2 (1.5 d) — team is waiting on the contract.
3. SSO (1 d) → Logins tab (0.5 d) — same run, natural pair.
4. Content-gen prototype (2 d) → review gate → integrate (1 d).

Next action: drop `SLACK_WEBHOOK_URL` into prod `.env` and say "go".
