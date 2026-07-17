# Extra Sources Deployment Guide

## Scope

This branch adds YouTube, GitHub, broker-community, and app-review collection
to the current Beacon application. It does not replace the existing Reddit/X
collectors or introduce a second database or deployment process.

## Required Deployment Values

Keep every existing main-branch environment value unchanged. Add:

```dotenv
YOUTUBE_API_KEY=
GITHUB_TOKEN=
```

`YOUTUBE_API_KEY` is required only for YouTube. `GITHUB_TOKEN` is optional but
recommended. Public broker communities and public app reviews require no key.

Do not commit `.env`.

## Pre-deployment Check

From the repository root:

```bash
pip install -r requirements-extra-sources.txt
python scripts/test_collectors_fetch_only.py --source github
python scripts/test_collectors_fetch_only.py --source broker_communities
python scripts/test_collectors_fetch_only.py --source app_reviews
python scripts/test_collectors_fetch_only.py --source youtube
```

If YouTube has no key, its check safely returns no rows. This does not affect
the other sources.

## Normal Deployment

Use the same deployment flow as main:

```bash
docker compose --profile app up -d --build
```

The existing one-shot `migrate` service applies migration
`0010_extra_source_types.sql` before the API starts. The migration is
idempotently tracked by Beacon's current migration runner.

After the stack is healthy:

```bash
curl http://localhost:8400/api/v1/health
curl http://localhost:8400/api/v1/source-health
docker compose --profile app ps
```

Open:

- Dashboard: `http://localhost:3000`
- Source health: `http://localhost:3000/source-health`
- Explore: `http://localhost:3000/explore`

The existing scheduler invokes the normal scrape stage. No second cron or
worker is required.

The API Dockerfile installs `requirements-extra-sources.txt` in a separate,
small layer. This preserves the existing cached Beacon dependency layer and
keeps the source addition from forcing a full ML/browser dependency download.
BuildKit cache mounts retain downloaded Python wheels outside the image, so an
interrupted build can resume without downloading the entire main stack again.

## Failure Behaviour

A timeout, rate limit, missing key, changed forum endpoint, or store error is
captured at the add-on source boundary. Reddit and X continue, remaining
add-on sources continue, and the error is visible in source health.

Rows are idempotent on `(source, external_id)`, so retrying a scrape does not
duplicate already stored content.

## Rollback

Roll back the application images or code using the same main-branch procedure.
Migration `0010` is additive and can safely remain in place: older application
code continues to use its original source values and ignores the additional
rows. A database rollback is not required for an application rollback.

## Known External Limits

- YouTube is quota-bound by the Google project behind `YOUTUBE_API_KEY`.
- Unauthenticated GitHub search has a low public rate limit.
- Public community endpoints can change or block automated requests.
- Apple reviews require numeric `apple_id` values in the registry.
- App-store availability and review ordering are controlled by the stores.
