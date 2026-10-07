# tests/test_health_config.py
from __future__ import annotations

import unittest

from community.health import config
from community.health.model import CRIT, OK, RANK, WARN, Result, owns


class ModelTests(unittest.TestCase):
    def test_levels_rank_in_severity_order(self):
        self.assertLess(RANK[OK], RANK[WARN])
        self.assertLess(RANK[WARN], RANK[CRIT])

    def test_result_defaults_and_immutability(self):
        r = Result("disk", CRIT, "92% used")
        self.assertEqual(r.hint, "")
        with self.assertRaises(Exception):
            r.level = OK  # frozen

    def test_owns_records_prefixes(self):
        @owns("a:", "b")
        def check(cfg, now):
            return []
        self.assertEqual(check.PREFIXES, ("a:", "b"))


class ConfigTests(unittest.TestCase):
    def test_defaults_when_registry_has_no_health_block(self):
        cfg = config.load({})
        self.assertEqual(cfg["remind_hours"], 6)
        self.assertEqual(cfg["muted"], ["reddit"])
        self.assertFalse(cfg["fallback_to_default_webhook"])
        self.assertEqual(cfg["slack_webhook_env"], "SLACK_ALERTS_WEBHOOK_URL")
        self.assertIn("run-local", cfg["jobs"])

    def test_registry_overrides_merge_deeply(self):
        cfg = config.load({"health": {"remind_hours": 2,
                                      "resources": {"disk_crit_pct": 95}}})
        self.assertEqual(cfg["remind_hours"], 2)
        self.assertEqual(cfg["resources"]["disk_crit_pct"], 95)
        self.assertEqual(cfg["resources"]["disk_warn_pct"], 80)  # untouched default

    def test_load_returns_a_copy(self):
        a = config.load({})
        a["muted"].append("x")
        self.assertEqual(config.load({})["muted"], ["reddit"])

    def test_run_local_schedule_matches_the_prod_crontab(self):
        hours = config.load({})["jobs"]["run-local"]["hours"]
        self.assertEqual(sorted(hours), [0] + list(range(7, 24)))

    def test_every_default_job_declares_its_timing(self):
        for name, job in config.load({})["jobs"].items():
            for key in ("hours", "start_window_min", "grace_min",
                        "crit_after_missed", "max_run_min"):
                self.assertIn(key, job, f"{name} is missing {key}")
            self.assertLess(job["start_window_min"], job["grace_min"] + 1, name)

    def test_registry_health_block_only_uses_known_keys(self):
        import pathlib

        import yaml
        registry_path = pathlib.Path(config.__file__).parent.parent / "config" / "registry.yaml"
        reg = yaml.safe_load(registry_path.read_text())
        self.assertIn("health", reg, "registry.yaml must carry the health: block")

        def check(over, base, path="health"):
            for key, value in over.items():
                self.assertIn(key, base, f"unknown key {path}.{key}")
                if isinstance(value, dict):
                    check(value, base[key], f"{path}.{key}")

        check(reg["health"], config.DEFAULTS)
        merged = config.load(reg)  # the real registry must merge cleanly
        self.assertEqual(merged["muted"], reg["health"]["muted"])
