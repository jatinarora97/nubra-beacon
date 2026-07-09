# Nubra Beacon

Community radar + marketing copilot for Nubra (Indian NSE/BSE + F&O broker).
Listens to X + Reddit, finds trends / broker issues / feature requests,
recommends compliant actions and content, delivers hourly heads-ups + daily
and weekly roundups — humans post, Beacon only recommends.

Docs: `docs/nubra-community-manager-status-2026-07-05.md` (what is built) ·
`docs/nubra-beacon-tech-backlog-2026-07-08.md` (what remains) ·
`docs/api-reference-2026-07-07.md` (every endpoint, tech + PM registers).

## Local development

```sh
docker compose up -d          # pgvector Postgres on :5544 (postgres only)
./cm migrate                  # apply schema (first time)
./cm run-local                # full pipeline -> out/messages/*.md + DB
./cm ui                       # dashboard :3000 + read-API :8400 (supervised)
```

### Working from prod dumps (the normal dev workflow)

Prod is the only environment that scrapes; local development runs on restored
prod data. Grab a nightly dump from the prod box (`backups/`), then:

```sh
make restore-local DUMP=beacon-prod-<date>.sql.gz   # wipes + restores local DB
./cm ui                                             # browse real prod data
./cm run-local --skip-scrape                        # re-run analysis stages on it
./cm stage <name>                                   # or one stage at a time
```

Local scraping (`./cm run-local` without the flag, or `./cm stage scrape`)
is only for testing scraper changes. Notes: analysis stages spend real LLM
money even locally; dispatch on a local machine is archive-only (channel sends
are prod-gated), so restored data can be worked on safely.

**Always use `./cm`** — it wraps the project venv locally (and falls back to
system python inside containers). Setup from scratch:
`python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
&& ./.venv/bin/python -m playwright install chromium`. Secrets in `.env`
(never committed; template `community/config/env.example`).

## Production

Dockerized: separate `api` and `webapp` images behind compose profile `app`;
the pipeline runs via host cron exec'ing into the api container. Full runbook:
**`deploy/README-prod.md`** (bring-up, data carry-over, cron, backups,
security). Paste-ready crontab: `deploy/crontab.prod`.

## Layout

`community/` pipeline stages (`scrape -> clean -> enrich -> aggregate ->
recommend -> compose -> dispatch`) + `api/ llm/ store/ config/ lib/ reference/
scheduler/` · `webapp/` Next.js dashboard · `migrations/` numbered SQL ·
`scripts/` seeds + vendor sync + maintenance · `deploy/` prod kit.
Vendored code in `community/lib/` is refreshed by `scripts/sync_*.py` —
never hand-edit it.
