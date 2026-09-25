# API-trading content queue — build plan (2026-09-09)

Goal: a "Content" page under the API Trading section holding ready-to-post,
grounded, compliance-checked briefs per platform, topped up hourly, with
Act (posted) / Dismiss buttons for the interns who seed them. It is the
API/algo-focused merge of opportunities + social recommendations.

Architecture (one codebase, reuse the social_recommend engine):

1. Migration 0018: social_recommendations + `lens` (default 'general') and
   `seed_url`; index (lens, status, day). Events table reused: act →
   'published', dismiss → 'rejected' (already in the CHECK).
2. `community/social_recommend/api_lens.py`:
   - Evidence = api_trader_items (stage <> irrelevant) fresh window, split
     seedable (friction/guidance with a real url — the intern replies in
     that thread) vs inspiration (showcase/comparison — standalone posts).
   - Features = product context (nubra_features) segment api|shared only.
   - Prompt = API-lens variant of the ready-copy prompt. Platforms:
     reddit | x | linkedin | youtube_community. Two types: seed_reply
     (helpful, discloses Nubra affiliation, answers the thread's actual
     question first) and standalone. Bans: performance/returns claims
     (NSE §5.7), competitor disparagement, hype; runs the same
     compliance_check as the general path.
   - `top_up(min_ready_per_platform, max_new)`: counts draft+api_trading
     briefs per platform, generates only the shortfall, bounded per run.
     Gated by api_trader.lens_enabled().
3. Hourly wiring: compose stage (community.compose.roundup.run) calls
   api_lens.top_up() isolated in try/except — compose already runs hourly.
4. Endpoints (api_trading_api.py, behind the same 404 gate):
   GET /api/v1/api-trading/content?platform=&status=  · POST
   /content/{id}/act · POST /content/{id}/dismiss (actor from
   X-Forwarded-Email, note optional) · POST /content/top-up (manual).
5. UI page /api-trading/content (+ sidebar entry): platform-grouped queue,
   seed/standalone badge + target-thread link, exact copy with copy
   button, grounding chips, Act/Dismiss, status filter.
6. Verify locally on the prod mirror (top_up spends a few Sonnet calls),
   npm build + SSR checks, commit, push. Prod stays dark until
   API_TRADING_ENABLED flips (section gate covers this page too).

Guardrail note for the interns' workflow: seeded replies are DISCLOSED
(one official voice), never bulk-pasted; a dismissed brief never
reappears (status change is permanent); every act/dismiss is attributed.
