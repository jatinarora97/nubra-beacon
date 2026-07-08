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
