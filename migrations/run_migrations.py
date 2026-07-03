"""Apply numbered SQL migrations to nubra_community (LLD-01 §9).

Tracking table + sha256 drift check + advisory lock; one transaction per file.
Usage: python migrations/run_migrations.py [--dry-run]
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import psycopg

from community.config.settings import settings

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent

TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     integer      PRIMARY KEY,
    filename    text         NOT NULL,
    sha256      char(64)     NOT NULL,
    applied_at  timestamptz  NOT NULL DEFAULT now()
);
"""


def main(dry_run: bool = False) -> None:
    files = sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    with psycopg.connect(settings.db_url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext('nubra_community:migrate'))")
        conn.execute(TRACKING)
        applied = {
            r[0]: r[1]
            for r in conn.execute("SELECT version, sha256 FROM schema_migrations").fetchall()
        }
        for f in files:
            version = int(f.name.split("_")[0])
            sha = hashlib.sha256(f.read_bytes()).hexdigest()
            if version in applied:
                if applied[version] != sha:
                    raise SystemExit(f"DRIFT: {f.name} changed after being applied — aborting")
                continue
            if dry_run:
                print(f"pending: {f.name}")
                continue
            with psycopg.connect(settings.db_url) as tx:  # one transaction per file
                tx.execute(f.read_text())
                tx.execute(
                    "INSERT INTO schema_migrations (version, filename, sha256) VALUES (%s, %s, %s)",
                    (version, f.name, sha),
                )
            print(f"applied: {f.name}")
        conn.execute("SELECT pg_advisory_unlock(hashtext('nubra_community:migrate'))")
    print("migrations up to date")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
