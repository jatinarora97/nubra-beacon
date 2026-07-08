"""Apply numbered SQL migrations to nubra_community (LLD-01 §9).

Tracking table (version + dirty) + advisory lock; one transaction per file.
A file is applied at most once, keyed by version. If a migration fails
mid-flight its row is left `dirty` and the next run aborts until it's resolved
by hand — editing an already-applied file is a no-op (it never re-runs).
Usage: python migrations/run_migrations.py [--dry-run]
"""
from __future__ import annotations

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
    dirty       boolean      NOT NULL DEFAULT false,
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
            for r in conn.execute("SELECT version, dirty FROM schema_migrations").fetchall()
        }
        dirty = sorted(v for v, is_dirty in applied.items() if is_dirty)
        if dirty:
            raise SystemExit(
                f"DIRTY: version(s) {dirty} left half-applied — resolve by hand before migrating"
            )
        for f in files:
            version = int(f.name.split("_")[0])
            if version in applied:
                continue
            if dry_run:
                print(f"pending: {f.name}")
                continue
            # Claim the version as dirty first (committed), then run the file in
            # its own transaction. A crash mid-migration leaves the row dirty.
            conn.execute(
                "INSERT INTO schema_migrations (version, filename, dirty) VALUES (%s, %s, true)",
                (version, f.name),
            )
            with psycopg.connect(settings.db_url) as tx:  # one transaction per file
                tx.execute(f.read_text())
            conn.execute("UPDATE schema_migrations SET dirty = false WHERE version = %s", (version,))
            print(f"applied: {f.name}")
        conn.execute("SELECT pg_advisory_unlock(hashtext('nubra_community:migrate'))")
    print("migrations up to date")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
