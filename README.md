# Nubra Community Manager

Listens to Indian trading communities (X + Reddit), understands what's trending /
breaking / requested, and recommends compliant actions — heads-ups and roundups for
the team. Design docs in `docs/` (build plan = master). POC archived in `poc/`.

## Quickstart (local)

```sh
docker compose up -d          # pgvector Postgres on :5544 (first time)
./cm migrate                  # apply schema (first time)
./cm run-local                # full pipeline → out/messages/*.md
```

**Always use `./cm`** (wraps the project venv) — plain `python runner.py` will hit
missing-library errors because dependencies live in `.venv/`, not system Python.

Setup from scratch: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
&& ./.venv/bin/python -m playwright install chromium`. Secrets in `.env` (never committed).

Useful:
```sh
./cm stage ingest|dedup|enrich|aggregate|score|recommend|roundup   # single stage
./.venv/bin/python scripts/refresh_local_data.py   # LOCAL ONLY: re-run on existing data as if fresh
./.venv/bin/python scripts/seed_features.py        # (re)seed assumed-v0 nubra_features
```

Local-mode notes: delivery writes markdown to `out/messages/` (prod: Slack + email);
X live fetch is capped at 10 items (config) and flagged in every ops summary; Reddit
live fetch requires a network that doesn't block reddit.com.
