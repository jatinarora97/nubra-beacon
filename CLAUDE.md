# Nubra Community Manager

Community radar + marketing copilot for Nubra (Indian NSE/BSE + F&O broker): listens to
X + Reddit, finds trends / broker issues / feature requests, recommends compliant
actions and content — humans post. Pipeline packages map 1:1 to stages:
`community/scrape/ clean/ enrich/ aggregate/ recommend/ compose/ dispatch/`.

## Start here

1. **`docs/nubra-community-manager-status-2026-07-05.md`** — the living state doc:
   vision, what's built+verified, deviations from the design docs, backlog. It WINS
   over every other doc where they conflict.
2. Design docs (same folder) for rationale/mechanics — note they predate the
   restructure, the React UI, and several calibrations (listed in the status doc §3).

## Essentials

- Run: `docker compose up -d` then `./cm run-local` (E2E) · `./cm stage <name>` ·
  `./cm ui` (React app :3000 + read-API :8400) · `./cm migrate` · `./cm schedule` ·
  `./cm morning-build`. ALWAYS `./cm`, never bare python (deps live in `.venv/`).
- Config: `.env` (secrets; template `community/config/env.example`) +
  `community/config/registry.yaml` (thresholds, taxonomy, cadences — calibrations are
  commented with dates). Collection sources are DB-managed (`watch_sources`, UI Sources
  page) — registry lists are only the seed.
- Vendored code (comms guardrails, reddit scraper) is refreshed via
  `scripts/sync_*.py` — never hand-edit `community/lib/*`.
- DB: pgvector Postgres in Docker, :5544. POC archived in `poc/` (also the reddit
  scraper upstream checkout — `git pull` there before re-vendoring).

## Locked decisions — do NOT re-open

180d retention for ALL data incl. compliance_audit · Gmail SMTP not SES · build on
`assumed-v0` grounding until marketing's versioned swap · vendored zanshash scraper is
the ONLY Reddit transport (no JSON fallback) · one prod-grade codebase, no local/prod
forks · React UI (Streamlit rejected) · emoji-free system chrome · centroid τ=0.86 and
action bar 60 are measured calibrations (re-tune only with shadow-run data).
