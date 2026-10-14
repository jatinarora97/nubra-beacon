# Nubra Beacon — prod deployment

Two Docker images (backend `api`, frontend `webapp`) plus pgvector Postgres,
orchestrated by docker compose. The pipeline is NOT a daemon — the host
crontab execs `./cm` inside the running api container on the designed
cadence. Everything below happens on the prod machine.

## 0 · How the pieces talk (read once — everything else follows)

```
 team browser ──► webapp :3000 ──(same-origin /api/v1/* rewrite)──► api :8400 ──► postgres :5432
                     │                                                ▲
                     └── server-rendered pages fetch api directly ────┘   (compose network,
                                                                           service-name DNS)
 host cron ──► docker compose exec api ./cm run-local ──► pipeline stages write postgres
```

- **Why the dashboard never talks to Postgres:** every number on every page
  comes through the read-API — one contract, one place to audit, and the same
  queries feed Slack/email messages, so surfaces can never disagree.
- **How the API "points at" the dashboard:** it's the reverse — the dashboard
  points at the API. The browser only ever calls the webapp's own origin
  (`/api/v1/...`); Next.js transparently proxies those calls to the api
  container (baked in at image build as `http://api:8400`, resolved by
  compose's service DNS). No CORS, no exposed cross-origin URLs, and the team
  only needs to reach port 3000. Port 8400 is exposed for engineers (`/docs`),
  not required for the dashboard to work.
- **Why cron instead of a scheduler daemon:** one less always-on process to
  babysit; cron is inspectable (`crontab -l`), and a wedged run cannot take
  the API or dashboard down with it — those are separate containers.
- **Why the pipeline runs INSIDE the api container:** it needs the exact same
  python environment (Playwright Chromium for Reddit, torch for embeddings) —
  one image to build, zero environment drift between serving and processing.

## 1 · Bring-up

```bash
git clone git@github.com:jatinarora97/nubra-beacon.git /opt/nubra-beacon
cd /opt/nubra-beacon

# secrets — never committed; copy your working .env from the dev Mac,
# or start from the template: community/config/env.example
cp community/config/env.example .env
#   REQUIRED: ANTHROPIC_API_KEY
#   X:        TWITTERAPI_IO_KEY            (live X collection)
#   Slack:    SLACK_WEBHOOK_URL            (heads-ups, roundups, overview)
#   Email:    GMAIL_SENDER, GMAIL_APP_PASSWORD (+ recipients in registry.yaml)
#   Traces:   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

# full stack — two ways to get images:
#  (a) registry pull (the normal release flow, mirrors nubra-ai-personalization):
#      set RELEASE_TAG=<tag> in .env, then:
make pull-prod
#  (b) build on this machine (fallback / first bring-up without ECR access):
#      docker compose --profile app up -d --build   (first build ~10 min)

# schema + seeds (fresh DB only)
docker compose exec api ./cm migrate
docker compose exec api python scripts/seed_features.py
docker compose exec api python scripts/seed_sources.py
```

Dashboard: http://<prod-host>:3000 · read-API: http://<prod-host>:8400/docs

After bring-up, set `delivery.dashboard_url` in
`community/config/registry.yaml` to `http://<prod-host>:3000` — it's the link
at the foot of every Slack message.

## 1b · Carrying over the local data (instead of a fresh start)

To go live with the populated dev database (items, enrichment, embeddings,
history) rather than empty tables, dump on the dev Mac and restore on prod
BEFORE the first cron run:

```bash
# dev Mac
docker exec nubra-community-postgres pg_dump -U community nubra_community | gzip > beacon-dev.sql.gz
scp beacon-dev.sql.gz produser@prodhost:/opt/nubra-beacon/

# prod (fresh stack up, BEFORE migrate/seeds — the dump carries schema + data)
gunzip -c beacon-dev.sql.gz | docker compose exec -T postgres psql -U community -d nubra_community
docker compose exec api ./cm migrate     # no-op if the dump is current; safe either way
```

Skip the seed scripts in that case — the dump already contains sources,
features, and all history. This is also the pattern for the "give it the
populated postgres and test" workflow: restore any dump, then exercise
existing/new functionality against real data.

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
make pull-prod                                     # deploy the RELEASE_TAG in .env (pull + up + migrate)
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

## Health alerts (Slack)

Design: `docs/superpowers/specs/2026-10-05-slack-health-alerts-design.md`. Everything
ships in the image; the VM needs these one-time manual edits, in this order:

1. `.env`: set the new `RELEASE_TAG` and add `SLACK_ALERTS_WEBHOOK_URL=<incoming webhook
   for the alerts channel>` (NOT the SSO approvals webhook).
2. `make pull-prod` (the `migrate` service creates `job_runs`, `health_state`,
   `resource_samples` before `api` starts).
3. AFTER step 2 (a cron line added earlier fails against the old image): add the
   `*/20 ... ./cm watchdog` and `08:05 IST ... ./cm health-digest` lines from
   `crontab.prod` / `crontab.prod.utc` (UTC box: digest is `35 2 * * *`), and append
   `&& touch out/.backup_ok` to the backup line.
4. Prove the webhook: `docker compose exec api ./cm watchdog --test-message`.
5. Optional: copy the `health:` block from `community/config/registry.yaml` into the
   VM's own `registry.yaml` to tune thresholds (defaults apply without it).

## Reddit via Apify (go-live)

Reddit comes from Apify (actor `harshmaur~reddit-scraper-pro`; the vendored old.reddit scraper is dead).
The code ships in the image and is OFF until switched on. The prod VM mounts NO registry file (its compose
file has none, so the container uses the registry baked into the image), so the switch is in `.env`; three
host-side edits (`.env` and crontab are manual):

1. `.env`: `APIFY_TOKEN` set (already there if Instagram/LinkedIn run). Reddit shares the Apify credits;
   the existing `credits:apify_*` health alert covers the monthly cap.
2. `.env`: add `REDDIT_APIFY_ENABLED=true`. The baked-in `sources.reddit_apify` block already carries the
   actor, post budgets, India filter and spend cap; changing those means a new image, or optionally
   mounting a registry file: copy it out (`docker compose cp api:/app/community/config/registry.yaml
   community/config/registry.yaml`), add `- ./community/config/registry.yaml:/app/community/config/registry.yaml:ro`
   under the api `volumes:` as the repo's `docker-compose.yml` does, and `docker compose up -d`.
3. crontab: the `source reddit_apify` line from `crontab.prod` / `crontab.prod.utc` (01:00 IST = 19:30 UTC).
   Do this AFTER `make pull-prod` (an older image has no such source).
4. First run by hand, then `./cm doctor` and the Sources page. The nightly default (2-day window, 10 posts per
   subreddit, 25 for the `post_overrides` ones) reads only the newest posts, so a real backfill needs both flags:
   `docker compose exec -T api ./cm source reddit_apify --days 14 --posts 100` (one-off, the registry is untouched;
   roughly $5-10 - the per-run cap `max_charge_usd` still applies). Check the Apify headroom first
   (`./cm doctor`, the Instagram line: "$X of $Y used this cycle"): the backfill stops by itself at the
   account line below, so on a nearly full plan it will only get part of the way.

What switching on does: the hourly ingest stops calling the vendored scraper, the old.reddit engagement
refresh and the old keyword search (they were no-ops/failures); the engagement refresh of suggested
threads runs once a day in the morning build through Apify; `./cm doctor`, the health digest and the
Source-health page gain a `reddit_apify` row. The health monitor expects the 01:00 job only from its first
run, so enabling it mid-day cannot page a false alert.

Cost: $0.01 per run + about $0.0014 per row; one run per watched subreddit (the actor's post cap is one total
per run, so batching starves the busy subreddit's neighbours) + a few search runs. Ceiling about $2-2.5 a
night (about $60-75 a month; typically less, most subreddits are quiet); every run is capped by
`max_charge_usd` (default 2.0). Levers: `comments_per_post`, `max_posts_per_sub`, `post_overrides`,
`date_limit_days` (default 2), `listing_subs_per_run`. Keyword hits must show an India signal
(`keyword_india_only`, default on).

Shared Apify account: Reddit, Instagram and LinkedIn draw on ONE monthly usage limit (on 2026-10-11 the
account showed $21.27 of $29 used). Reddit therefore refuses to start a run once the account is 85% into its
limit (`account_stop_pct`, leaving the rest for the others) and stops a job after `nightly_budget_usd` (2.5;
a full night measured about $1.7-2.0).
A job stopped part-way keeps what it fetched and is recorded as an error, so the digest and the Source page
show it; a job that could not start at all fails with the reason. Reddit at the full scope (~$60-75 a month)
needs a larger Apify monthly limit; at $29 it can only run a reduced scope (e.g. `comments_per_post: 0`).
Both guards take `null` to switch them off. Because a budget can stop a job part-way, the order is fixed by
value: keyword searches first, then the `priority_categories` subreddits (default brokers, fno_algo), then the rest.

Rollback: remove `REDDIT_APIFY_ENABLED` from `.env` (or set it to false) and `docker compose up -d`: the old
path comes back unchanged; remove the cron line.

Useful: `./cm watchdog --dry-run` / `./cm health-digest --dry-run` print what would be
sent without posting or saving. The watchdog is silent when everything is healthy.
If you roll back to an older `RELEASE_TAG`, comment out the two health cron lines: the
old image has no `watchdog` command and the failure would only appear in `out/cron.log`.
