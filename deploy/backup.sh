#!/usr/bin/env bash
# Nightly DB backup (cron 02:00) — gzipped pg_dump into backups/, keep 14.
# Failure-safe: dump to a temp file, verify the gzip, THEN atomically rename —
# a failed/partial pg_dump (postgres down, disk full) must never enter the
# rotation as a plausible-looking corrupt file. Non-zero exit on any failure.
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M)
TMP="backups/.inprogress-${STAMP}.sql.gz"
OUT="backups/nubra_community-${STAMP}.sql.gz"
trap 'rm -f "$TMP"' EXIT

docker compose exec -T postgres pg_dump -U community nubra_community | gzip > "$TMP"
gzip -t "$TMP"                       # verify integrity before it enters rotation
[ -s "$TMP" ] || { echo "backup empty" >&2; exit 1; }
mv "$TMP" "$OUT"
echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"

# prune: keep the newest 14 completed backups
ls -1t backups/nubra_community-*.sql.gz 2>/dev/null | tail -n +15 | xargs -r rm --
