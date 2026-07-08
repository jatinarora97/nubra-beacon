# Nubra Beacon — prod deployment

Two Docker images (backend `api`, frontend `webapp`) plus pgvector Postgres,
orchestrated by docker compose. The pipeline is NOT a daemon — the host
crontab execs `./cm` inside the running api container on the designed
cadence. Everything below happens on the prod machine.

## 1 · Bring-up

```bash
git clone https://github.com/jatinarora97/<repo>.git /opt/nubra-beacon
cd /opt/nubra-beacon

# secrets — never committed; template: community/config/env.example
cp community/config/env.example .env
#   REQUIRED: ANTHROPIC_API_KEY
#   X:        TWITTERAPI_IO_KEY            (live X collection)
#   Slack:    SLACK_WEBHOOK_URL            (heads-ups, roundups, overview)
#   Email:    GMAIL_SENDER, GMAIL_APP_PASSWORD (+ recipients in registry.yaml)
#   Traces:   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

# full stack (postgres + api + webapp). First build ~10 min.
docker compose --profile app up -d --build

# schema + seeds (fresh DB only)
docker compose exec api ./cm migrate
docker compose exec api python scripts/seed_features.py
docker compose exec api python scripts/seed_sources.py
```

Dashboard: http://<prod-host>:3000 · read-API: http://<prod-host>:8400/docs

## 2 · Cron (the heartbeat)

Edit `deploy/crontab.prod` — set `APP_DIR` to the clone path — then:

```bash
crontab -l > /tmp/cur 2>/dev/null; cat /tmp/cur deploy/crontab.prod | crontab -
```

(or paste it via `crontab -e`). Cadence: hourly pipeline 07:00–00:00 IST,
06:00 morning build, Saturday 10:00 weekly roundup, 02:00 nightly DB backup.
`./cm schedule --docker` prints the same block. Logs land in `out/cron.log`.

## 3 · Backups

`deploy/backup.sh` (cron, 02:00) writes gzipped `pg_dump`s to `backups/`,
keeping the last 14. Restore into a fresh stack:

```bash
gunzip -c backups/nubra_community-<stamp>.sql.gz \
  | docker compose exec -T postgres psql -U community -d nubra_community
```

## 4 · Day-2 operations

```bash
docker compose ps                                  # health (both healthchecks wired)
docker compose logs -f api                         # API logs
docker compose exec api ./cm run-local             # manual pipeline run
docker compose exec api ./cm stage <name>          # single stage
docker compose --profile app up -d --build         # deploy a new version (then re-run migrate)
tail -f out/cron.log                               # pipeline runs
```

The api container mounts `./out` (message archives + cron log) and a named
volume for the embedding-model cache (first enrich run downloads
multilingual-e5-small once, ~450 MB, then it's warm).

## 5 · Security note — read before exposing anything

There is NO auth on the dashboard or API yet (auth is the top parked item).
Ports 3000/8400/5544 must stay LAN/VPN-only or firewalled to the team.
Postgres credentials are the compose defaults — acceptable only while the DB
port is not internet-reachable; harden before any public exposure.

## 6 · What's intentionally NOT here

- Rolling partition creation + 180d retention purge — parked (partitions
  pre-created through 2026-10; revisit before October).
- nginx/TLS reverse proxy — add when the dashboard gets a hostname + auth.
- Shadow-run calibration — running in prod per user decision 2026-07-08;
  weights re-tune after 1–2 weeks of team feedback.
