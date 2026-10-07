# tests/test_health_migration.py
from __future__ import annotations

import pathlib
import re
import unittest

MIGRATION = pathlib.Path(__file__).resolve().parent.parent / "migrations" / "0023_health_monitoring.sql"


class HealthMigrationTests(unittest.TestCase):
    def test_file_exists_and_creates_the_three_tables(self):
        sql = MIGRATION.read_text()
        for table in ("job_runs", "health_state", "resource_samples"):
            self.assertRegex(sql, rf"CREATE TABLE {table}\b")

    def test_migration_is_additive_only(self):
        sql = re.sub(r"--.*", "", MIGRATION.read_text())  # ignore comments
        for forbidden in ("ALTER ", "DROP ", "DELETE ", "UPDATE ", "TRUNCATE "):
            self.assertNotIn(forbidden, sql.upper(), f"{forbidden.strip()} must not appear")
