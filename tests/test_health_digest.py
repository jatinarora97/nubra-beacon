# tests/test_health_digest.py
from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import runner
from community.health import config, digest, engine
from community.health.model import CRIT, OK, WARN, Result
from community.health.state import Row

NOW = datetime(2026, 10, 5, 2, 35, tzinfo=timezone.utc)  # 08:05 IST
CFG = config.load({})
CTX = {
    "jobs": [{"job": "run-local", "status": "ok", "started_at": NOW - timedelta(minutes=40),
              "finished_at": NOW - timedelta(minutes=30)}],
    "llm": {"day": date(2026, 10, 4), "calls": 143, "cost": 0.82},
    "resources": {"disk_used_pct": 63.2, "disk_free_gb": 41.0, "mem_available_pct": 54.0,
                  "load_per_core": 0.3, "db_size_gb": 2.14, "cron_log_mb": 12.0},
    "top_tables": [("social_items_y2026m09", 1_200_000_000)],
    "live": {"twitter": {"live": "ok"}},
}


class RenderTests(unittest.TestCase):
    def test_all_healthy_headline_mentions_muted_sources(self):
        text = digest.render([Result("a", OK, "fine"), Result("b", OK, "fine")], CTX, CFG, NOW)
        self.assertEqual(text.splitlines()[0],
                         "Beacon health: all 2 checks healthy (muted, known broken: reddit)")

    def test_problems_come_first_with_counts_and_hints(self):
        results = [Result("ok1", OK, "fine"),
                   Result("partitions:social_items", WARN, "27 days left"),
                   Result("disk", CRIT, "93% used", "free space on the VM")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertIn("3 checks, 1 critical, 1 warnings", text.splitlines()[0])
        self.assertLess(text.index("*Critical*"), text.index("*Warnings*"))
        self.assertLess(text.index("*Warnings*"), text.index("*Jobs*"))
        self.assertIn("- disk: 93% used", text)
        self.assertIn("What to check: free space on the VM", text)

    def test_sections_show_jobs_llm_resources_and_sources(self):
        results = [Result("source:twitter", OK, "last success 1 h ago"),
                   Result("source_items:twitter", OK, "newest item arrived 1 h ago")]
        text = digest.render(results, CTX, CFG, NOW)
        self.assertIn("- run-local: ok, last run 40 min ago", text)
        self.assertIn("- morning-build: no run recorded yet", text)
        self.assertIn("143 calls", text)
        self.assertIn("$0.82", text)
        self.assertIn("disk 63% used (41 GB free)", text)
        self.assertIn("database 2.1 GB", text)
        self.assertIn("social_items_y2026m09", text)
        self.assertIn("- twitter: last success 1 h ago", text)
        self.assertIn("live probe ok", text)

    def test_text_is_plain_ascii(self):
        results = [Result("disk", CRIT, "93% used", "free space")]
        self.assertTrue(all(ord(c) < 128 for c in digest.render(results, CTX, CFG, NOW)))

    def test_missing_context_pieces_do_not_crash(self):
        empty = {"jobs": [], "llm": {"day": date(2026, 10, 4), "calls": 0, "cost": 0.0},
                 "resources": {}, "top_tables": [], "live": {}}
        self.assertIn("Beacon health", digest.render([], empty, CFG, NOW))


class LiveResultsTests(unittest.TestCase):
    def test_only_real_probe_problems_become_warnings(self):
        ctx = {"live": {"twitter": {"live": "ok"}, "youtube": {"live": "http_403"},
                        "instagram": {"live": "no_key"}, "reddit": {"live": "blocked_or_down"},
                        "app_reviews": {"live": "no_probe"}}}
        res = {r.key: r for r in digest.live_results(ctx)}
        self.assertEqual(sorted(res), ["live_probe:instagram", "live_probe:reddit",
                                       "live_probe:youtube"])
        self.assertTrue(all(r.level == WARN for r in res.values()))
        self.assertIn("API key is not set", res["live_probe:instagram"].detail)
        self.assertIn("http_403", res["live_probe:youtube"].detail)


class RunDigestTests(unittest.TestCase):
    def setUp(self):
        self.saved: list[Row] = []
        self.seen_cfg: dict = {}

        def capture_cfg(cfg, now):
            self.seen_cfg.update(cfg)
            return []
        capture_cfg.PREFIXES = ()
        self.capture_cfg = capture_cfg
        for p in (patch.object(engine, "_db_up", return_value=True),
                  patch.object(engine.state, "load_states", return_value={}),
                  patch.object(engine.state, "save", side_effect=self.saved.append),
                  patch.object(engine.digest, "collect_context", return_value=CTX),
                  patch.object(engine, "CRITICAL_CHECKS", [engine.checks_jobs.check_watchdog_heartbeat]),
                  patch.object(engine, "DIGEST_ONLY_CHECKS", [])):
            p.start()
            self.addCleanup(p.stop)

    def test_posts_the_rendered_message_and_saves_only_the_heartbeat(self):
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        post.assert_called_once()
        self.assertTrue(post.call_args.args[0].startswith("Beacon health:"))
        self.assertEqual(summary["posted"], "sent")
        self.assertEqual([r.key for r in self.saved], ["digest_heartbeat"])

    def test_dry_run_returns_the_text_and_saves_nothing(self):
        summary = engine.run_digest(dry_run=True, now=NOW)
        self.assertEqual(summary["posted"], "dry-run")
        self.assertIn("Beacon health:", summary["text"])
        self.assertEqual(self.saved, [])

    def test_probes_are_forced_so_the_hourly_gate_is_bypassed(self):
        with patch.object(engine, "CRITICAL_CHECKS", [self.capture_cfg]), \
             patch.object(engine.notify, "post", return_value="sent"):
            engine.run_digest(now=NOW)
        self.assertTrue(self.seen_cfg["_force"])

    def test_live_probe_failures_appear_as_warnings(self):
        ctx = {**CTX, "live": {"youtube": {"live": "http_403"}}}
        with patch.object(engine.digest, "collect_context", return_value=ctx), \
             patch.object(engine.notify, "post", return_value="sent") as post:
            engine.run_digest(now=NOW)
        self.assertIn("live_probe:youtube", post.call_args.args[0])

    def test_database_down_sends_a_short_critical_instead_of_crashing(self):
        engine._db_up.return_value = False
        with patch.object(engine.notify, "post", return_value="sent") as post:
            summary = engine.run_digest(now=NOW)
        self.assertTrue(summary["db_unreachable"])
        self.assertIn("could not run", post.call_args.args[0])


class DigestCommandTests(unittest.TestCase):
    def test_dry_run_prints_the_text_then_a_summary(self):
        summary = {"checks": 3, "critical": [], "warnings": [], "posted": "dry-run", "text": "Beacon health: ok"}
        with patch("community.health.engine.run_digest", return_value=summary) as run, \
             patch.object(runner.typer, "echo") as echo:
            runner.health_digest(dry_run=True, no_live=True)
        run.assert_called_once_with(dry_run=True, live=False)
        self.assertEqual(echo.call_args_list[0].args[0], "Beacon health: ok")
        self.assertNotIn("Beacon health: ok", echo.call_args_list[1].args[0])

    def test_unexpected_exception_exits_one(self):
        with patch("community.health.engine.run_digest", side_effect=RuntimeError("x")):
            with self.assertRaises(SystemExit) as ctx:
                runner.health_digest(dry_run=False, no_live=False)
        self.assertEqual(ctx.exception.code, 1)
