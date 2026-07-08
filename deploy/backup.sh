#!/bin/sh
# Nightly Postgres backup — gzip pg_dump into ./backups, keep the last 14.
# Run from cron (deploy/crontab.prod) or by hand: ./deploy/backup.sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M)
docker compose exec -T postgres pg_dump -U community nubra_community \
    | gzip > "backups/nubra_community-$STAMP.sql.gz"
# prune: keep newest 14
ls -1t backups/nubra_community-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "backup written: backups/nubra_community-$STAMP.sql.gz"
